# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RAGInbox is a configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management. It combines document processing, vector search, and LLM-powered question answering with email integration capabilities. The system can be deployed in multiple instances with different configurations for various organizations or departments.

## Core Architecture

### High-Level Flow

1. **Document Ingestion** → Documents (PDF, DOCX, TXT, CSV) → Chunking → Embeddings → ChromaDB
2. **Email Integration** → IMAP inbox monitoring → Parse/validate → Extract attachments → Process into KB or handle queries
3. **Query Processing** → Email/API query → RAG retrieval → LLM response → Email reply/API response

### Multi-Mode Email Processing

The system has **dual whitelist validation** with separate permissions for teaching (KB ingestion) vs querying:

- **Direct emails (To: bot)** → RAG query processing + automated reply (if sender in query whitelist)
  - Exception: Forwarded emails (Fw:/Fwd: prefix) → KB ingestion (configurable via `FORWARD_TO_KB_ENABLED`)
- **CC/BCC emails** → Silent KB ingestion (if sender in teach whitelist)
- **Forwarded emails** → KB ingestion (if sender in teach whitelist and `FORWARD_TO_KB_ENABLED=true`)

Users can be in one whitelist, both whitelists, or neither. Configure in:
- `data/config/allowed_teachers.txt` (who can add to KB)
- `data/config/allowed_queriers.txt` (who can ask questions)

### Key Components

#### 1. Document Processing (`src/document_processing/`)
- **DocumentProcessor**: Parses PDF, DOCX, TXT, CSV using LlamaIndex
- **KnowledgeBaseManager**: ChromaDB vector storage with deduplication via file hashing
- **FileWatcher**: Monitors `data/documents/` for new files using watchdog

#### 2. RAG Engine (`src/rag/`)
- **RAGEngine**: LlamaIndex query engine with customizable prompts per instance
- **QueryHandler**: High-level interface for query processing with source citations
- **Function Calling System** (`src/rag/tools/`): Calendar event creation, export formatting

#### 3. Email Integration (`src/email/`)
- **EmailClient**: IMAP client with SSL/TLS and STARTTLS support (ports 993, 143)
- **EmailParser**: Parses headers, body (HTML-to-text), validates against whitelists
- **AttachmentHandler**: Extracts and validates attachments (file type, size limits)
- **EmailProcessor**: Orchestrates the full pipeline (fetch → parse → extract → process → track)
- **EmailSender**: SMTP email sending with TLS, supports HTML/markdown/text formats
- **MessageTracker**: SQLite or MariaDB tracking to prevent duplicate processing
- **EmailService**: Background daemon with exponential backoff and graceful shutdown
- **WhitelistValidator**: Dual validation for teach vs query permissions with domain wildcards

#### 4. Database Layer (`src/email/db_*.py`)
- **db_models.py**: SQLAlchemy models for `ProcessedMessage` and `ProcessingStats`
- **db_manager.py**: Database abstraction supporting SQLite (default) and MariaDB
- **message_tracker.py**: Message tracking interface with stats aggregation

#### 5. Configuration (`src/config.py`)
- Pydantic Settings-based configuration with `.env` file support
- Instance-specific customization: `INSTANCE_NAME`, `INSTANCE_DESCRIPTION`, `ORGANIZATION`
- Custom system prompts: `RAG_CUSTOM_PROMPT_FILE` (appends to base prompt)
- Custom email footers: `EMAIL_CUSTOM_FOOTER_FILE`
- Email response format: `EMAIL_RESPONSE_FORMAT` (html/markdown/text)

## Common Development Tasks

### Development Workflow

**Docker-First Development** (Recommended):
1. Make code changes in `src/` or `tests/` directories
2. Changes are immediately available in the running container (volume-mapped)
3. Run tests in Docker: `docker exec raginbox-web pytest tests/ -v`
4. No need to rebuild container unless dependencies change in `pyproject.toml`
5. Pre-commit hook automatically runs Black, Ruff, and pytest before each commit

**When to rebuild Docker images:**
- After modifying `pyproject.toml` (new dependencies)
- After changing `Dockerfile`
- Otherwise, code changes are live-reloaded via volume mounts

### Running the System

```bash
# Run email service (monitors inbox for KB updates and queries)
python run_email_service.py

# Or use Docker Compose
docker-compose up -d
```

### CLI Commands (Docker-only)

RAGInbox includes a unified CLI for administration:

