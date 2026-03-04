# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Berengario is a configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management. It combines document processing, vector search, and LLM-powered question answering with email integration capabilities. The system can be deployed in multiple instances with different configurations for various organizations or departments.

## Core Architecture

### High-Level Flow

1. **Document Ingestion** → Documents (PDF, DOCX, TXT, CSV, XLS, XLSX) → Enhancement (for CSV/Excel) → Chunking → Embeddings → ChromaDB
2. **Email Integration** → IMAP inbox monitoring → Parse/validate → Extract attachments → Process into KB or handle queries
3. **Query Processing** → Email/API query → Query Optimization → RAG retrieval → LLM response → Email reply/API response

### Multi-Mode Email Processing

The system has **dual whitelist validation** with separate permissions for teaching (KB ingestion) vs querying:

- **Direct emails (To: bot)** → RAG query processing + automated reply (if sender in query whitelist)
  - Exception: Forwarded emails (Fw:/Fwd: prefix) → KB ingestion (configurable via `FORWARD_TO_KB_ENABLED`)
- **Teach address emails** (To/CC: teach address) → KB ingestion (if `EMAIL_TEACH_ADDRESS` is configured, takes highest priority)
- **CC/BCC emails** → Silent KB ingestion (if sender in teach whitelist)
- **Forwarded emails** → KB ingestion (if sender in teach whitelist and `FORWARD_TO_KB_ENABLED=true`)

Users can be in one whitelist, both whitelists, or neither. Configure in:
- `data/config/allowed_teachers.txt` (who can add to KB)
- `data/config/allowed_queriers.txt` (who can ask questions)

### Key Components

#### 1. Document Processing (`src/document_processing/`)
- **DocumentProcessor**: Parses PDF, DOCX, TXT, CSV, XLS, XLSX using LlamaIndex
- **EnhancementProcessor**: LLM-based enhancement for structured data (CSV/Excel) - converts dry tables to narrative text and generates Q&A pairs for improved RAG retrieval
- **KnowledgeBaseManager**: ChromaDB vector storage with deduplication via file hashing
- **FileWatcher**: Monitors `data/documents/` for new files using watchdog

#### 2. RAG Engine (`src/rag/`)
- **RAGEngine**: LlamaIndex query engine with customizable prompts per instance
- **QueryHandler**: High-level interface for query processing with source citations
- **QueryOptimizer**: LLM-based query optimization for improved retrieval (expansion, rewriting, context-aware)
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
3. Run tests in Docker: `docker exec berengario-dev pytest tests/ -v`
4. No need to rebuild container unless dependencies change in `pyproject.toml`
5. Pre-commit hook automatically runs Black, Ruff, and pytest before each commit

**Docker Containers:**

Berengario uses a streamlined container setup with 3 production containers + 1 optional dev container:

- **Production Containers** (3 - start automatically):
  - `berengario-web`: Web interface (production image)
  - `berengario-email`: Email service (production image)
  - `berengario-db`: MariaDB database (shared by all services)

- **Development Container** (1 - starts only when explicitly requested):
  - `berengario-dev`: Testing and development tools (dev image)
    - Includes: pytest, black, ruff, coverage, gcc/g++
    - Used for: Running tests, linting, formatting
    - Shares the same database as production
    - Does NOT run the email service (utility container only)

**Development Workflow:**

```bash
# Start production services only (web, email, database)
docker-compose up -d

# Start production services + dev container (when needed for testing)
docker-compose --profile dev up -d

# Run tests (will auto-start dev container if not running)
docker-compose run --rm berengario-dev pytest tests/ -v

# Or if dev container is already running:
docker exec berengario-dev pytest tests/ -v

# Run code formatting
docker-compose run --rm berengario-dev black src/ tests/

# Run linting
docker-compose run --rm berengario-dev ruff check src/ tests/ --fix

# Run with coverage
docker-compose run --rm berengario-dev pytest tests/ -v --cov=src --cov-report=term-missing

# Access dev shell
docker-compose run --rm berengario-dev bash

# Stop all services (including dev if running)
docker-compose --profile dev down
```

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