```bash
# Basic usage
docker exec raginbox-web raginbox-cli [COMMAND] [OPTIONS]

# Get help
docker exec raginbox-web raginbox-cli help
docker exec raginbox-web raginbox-cli --help

# Knowledge base operations
docker exec raginbox-web raginbox-cli kb list       # List documents
docker exec raginbox-web raginbox-cli kb stats      # Show statistics
docker exec raginbox-web raginbox-cli kb reingest   # Reingest all documents

# Database operations
docker exec raginbox-web raginbox-cli db init       # Initialize database
docker exec raginbox-web raginbox-cli db test       # Test connection
docker exec raginbox-web raginbox-cli db info       # Show DB info
docker exec raginbox-web raginbox-cli db stats      # Show statistics

# Backup operations
docker exec raginbox-web raginbox-cli backup create  # Create backup
docker exec raginbox-web raginbox-cli backup list    # List backups
docker exec raginbox-web raginbox-cli backup cleanup # Clean old backups

# System information
docker exec raginbox-web raginbox-cli version        # Show version
docker exec raginbox-web raginbox-cli info           # Show configuration
```

**Tip:** Create an alias for easier access:
```bash
alias raginbox="docker exec raginbox-web raginbox-cli"
# Then use: raginbox kb list, raginbox db stats, etc.
```

See `docs/CLI.md` for complete CLI documentation.

### Testing

**CRITICAL: Always test code in the Docker container**, not with local `.venv`:

```bash
# Start Docker services first
docker-compose up -d

# Run all tests in container
docker exec raginbox-web pytest tests/ -v

# Run specific test file
docker exec raginbox-web pytest tests/test_email_parser.py -v

# Run specific test function
docker exec raginbox-web pytest tests/test_email_parser.py::test_function_name -v

# Run with coverage report
docker exec raginbox-web pytest tests/ -v --cov=src --cov-report=term-missing

# Run tests matching a pattern
docker exec raginbox-web pytest tests/ -v -k "email"
```

**Why Docker for testing?**
- The `src/` and `tests/` directories are volume-mapped to the container
- Code changes are immediately available without rebuilding
- Ensures consistent test environment with all dependencies
- Container name: `raginbox-web`

### Code Quality & Pre-commit Hook

RAGInbox includes a pre-commit hook that automatically runs before each commit:

1. **Black** - Code formatting
2. **Ruff** - Linting
3. **Pytest** - Full test suite in Docker

**Manual commands:**
```bash
# Format code (required before committing)
black src/ tests/

# Fix auto-fixable linting issues
ruff check src/ tests/ --fix

# Check without fixing
ruff check src/ tests/
```

**Pre-commit workflow:**
```bash
# The hook runs automatically on commit
git commit -m "your message"

# If checks fail, fix and re-commit
black src/ tests/
ruff check src/ tests/ --fix
docker exec raginbox-web pytest tests/

# Only in emergencies (causes CI failures)
git commit --no-verify -m "bypass hook"
```

See `docs/PRE_COMMIT_HOOK.md` for troubleshooting.

### Docker Deployment

```bash
# Build and start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f raginbox-web
docker-compose logs -f raginbox-email

# Stop services
docker-compose down

# Rebuild after dependency changes
docker-compose build
docker-compose up -d

# Pull latest published image from GitHub Container Registry
docker pull ghcr.io/gilestrolab/raginbox:latest
```

### Debugging in Docker

```bash
# Access Python REPL in container
docker exec -it raginbox-web python

# Access bash shell in container
docker exec -it raginbox-web bash

# Check container logs with timestamps
docker-compose logs -f --timestamps raginbox-web

# Inspect container environment variables
docker exec raginbox-web env | grep -E "(DB_|EMAIL_|IMAP_|SMTP_)"

# Check database connection
docker exec raginbox-web raginbox-cli db test

# View knowledge base contents
docker exec raginbox-web raginbox-cli kb list
```

## Important Implementation Details

### Email Processing Flow

1. **EmailService** polls IMAP inbox every `EMAIL_CHECK_INTERVAL` seconds
2. **EmailProcessor.process_emails()** fetches unread messages
3. For each message:
   - Parse headers, body, extract attachments
   - Check if already processed via **MessageTracker**
   - Determine action type (query vs KB ingestion) based on To/CC/BCC/forwarding
   - **Validate sender** against appropriate whitelist (teach vs query)
   - For KB ingestion: Process attachments + body → **DocumentProcessor** → **KnowledgeBaseManager**
   - For queries: Extract question → **QueryHandler** → **RAGEngine** → **EmailSender**
   - Mark as processed in database

### Forwarded Email Detection

The system has configurable forwarded email detection (`src/email/email_parser.py:is_forwarded()`):
- Checks subject line for prefixes like "Fw:", "Fwd:", "I:", "RV:" (case-insensitive)
- Prefixes configurable via `FORWARD_SUBJECT_PREFIXES` environment variable
- Enable/disable via `FORWARD_TO_KB_ENABLED` (default: true)
- When enabled: forwarded emails (To: bot) are treated as KB content, not queries

### Database Abstraction

The system supports both SQLite (default, simple) and MariaDB (production/Docker):
- Set via `DB_TYPE` environment variable
- **SQLite**: `SQLITE_DB_PATH` (default: `data/message_tracker.db`)
- **MariaDB**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Connection URL built via `settings.get_database_url()`
- Use pymysql driver for MariaDB (pure Python, container-friendly)

### RAG Customization

Custom system prompts can be added without modifying code:
1. Create `data/config/custom_prompt.txt`
2. Add custom instructions (appended to base prompt)
3. Set `RAG_CUSTOM_PROMPT_FILE=data/config/custom_prompt.txt` in `.env`

Example custom prompt:
```
Additional instructions:
- Always use British English spelling
- Reference specific policy numbers when available
- If a policy has changed recently, mention the effective date
```

### Email Response Customization

Three format options via `EMAIL_RESPONSE_FORMAT`:
- **html** (default): Professional styled HTML with CSS
- **markdown**: Plain text with markdown syntax
- **text**: Simple plain text

Custom footers via `EMAIL_CUSTOM_FOOTER_FILE`:
1. Copy `data/config/email_footer.txt.example`
2. Customize the text
3. Set `EMAIL_CUSTOM_FOOTER_FILE=data/config/email_footer.txt` in `.env`

### Data Directory Structure

All persistent data lives under `data/` for easy Docker volume mounting:
- `data/documents/` - Source documents (monitored by FileWatcher)
- `data/chroma_db/` - Vector database storage
- `data/config/` - Configuration files (whitelists, custom prompts, footers)
- `data/logs/` - Application logs (`dols_gpt.log`)
- `data/temp_attachments/` - Temporary email attachments (auto-cleaned)
- `data/message_tracker.db` - SQLite database (if using SQLite)

### Testing Strategy

- **Mock external services**: IMAP/SMTP servers, LLM API calls
- **Use in-memory SQLite** for database tests
- **Test categories**: Expected behavior, edge cases, failure scenarios
- **Coverage target**: Minimum 70%
- Tests mirror source structure in `/tests`

## Configuration Management

Key environment variables (see `.env.example` for full list):

### Instance Customization
- `INSTANCE_NAME` - Name of assistant (e.g., "DoLS-GPT", "HR-Assistant")
- `INSTANCE_DESCRIPTION` - Purpose description (used in prompts)
- `ORGANIZATION` - Organization name (optional)

### API Configuration
- `OPENAI_API_KEY`, `OPENAI_API_BASE` - For embeddings (supports Naga.ac, OpenAI)
- `OPENROUTER_API_KEY`, `OPENROUTER_API_BASE`, `OPENROUTER_MODEL` - For LLM queries

### Email Configuration
- **IMAP**: `IMAP_SERVER`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_USE_SSL`
- **SMTP**: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`
- `EMAIL_TARGET_ADDRESS` - Bot's email address
- `EMAIL_DISPLAY_NAME` - Display name in emails
- `EMAIL_CHECK_INTERVAL` - Polling frequency (seconds)

### Whitelist Configuration (Dual Lists)
- **Teaching**: `EMAIL_TEACH_WHITELIST_FILE`, `EMAIL_TEACH_WHITELIST_ENABLED`
- **Query**: `EMAIL_QUERY_WHITELIST_FILE`, `EMAIL_QUERY_WHITELIST_ENABLED`

### RAG Configuration
- `CHUNK_SIZE`, `CHUNK_OVERLAP` - Document chunking parameters
- `TOP_K_RETRIEVAL` - Number of chunks to retrieve
- `SIMILARITY_THRESHOLD` - Minimum similarity score
- `RAG_CUSTOM_PROMPT_FILE` - Custom system prompt additions (optional)

### Response Customization
- `EMAIL_RESPONSE_FORMAT` - html/markdown/text
- `EMAIL_CUSTOM_FOOTER_FILE` - Custom email footer (optional)

## Package Installation

The project uses `pyproject.toml` for package configuration:

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install with MariaDB support
pip install -e ".[mariadb]"