Berengario includes a unified CLI for administration:

```bash
# Basic usage
docker exec berengario-web berengario-cli [COMMAND] [OPTIONS]

# Get help
docker exec berengario-web berengario-cli help
docker exec berengario-web berengario-cli --help

# Knowledge base operations
docker exec berengario-web berengario-cli kb list       # List documents
docker exec berengario-web berengario-cli kb stats      # Show statistics
docker exec berengario-web berengario-cli kb reingest   # Reingest all documents

# Database operations
docker exec berengario-web berengario-cli db init       # Initialize database
docker exec berengario-web berengario-cli db test       # Test connection
docker exec berengario-web berengario-cli db info       # Show DB info
docker exec berengario-web berengario-cli db stats      # Show statistics

# Backup operations
docker exec berengario-web berengario-cli backup create  # Create backup
docker exec berengario-web berengario-cli backup list    # List backups
docker exec berengario-web berengario-cli backup cleanup # Clean old backups

# System information
docker exec berengario-web berengario-cli version        # Show version
docker exec berengario-web berengario-cli info           # Show configuration
```

**Tip:** Create an alias for easier access:
```bash
alias berengario="docker exec berengario-web berengario-cli"
# Then use: berengario kb list, berengario db stats, etc.
```

See `docs/CLI.md` for complete CLI documentation.

### Testing

**CRITICAL: Always test code in the Docker container**, not with local `.venv`:

```bash
# Method 1: Use docker-compose run (recommended - auto-starts/stops dev container)
docker-compose run --rm berengario-dev pytest tests/ -v

# Method 2: Start dev container persistently, then use docker exec
docker-compose --profile dev up -d
docker exec berengario-dev pytest tests/ -v

# Run specific test file
docker-compose run --rm berengario-dev pytest tests/test_email_parser.py -v

# Run specific test function
docker-compose run --rm berengario-dev pytest tests/test_email_parser.py::test_function_name -v

# Run with coverage report
docker-compose run --rm berengario-dev pytest tests/ -v --cov=src --cov-report=term-missing

# Run tests matching a pattern
docker-compose run --rm berengario-dev pytest tests/ -v -k "email"
```

**Why Docker for testing?**
- The `src/` and `tests/` directories are volume-mapped to the container
- Code changes are immediately available without rebuilding
- Ensures consistent test environment with all dependencies
- The dev container includes pytest and all testing tools
- Container name: `berengario-dev`

**Note:** Production containers (`berengario-web`, `berengario-email`) do not include testing tools. Always use `berengario-dev` for running tests.

### Code Quality & Pre-commit Hook

Berengario includes a pre-commit hook that automatically runs before each commit:

1. **Black** - Code formatting
2. **Ruff** - Linting
3. **Pytest** - Full test suite in Docker

**Manual commands (using dev container):**
```bash
# Format code (required before committing)
docker-compose run --rm berengario-dev black src/ tests/

# Fix auto-fixable linting issues
docker-compose run --rm berengario-dev ruff check src/ tests/ --fix

# Check without fixing
docker-compose run --rm berengario-dev ruff check src/ tests/

# Or use local tools if installed
black src/ tests/
ruff check src/ tests/ --fix
```

**Pre-commit workflow:**
```bash
# The hook runs automatically on commit
git commit -m "your message"

# If checks fail, fix and re-commit
docker-compose run --rm berengario-dev black src/ tests/
docker-compose run --rm berengario-dev ruff check src/ tests/ --fix
docker-compose run --rm berengario-dev pytest tests/

# Only in emergencies (causes CI failures)
git commit --no-verify -m "bypass hook"
```

See `docs/PRE_COMMIT_HOOK.md` for troubleshooting.

### Docker Deployment

```bash
# Build and start production services (web, email, database)
docker-compose up -d

# Build and start with dev container included
docker-compose --profile dev up -d

# View logs for specific services
docker-compose logs -f berengario-web
docker-compose logs -f berengario-email

# Stop production services
docker-compose down

# Stop all services including dev
docker-compose --profile dev down

# Rebuild after dependency changes
docker-compose build
docker-compose up -d

# Pull latest published image from GitHub Container Registry
docker pull ghcr.io/gilestrolab/berengar.io:latest
```

**Building specific targets manually:**
```bash
# Build production image
docker build -t berengario:prod --target production .

# Build development image
docker build -t berengario:dev --target dev .
```

### Debugging in Docker

```bash
# Access Python REPL in containers
docker exec -it berengario-web python      # Production web
docker exec -it berengario-email python    # Production email
docker-compose run --rm berengario-dev python  # Development (on-demand)

# Access bash shell in containers
docker exec -it berengario-web bash
docker exec -it berengario-email bash
docker-compose run --rm berengario-dev bash  # Development (on-demand)

# Check container logs with timestamps
docker-compose logs -f --timestamps berengario-web
docker-compose logs -f --timestamps berengario-email

# Inspect container environment variables
docker exec berengario-web env | grep -E "(DB_|EMAIL_|IMAP_|SMTP_)"

# Check database connection
docker exec berengario-web berengario-cli db test

# View knowledge base contents
docker exec berengario-web berengario-cli kb list
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

### Document Enhancement

The system automatically enhances structured data files (CSV/Excel) during ingestion to improve RAG retrieval:

**Problem**: Dry, tabular data (spreadsheets, CSV files) retrieves poorly with semantic search because:
- Lacks narrative context
- Missing descriptive text
- No natural language queries map well to raw table data

**Solution**: LLM-based enhancement that:
1. **Narrative Expansion**: Converts tables into descriptive text explaining patterns, relationships, and context
2. **Q&A Generation**: Creates factual question-answer pairs that improve semantic matching

**How it works** (`src/document_processing/enhancement_processor.py`):
1. DocumentProcessor detects file type (.csv, .xls, .xlsx)
2. Original text is extracted using semantic-friendly formatting
3. EnhancementProcessor sends content to LLM with specialized prompts
4. Enhanced content (narrative + Q&A) is appended to original text
5. Combined text is chunked and embedded as usual
6. Metadata tracks enhancement: `enhanced: bool`, `enhancement_count: int`

**Configuration**:
- `DOC_ENHANCEMENT_ENABLED=true` - Enable/disable feature
- `DOC_ENHANCEMENT_TYPES=narrative,qa` - Choose enhancement types
- `DOC_ENHANCEMENT_MAX_TOKENS=4000` - Control detail level vs cost
- `DOC_ENHANCEMENT_MODEL` - Override LLM model for enhancement

**Example**:

Original CSV:
```
Name,Age,Salary
Alice,25,50000
Bob,30,60000
```

Enhanced content appended:
```
--- Narrative Summary ---
This dataset contains employee information with 2 records showing staff demographics
and compensation. The data includes Alice, a 25-year-old employee earning $50,000
annually, and Bob, a 30-year-old employee earning $60,000 annually. The salary range
spans from $50,000 to $60,000, with an average age of 27.5 years.

--- Q&A Pairs ---
Q: What is Alice's age?
A: Alice is 25 years old.

Q: What is Bob's salary?
A: Bob earns $60,000 annually.