# Install both
pip install -e ".[dev,mariadb]"
```

## CI/CD Pipeline

GitHub Actions workflows in `.github/workflows/`:

### CI (`ci.yml`)
Runs on push/PR to main/develop:
- **Linting**: Black formatting check, Ruff linting
- **Testing**: Pytest on Python 3.11, 3.12, 3.13
- **Coverage**: Automated reporting to Codecov

### Docker Build (`docker.yml`)
- Builds multi-platform images (amd64, arm64)
- Publishes to `ghcr.io/gilestrolab/raginbox`
- Tags: `latest`, `v1.2.3`, `main-abc123`

### Release (`release.yml`)
- Automatic changelog generation
- GitHub releases with artifacts
- Triggered by version tags (`git tag v1.0.0`)

## Known Issues and Workarounds

### Office 365 Authentication
Imperial College's Office 365 disables basic auth at policy level. Solutions:
1. Use alternative IMAP server (e.g., mailu.gilest.ro for testing)
2. Implement OAuth2 authentication (future enhancement)
3. Contact Imperial IT to enable basic auth for specific account

See `docs/EMAIL_AUTH_ISSUE.md` for detailed troubleshooting.

### STARTTLS Support
The EmailClient supports both SSL (port 993) and STARTTLS (port 143). Set `IMAP_PORT` appropriately:
- Port 993: Direct SSL connection (`IMAP_USE_SSL=true`)
- Port 143: STARTTLS upgrade (`IMAP_USE_SSL=false`)

## Common Pitfalls & Troubleshooting

### Testing Issues

**Problem**: Tests fail locally but need to run in Docker
**Solution**: Always use `docker exec raginbox-web pytest tests/` - local `.venv` may have missing dependencies

**Problem**: Container not running when trying to test
**Solution**: `docker-compose up -d` first, then run tests

**Problem**: Tests pass in container but fail in CI
**Solution**: Ensure you've committed all required files and that `.dockerignore` isn't excluding necessary files

### Development Issues

**Problem**: Code changes not reflected in container
**Solution**: Check volume mounts in `docker-compose.yml` - `src/` and `tests/` should be mounted

**Problem**: New dependency not available in container
**Solution**: After modifying `pyproject.toml`, rebuild: `docker-compose build && docker-compose up -d`

**Problem**: Permission errors with data directory
**Solution**: Check Docker volume permissions - may need to adjust ownership

### Database Issues

**Problem**: "Table doesn't exist" errors
**Solution**: Initialize database: `docker exec raginbox-web raginbox-cli db init`

**Problem**: Connection errors with MariaDB
**Solution**: Check `docker-compose logs mariadb` and ensure healthcheck passes before services start

### Email Processing Issues

**Problem**: Emails not being processed
**Solution**:
1. Check whitelist files exist and contain valid entries
2. Verify IMAP credentials with `accessories/test_email_connection.py`
3. Check logs: `docker-compose logs -f raginbox-email`

**Problem**: Can't send email replies
**Solution**: Verify SMTP settings - most providers require app-specific passwords or OAuth2

### Pre-commit Hook Issues

**Problem**: Pre-commit hook not running
**Solution**: `chmod +x .git/hooks/pre-commit`

**Problem**: Hook fails but changes are needed urgently
**Solution**: Use `git commit --no-verify` (will likely fail CI - fix before pushing)

## Module Organization

Each email component follows a consistent pattern:
- `email_client.py` - Main client class with connection management
- `email_parser.py` - Parsing logic and data models
- `email_sender.py` - Sending logic with formatting
- `attachment_handler.py` - Attachment extraction and validation
- `email_processor.py` - Orchestration and integration
- `email_service.py` - Background daemon with auto-reconnection

RAG tools follow similar organization:
- `tools/base.py` - Base tool interface
- `tools/calendar_tools.py` - Calendar event creation
- `tools/export_tools.py` - Export formatting
- `tools/tool_executor.py` - Tool execution and error handling

## Project Status

**Current Phase**: All core phases completed - production ready

**Completed**:
- ✅ Phase 1: Core RAG with document processing
- ✅ Phase 2: Email inbox integration (IMAP, parsing, attachments, tracking)
- ✅ Phase 3: Email query handler (SMTP, RAG-powered replies, HTML formatting)
- ✅ Phase 4: Web frontend with chat interface, OTP authentication, admin panel
- ✅ Phase 5: Docker deployment and CI/CD

**Test Coverage**: Run `docker exec raginbox-web pytest tests/ -v` to verify current test status