Q: How many employees are in this dataset?
A: There are 2 employees in this dataset.
```

**Benefits**:
- Significantly improves retrieval for queries like "Who earns more than 55k?" or "Average employee age"
- Works automatically - no manual intervention required
- Falls back gracefully if enhancement fails
- Can be disabled per-deployment via configuration

**Cost considerations**:
- Enhancement uses LLM API calls (~$0.01-0.05 per document depending on size/model)
- Only runs once per document during initial ingestion
- Can be disabled for cost-sensitive deployments

### Query Optimization

The system includes an LLM-based query optimizer that transparently improves user queries before RAG retrieval to enhance search accuracy and relevance.

**Problem**: User queries are often:
- Too terse or ambiguous ("vacation days?")
- Missing context from conversation history
- Grammatically incorrect (especially from email)
- Lacking relevant synonyms for semantic search

**Solution**: Transparent query optimization that:
1. **Query Expansion**: Adds relevant synonyms and related terms
2. **Query Rewriting**: Improves clarity, grammar, and sentence structure
3. **Context-Aware Enhancement**: Uses conversation history to resolve ambiguity

**How it works** (`src/rag/query_optimizer.py`):
1. QueryHandler receives user query (from email or web API)
2. QueryOptimizer calls LLM to optimize the query
3. LLM expands, rewrites, and enhances based on conversation context
4. Optimized query is validated (length, format, no hallucinations)
5. RAG engine uses optimized query for retrieval
6. Original query is logged alongside optimized version for analysis

**Configuration**:
- `QUERY_OPTIMIZATION_ENABLED=true` - Enable/disable feature (default: enabled)
- `QUERY_OPTIMIZATION_MODEL` - LLM model to use (default: same as main LLM)
- `QUERY_OPTIMIZATION_MAX_TOKENS=500` - Response token limit
- `QUERY_OPTIMIZATION_TEMPERATURE=0.3` - Low temperature for consistency
- `QUERY_OPTIMIZATION_TIMEOUT=10` - API timeout in seconds

**Example**:

Original query (email): "what policy vacation?"

Optimized query: "What is the company vacation policy?"

Result: Better semantic matching with KB documents about vacation policies.

**Benefits**:
- Improves retrieval accuracy for ambiguous or poorly-worded queries
- Handles typos and grammar issues automatically (especially useful for email)
- Context-aware: resolves follow-up questions using conversation history
- Transparent: users never see the optimization (happens behind the scenes)
- Safe fallback: returns original query if optimization fails

**Performance considerations**:
- Adds ~200-500ms latency per query (LLM API call)
- Cost: ~$0.001-0.005 per query depending on model
- Very short queries (< 3 chars) skip optimization
- Can be disabled per-deployment if latency/cost is a concern

**Integration points**:
- Integrated at `QueryHandler.process_query()` (src/rag/query_handler.py:89)
- Works for both email queries and web API queries
- Optimization is logged for analysis and monitoring

### Query Tracking and Analytics

The system tracks the complete query pipeline (original query → optimized query → sources → answer) and provides detailed analytics in the admin panel.

**What's tracked** (`src/email/db_models.py`, `ConversationMessage` model):

For QUERY messages:
- `original_query` - User's original query text
- `optimized_query` - LLM-optimized query used for retrieval
- `optimization_applied` - Boolean flag (True if query was modified)

For REPLY messages:
- `sources_used` - JSON array of source documents with scores
- `retrieval_metadata` - JSON object with RAG engine metadata

**Database storage** (`src/email/conversation_manager.py`):
- `add_message()` accepts optional parameters: `original_query`, `optimized_query`, `sources_used`, `retrieval_metadata`
- Auto-calculates `optimization_applied` flag (True if queries differ)
- All new fields are nullable for backward compatibility
- `get_message_optimization_details()` - Retrieve optimization data for a message
- `get_message_source_details()` - Retrieve source document data for a message
- `get_optimization_analytics()` - Calculate optimization statistics
- `get_source_analytics()` - Calculate source usage statistics

**Analytics endpoints** (`src/api/api.py`):
- `/api/admin/analytics/optimization` - Query optimization analytics:
  - Total queries, optimized count, optimization rate
  - Average query expansion ratio
  - Sample optimizations showing original vs optimized
- `/api/admin/analytics/sources` - Source document analytics:
  - Total replies, replies with sources
  - Average sources per reply, average relevance score
  - Most cited documents with citation counts

**Admin UI** (`src/api/static/admin.html`, `admin.js`):
- "Query Optimization Analytics" section shows:
  - Optimization rate (% of queries optimized)
  - Average query expansion (% length increase)
  - Sample optimizations with before/after comparison
- "Source Document Usage" section shows:
  - Total replies and replies with sources
  - Average sources per reply
  - Average relevance score
  - Most cited documents table

**Time filtering**:
- All analytics support time range filtering (7 days, 30 days, 90 days, all time)
- Time range buttons control all analytics sections simultaneously

**Use cases**:
- Monitor query optimizer effectiveness
- Identify documents that need improvement (low citation counts)
- Identify over-cited documents (may need splitting or updating)
- Analyze query patterns and optimization trends
- Debug retrieval issues by examining source relevance scores

**Implementation details**:
- Query storage moved to AFTER processing (so optimization metadata is available)
- Both web API (`api.py`) and email processor (`email_processor.py`) store tracking data
- JavaScript methods: `loadOptimizationAnalytics()`, `renderOptimizationAnalytics()`, `loadSourceAnalytics()`, `renderSourceAnalytics()`
- Analytics calculated on-the-fly from database (no pre-aggregation)

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
- `EMAIL_TEACH_ADDRESS` - Dedicated email address for KB ingestion (optional)
- `EMAIL_DISPLAY_NAME` - Display name in emails
- `EMAIL_CHECK_INTERVAL` - Polling frequency (seconds)
- `WELCOME_EMAIL_ENABLED` - Send welcome emails to new users (default: true)

### Whitelist Configuration (Dual Lists)
- **Teaching**: `EMAIL_TEACH_WHITELIST_FILE`, `EMAIL_TEACH_WHITELIST_ENABLED`
- **Query**: `EMAIL_QUERY_WHITELIST_FILE`, `EMAIL_QUERY_WHITELIST_ENABLED`

### RAG Configuration
- `CHUNK_SIZE`, `CHUNK_OVERLAP` - Document chunking parameters
- `TOP_K_RETRIEVAL` - Number of chunks to retrieve
- `SIMILARITY_THRESHOLD` - Minimum similarity score
- `RAG_CUSTOM_PROMPT_FILE` - Custom system prompt additions (optional)

### Document Enhancement Configuration
- `DOC_ENHANCEMENT_ENABLED` - Enable LLM-based enhancement for structured data (default: true)
- `DOC_ENHANCEMENT_MODEL` - Model to use for enhancement (default: same as `OPENROUTER_MODEL`)
- `DOC_ENHANCEMENT_MAX_TOKENS` - Maximum tokens for enhancement (default: 4000)
- `DOC_ENHANCEMENT_TYPES` - Enhancement types: `narrative`, `qa` (default: both)

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
- Publishes to `ghcr.io/gilestrolab/berengar.io`
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
**Solution**: Use `docker-compose run --rm berengario-dev pytest tests/` - local `.venv` may have missing dependencies

**Problem**: Dev container not available for testing
**Solution**: Use `docker-compose run --rm berengario-dev` (auto-starts container) or `docker-compose --profile dev up -d` to start it persistently

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
**Solution**: Initialize database: `docker exec berengario-web berengario-cli db init`

**Problem**: Connection errors with MariaDB
**Solution**: Check `docker-compose logs mariadb` and ensure healthcheck passes before services start

### Email Processing Issues

**Problem**: Emails not being processed
**Solution**:
1. Check whitelist files exist and contain valid entries
2. Verify IMAP credentials with `accessories/test_email_connection.py`
3. Check logs: `docker-compose logs -f berengario-email`

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

**Test Coverage**: Run `docker exec berengario-web pytest tests/ -v` to verify current test status
