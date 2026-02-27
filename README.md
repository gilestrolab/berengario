# Berengario

**A configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management.**

Berengario is a flexible infrastructure that combines document processing, vector search, and LLM-powered question answering with unique email integration capabilities. Deploy multiple instances with different configurations for various organizations or departments.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/gilestrolab/berengar.io/workflows/CI/badge.svg)](https://github.com/gilestrolab/berengar.io/actions/workflows/ci.yml)
[![Docker Build](https://github.com/gilestrolab/berengar.io/workflows/Docker%20Build/badge.svg)](https://github.com/gilestrolab/berengar.io/actions/workflows/docker.yml)
[![codecov](https://codecov.io/gh/gilestrolab/berengar.io/branch/master/graph/badge.svg)](https://codecov.io/gh/gilestrolab/berengar.io)

## Features

- 📄 **Multi-format Document Processing**: PDF, DOCX, TXT, CSV support
- 🔍 **Semantic Search**: ChromaDB vector database for efficient retrieval
- 🤖 **LLM Integration**: OpenAI-compatible API support (OpenAI, Naga.ac, etc.)
- 📧 **Email Integration**:
  - IMAP inbox monitoring with SSL/TLS
  - Automatic KB updates from CC'd/forwarded emails
  - Automated RAG-powered email replies
  - SMTP email sending with HTML formatting
  - Customizable email format (text, markdown, or HTML)
  - Custom email footers
  - Email whitelist for security
  - Configurable forwarded email detection
  - Message tracking and deduplication
- 🌐 **Web Interface**:
  - Modern chat interface with real-time query processing
  - OTP-based passwordless authentication via email
  - Session management with configurable timeout
  - Source citations and attachment downloads
  - Conversation history persistence
  - Mobile-responsive design
  - Dynamic branding from environment variables
- 🔧 **Admin Panel**:
  - Whitelist management (queriers, teachers, admins)
  - Document browser with view/download/delete
  - Data backup with email notifications
  - Audit logging for all admin actions
  - Role-based access control
- ⚙️ **Instance Configuration**: Deploy multiple customized instances
  - Custom system prompts for AI behavior tuning
  - Instance-specific branding and naming
  - Dynamic frontend customization from .env
- 🔄 **Auto-monitoring**: Watch folders for automatic document updates
- 📊 **Source Citations**: All responses include source references
- 🗄️ **Flexible Storage**: SQLite or MariaDB for email tracking

## Quick Start

### Installation

#### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/gilestrolab/berengar.io.git
cd RAGInbox

# Copy and configure environment
cp .env.example .env
# Edit .env with your configuration

# Start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f berengario
```

Docker images are automatically built and published to GitHub Container Registry:

```bash
# Pull latest image
docker pull ghcr.io/gilestrolab/berengar.io:latest

# Run with docker
docker run -d \
  --name berengario \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/gilestrolab/berengar.io:latest
```

#### Option 2: Local Installation

```bash
# Clone the repository
git clone https://github.com/gilestrolab/berengar.io.git
cd RAGInbox

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in editable mode
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and configure your instance:

```bash
# Instance Configuration (customize for your deployment)
INSTANCE_NAME=MyAssistant
INSTANCE_DESCRIPTION=AI assistant for my organization
ORGANIZATION=My Organization Name

# API Configuration
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1  # or https://api.naga.ac/v1
```

### Usage

#### Web Interface (Recommended)

```bash
# Run web service with Docker Compose
docker-compose -f docker-compose.mariadb.yml up -d

# Access the web interface at http://localhost:8000
# Login with your whitelisted email to receive an OTP code
```

The web interface provides:
- **Authentication**: OTP-based passwordless login via email
- **Chat Interface**: Real-time queries with source citations
- **Conversation History**: Persistent session management
- **Attachments**: Download generated files (calendar events, etc.)
- **Dynamic Branding**: Instance name and description from .env
- **Admin Panel**: Whitelist and document management (for admin users)

#### CLI Administration Tool

Berengario includes a unified CLI for administration and management (Docker-only):

```bash
# Basic usage
docker exec berengario-web berengario-cli [COMMAND] [OPTIONS]

# Get help
docker exec berengario-web berengario-cli help
docker exec berengario-web berengario-cli --help

# Knowledge Base operations
docker exec berengario-web berengario-cli kb list              # List all documents in the KB
docker exec berengario-web berengario-cli kb stats             # Show KB statistics
docker exec berengario-web berengario-cli kb reingest          # Reingest all documents
docker exec berengario-web berengario-cli kb delete <hash>     # Delete a specific document
docker exec berengario-web berengario-cli kb clear             # Clear entire KB (confirmation required)

# Database operations
docker exec berengario-web berengario-cli db init              # Initialize database tables
docker exec berengario-web berengario-cli db test              # Test database connection
docker exec berengario-web berengario-cli db info              # Show database configuration
docker exec berengario-web berengario-cli db stats             # Show processing statistics

# Backup operations
docker exec berengario-web berengario-cli backup create        # Create a new backup
docker exec berengario-web berengario-cli backup list          # List available backups
docker exec berengario-web berengario-cli backup delete <file> # Delete a specific backup
docker exec berengario-web berengario-cli backup cleanup       # Clean up old backups

# System information
docker exec berengario-web berengario-cli version              # Show version and instance info
docker exec berengario-web berengario-cli info                 # Show detailed configuration
```

**Features:**
- Colorized output with progress bars
- Interactive confirmations for destructive operations
- Pretty-printed tables for list commands
- Comprehensive help text (`berengario-cli help` or `berengario-cli <command> --help`)
- Replaces scripts folder with unified interface

**Tip:** For easier access, you can create a shell alias:
```bash
alias berengario="docker exec berengario-web berengario-cli"
# Then use: berengario kb list, berengario db stats, etc.
```

See [`docs/CLI.md`](docs/CLI.md) for complete CLI documentation.

#### Running Services

```bash
# Run email service (monitors inbox for KB updates and queries)
python run_email_service.py

# Run web service (chat interface with authentication)
python run_web_service.py

# Or use Docker Compose to run everything
docker-compose up -d
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for detailed setup instructions.

## Architecture

### Core Components

1. **Document Processing** (`src/document_processing/`)
   - Multi-format parser (PDF, DOCX, TXT, CSV)
   - Intelligent chunking with overlap
   - File monitoring for auto-updates

2. **Knowledge Base** (`src/document_processing/kb_manager.py`)
   - ChromaDB vector storage
   - Deduplication via file hashing
   - Efficient semantic search

3. **RAG Engine** (`src/rag/`)
   - LlamaIndex query engine
   - Customizable prompts per instance
   - Source citation

4. **Email Integration** (`src/email/`)
   - IMAP client with SSL/TLS and STARTTLS support
   - SMTP email sender with TLS encryption
   - Email parser with HTML-to-text conversion
   - Whitelist validation with domain wildcards
   - Attachment handler with file type validation
   - Message tracking (SQLite/MariaDB)
   - Email service daemon with auto-reconnection
   - Automated RAG-powered query responses
   - Professional HTML + plain text email formatting
   - Email threading support (In-Reply-To, References headers)
   - Configurable forwarded email detection
   - Processing rules: Direct emails → RAG Query + Reply, CC/BCC/Forwarded → KB ingestion

5. **Web API** (`src/api/`)
   - FastAPI REST endpoints for queries and configuration
   - OTP-based authentication system
   - Session management with configurable timeout
   - Cookie-based authentication
   - Protected routes with authentication middleware
   - Real-time query processing
   - Conversation history management
   - Attachment handling and downloads
   - Modern chat interface with responsive design
   - Admin panel with role-based access control
   - Whitelist management (queriers, teachers, admins)
   - Document browser with view/download/delete
   - Data backup with email notifications
   - Audit logging for admin actions

### Tech Stack

- **Python 3.11+**
- **LlamaIndex**: RAG framework
- **ChromaDB**: Vector database
- **FastAPI**: Web API and authentication
- **Uvicorn**: ASGI web server
- **OpenAI-compatible APIs**: Naga.ac, OpenAI, etc.

## Configuration Options

### Instance Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `INSTANCE_NAME` | Name of your assistant | `DoLS-GPT` |
| `INSTANCE_DESCRIPTION` | Purpose description | `AI assistant for...` |
| `ORGANIZATION` | Organization name | `Imperial College` |
| `WEB_BASE_URL` | Base URL for web interface | `http://localhost:8000` |

### API Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | API key for LLM/embeddings | Required |
| `OPENAI_API_BASE` | API endpoint URL | `https://api.openai.com/v1` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENROUTER_MODEL` | LLM model name | `anthropic/claude-3.5-sonnet` |

### Document Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCUMENTS_PATH` | Path to documents folder | `data/documents` |
| `CHUNK_SIZE` | Text chunk size | `1024` |
| `CHUNK_OVERLAP` | Chunk overlap | `200` |
| `TOP_K_RETRIEVAL` | Number of chunks to retrieve | `5` |

### Email Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `EMAIL_TARGET_ADDRESS` | Bot's email address | Required |
| `EMAIL_DISPLAY_NAME` | Bot's display name in emails | Required |
| `IMAP_SERVER` | IMAP server address | `imap.gmail.com` |
| `IMAP_PORT` | IMAP port (993 SSL, 143 STARTTLS) | `993` |
| `SMTP_SERVER` | SMTP server address | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port (587 STARTTLS, 465 SSL) | `587` |
| `SMTP_USER` | SMTP username | Same as email address |
| `SMTP_PASSWORD` | SMTP password | Required |
| `SMTP_USE_TLS` | Use STARTTLS encryption | `true` |
| `EMAIL_TEACH_WHITELIST_FILE` | Who can add to KB (teach) | `data/config/allowed_teachers.txt` |
| `EMAIL_TEACH_WHITELIST_ENABLED` | Enable teaching whitelist | `true` |
| `EMAIL_QUERY_WHITELIST_FILE` | Who can query KB | `data/config/allowed_queriers.txt` |
| `EMAIL_QUERY_WHITELIST_ENABLED` | Enable query whitelist | `true` |
| `EMAIL_ADMIN_WHITELIST_FILE` | Admin panel access | `data/config/allowed_admins.txt` |
| `EMAIL_ADMIN_WHITELIST_ENABLED` | Enable admin whitelist | `true` |
| `FORWARD_TO_KB_ENABLED` | Treat forwarded emails as KB content | `true` |
| `FORWARD_SUBJECT_PREFIXES` | Forwarding prefixes (e.g., fw,fwd) | `fw,fwd` |

### Email Response Customization

| Variable | Description | Default |
|----------|-------------|---------|
| `EMAIL_RESPONSE_FORMAT` | Email format: `text`, `markdown`, or `html` | `html` |
| `EMAIL_CUSTOM_FOOTER_FILE` | Custom footer text file (optional) | None |

### Web Interface Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_SESSION_TIMEOUT` | Session timeout in seconds | `86400` (24 hours) |
| `WEB_HOST` | Web server host | `0.0.0.0` |
| `WEB_PORT` | Web server port | `8000` |

**Authentication:** Web interface uses OTP-based passwordless authentication. Users must be whitelisted in `EMAIL_QUERY_WHITELIST_FILE` to access the web interface.

### RAG Customization

| Variable | Description | Default |
|----------|-------------|---------|
| `RAG_CUSTOM_PROMPT_FILE` | Custom system prompt additions (optional) | None |

See [`.env.example`](.env.example) for complete configuration options.

## Development

### Project Structure

```
RAGInbox/
├── .github/
│   └── workflows/                 # CI/CD pipelines
│       ├── ci.yml                 # Testing and linting
│       ├── docker.yml             # Docker build and publish
│       └── release.yml            # Release automation
├── src/
│   ├── config.py                  # Configuration management
│   ├── demo_phase1.py            # CLI interface
│   ├── document_processing/
│   │   ├── document_processor.py # Document parsing
│   │   ├── kb_manager.py         # Vector DB operations
│   │   └── file_watcher.py       # File monitoring
│   ├── rag/
│   │   ├── rag_engine.py         # Query engine
│   │   └── query_handler.py      # Query processing
│   ├── email/                     # Email integration (Phase 2 & 3)
│   │   ├── email_client.py        # IMAP inbox monitoring
│   │   ├── email_sender.py        # SMTP email sending
│   │   ├── email_parser.py        # Email parsing
│   │   └── ...
│   └── api/                        # Web interface (Phase 4)
│       ├── api.py                  # FastAPI endpoints
│       ├── admin/                  # Admin panel modules
│       │   ├── whitelist_manager.py # Whitelist management
│       │   ├── document_manager.py  # Document management
│       │   ├── backup_manager.py    # Data backup
│       │   └── audit_logger.py      # Admin audit logging
│       └── static/                 # Frontend files
│           ├── index.html          # Chat interface
│           ├── login.html          # Login page
│           ├── verify.html         # OTP verification
│           ├── admin.html          # Admin panel
│           ├── app.js              # Chat app logic
│           ├── login.js            # Login logic
│           ├── verify.js           # Verification logic
│           ├── admin.js            # Admin panel logic
│           ├── style.css           # Chat interface styles
│           └── auth.css            # Authentication styles
├── tests/                         # Unit tests
├── data/                          # All persistent data (Docker volumes)
│   ├── documents/                 # Source documents (watched folder)
│   ├── chroma_db/                 # Vector database storage
│   ├── config/                    # Configuration files
│   │   ├── allowed_teachers.txt   # Teaching whitelist
│   │   ├── allowed_queriers.txt   # Query whitelist
│   │   ├── allowed_admins.txt     # Admin whitelist
│   │   ├── custom_prompt.txt      # Custom system prompt (optional)
│   │   └── email_footer.txt       # Custom email footer (optional)
│   ├── logs/                      # Application logs
│   │   ├── dols_gpt.log           # Main log file
│   │   └── admin_audit.log        # Admin actions audit log
│   ├── backups/                   # Data backups (ZIP files)
│   ├── temp_attachments/          # Temporary email attachments
│   └── message_tracker.db         # Email processing tracking
├── docs/                          # Documentation
│   ├── QUICKSTART.md              # Quick start guide
│   ├── DATA_STRUCTURE.md          # Data directory structure
│   ├── EMAIL_PROCESSING_RULES.md  # Email processing logic
│   └── ...                        # See docs/README.md for full list
├── Dockerfile                     # Production container image
├── docker-compose.yml             # Docker Compose configuration
├── .dockerignore                  # Docker build exclusions
├── pyproject.toml                 # Package configuration
├── .env.example                   # Environment configuration template
├── PLANNING.md                    # Architecture documentation
├── TASK.md                        # Task tracking
└── README.md                      # This file
```

### Email Integration

Berengario includes comprehensive email integration for automatic knowledge base updates and intelligent email replies:

**How it works:**
- **Direct emails** (To: bot) → RAG-powered query processing + automated reply
- **CC/BCC emails** → Silent KB ingestion
- **Forwarded emails** (Fw:, Fwd:) → KB ingestion (configurable)

**Security (Dual Whitelists):**
- **Separate permissions** for teaching (KB ingestion) vs querying
- Teaching whitelist (`allowed_teachers.txt`) - who can add content via CC/BCC/forwarding
- Query whitelist (`allowed_queriers.txt`) - who can ask questions and get RAG replies
- Users can be in one list, both lists, or neither
- Support for domain wildcards (`@imperial.ac.uk`)
- File-based configuration for easy management

**Query Response Features:**
- Automated RAG-powered email replies
- Professional HTML + plain text formatting
- **Customizable email format** (text, markdown, or HTML)
- **Custom email footers** for branded signatures
- **Custom system prompts** for AI behavior tuning
- Source citations with relevance scores
- Email threading support (proper conversation grouping)
- Customizable instance branding

**KB Ingestion Features:**
- IMAP inbox monitoring (SSL/TLS and STARTTLS)
- SMTP email sending with TLS encryption
- Attachment processing (PDF, DOCX, TXT, CSV)
- Email body processing when no attachments
- Message tracking and deduplication
- Background service daemon with auto-reconnection

See [`docs/EMAIL_PROCESSING_RULES.md`](docs/EMAIL_PROCESSING_RULES.md) for detailed processing logic and configuration.

### Web Authentication

Berengario's web interface uses OTP-based passwordless authentication for secure access:

**How it works:**
1. User enters their email address on the login page
2. System validates email against query whitelist (`allowed_queriers.txt`)
3. If authorized, generates a 6-digit one-time code
4. Sends OTP code via email using your configured SMTP settings
5. User enters the code to authenticate and access the chat interface

**Security Features:**
- **Whitelist Validation**: Only users in `allowed_queriers.txt` can access the web interface
- **OTP Expiry**: Codes expire after 5 minutes
- **Attempt Limiting**: Maximum 5 verification attempts per code
- **Session Management**: Configurable timeout (default 24 hours via `WEB_SESSION_TIMEOUT`)
- **Secure Cookies**: HTTP-only cookies for session management
- **No Password Storage**: Completely passwordless system

**Configuration:**
```bash
# .env
WEB_SESSION_TIMEOUT=86400  # Session timeout in seconds (24 hours)

# data/config/allowed_queriers.txt
# Add authorized users (one per line)
user@example.com
@example.com  # Domain wildcard for all users at example.com
```

Users must be in the query whitelist to receive OTP codes. The system uses your existing SMTP configuration for sending authentication emails.

### Admin Panel

Berengario includes a comprehensive admin panel for managing your instance:

**Access:** Users in the admin whitelist (`allowed_admins.txt`) will see an admin button after logging in to the web interface.

**Features:**

1. **Whitelist Management**
   - Add/remove users from query, teacher, and admin whitelists
   - Support for email addresses and domain wildcards
   - Real-time whitelist updates without service restart

2. **Document Management**
   - Browse all documents in the knowledge base
   - View email content that was ingested
   - Download original document files (PDF, DOCX, etc.)
   - Delete documents from the knowledge base
   - See document metadata (type, source, hash)

3. **Data Backup**
   - Create full backups of the data directory
   - Backups created asynchronously (non-blocking)
   - Email notification with download link when complete
   - List and download previous backups
   - Automatic cleanup (keeps last 5, deletes older than 7 days)
   - Backup files named with instance: `dols_gpt_backup_YYYYMMDD_HHMMSS.zip`

4. **Audit Logging**
   - All admin actions logged to `data/logs/admin_audit.log`
   - Includes user, action, timestamp, and outcome
   - Helps track changes and troubleshoot issues

**Configuration:**
```bash
# .env
EMAIL_ADMIN_WHITELIST_FILE=data/config/allowed_admins.txt
EMAIL_ADMIN_WHITELIST_ENABLED=true
WEB_BASE_URL=http://localhost:8000  # Used in backup notification emails

# data/config/allowed_admins.txt
admin@example.com
@admin-domain.com  # All users at admin-domain.com
```

### Customization

Berengario supports extensive customization to match your organization's needs:

#### Custom Email Format

Control the format of email responses by setting `EMAIL_RESPONSE_FORMAT`:

```bash
# .env
EMAIL_RESPONSE_FORMAT=html    # Styled HTML (default)
# EMAIL_RESPONSE_FORMAT=markdown  # Markdown syntax in plain text
# EMAIL_RESPONSE_FORMAT=text      # Simple plain text
```

- **html** (default): Professional styled HTML with CSS formatting
- **markdown**: Plain text with markdown syntax (`## Sources`, `**bold**`)
- **text**: Simple plain text with minimal formatting

#### Custom Email Footer

Replace the default email footer with your own branding:

1. Copy the example template:
   ```bash
   cp data/config/email_footer.txt.example data/config/email_footer.txt
   ```

2. Edit `data/config/email_footer.txt` with your custom text:
   ```
   This response was generated by DoLS-GPT, your AI assistant.

   For more information:
   - Documentation: https://example.com/docs
   - Support: support@example.com
   - Office hours: Monday-Friday, 9AM-5PM GMT
   ```

3. Enable in `.env`:
   ```bash
   EMAIL_CUSTOM_FOOTER_FILE=data/config/email_footer.txt
   ```

The footer automatically converts newlines to `<br>` tags in HTML emails.

#### Custom System Prompt

Fine-tune the AI's behavior by appending custom instructions to the base system prompt:

1. Copy the example template:
   ```bash
   cp data/config/custom_prompt.txt.example data/config/custom_prompt.txt
   ```

2. Edit `data/config/custom_prompt.txt` with your custom instructions:
   ```
   Additional instructions:
   - Always use British English spelling
   - Reference specific policy numbers when available
   - Be especially detailed when discussing safety procedures
   - Include links to relevant documentation when possible
   - If a policy has changed recently, mention the effective date
   ```

3. Enable in `.env`:
   ```bash
   RAG_CUSTOM_PROMPT_FILE=data/config/custom_prompt.txt
   ```

Your custom instructions will be appended to the base system prompt, allowing you to customize AI behavior without modifying code.

### Data Directory Structure

All persistent data is stored under `data/` for easy Docker volume mounting. See [`docs/DATA_STRUCTURE.md`](docs/DATA_STRUCTURE.md) for detailed information about:
- Directory layout and purpose
- Docker volume mounting strategies
- Backup and restore procedures
- Storage requirements and monitoring
- Cleanup operations

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_email_parser.py -v       # Email parsing tests
pytest tests/test_email_sender.py -v       # Email sender tests (Phase 3)
pytest tests/test_phase3_integration.py -v # Phase 3 integration tests
pytest tests/test_document_processor.py -v # Document processing tests
pytest tests/test_kb_manager.py -v         # Knowledge base tests

# Current status: 246 of 252 tests passing (Phase 3 complete)
```

### Code Quality

```bash
# Format with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/
```

### CI/CD Pipeline

Berengario uses GitHub Actions for automated testing, building, and deployment:

#### Continuous Integration (`.github/workflows/ci.yml`)

Runs on every push and pull request:

- **Linting**: Black formatting check and Ruff linting
- **Testing**: Pytest on Python 3.11, 3.12, and 3.13
- **Coverage**: Automated code coverage reporting to Codecov
- **Status**: Check the CI badge at the top of this README

```bash
# CI runs these commands automatically:
black --check src/ tests/
ruff check src/ tests/
pytest tests/ -v --cov=src --cov-report=xml
```

#### Docker Build (`.github/workflows/docker.yml`)

Builds and publishes Docker images:

- **On Push to Main**: Builds multi-platform images (amd64, arm64)
- **On Tags**: Publishes versioned releases to GitHub Container Registry
- **Image Testing**: Validates container startup and imports
- **Registry**: `ghcr.io/gilestrolab/berengar.io`

Available tags:
- `latest` - Latest stable build from main branch
- `v1.2.3` - Specific version tags
- `main-abc123` - Branch builds with commit SHA

#### Release Automation (`.github/workflows/release.yml`)

Automated releases when tags are pushed:

- **Changelog Generation**: Automatic from git commits
- **GitHub Releases**: Created with release notes and artifacts
- **Python Package**: Built and ready for PyPI (optional)

To create a release:
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

## Roadmap

- [x] **Phase 1**: Core RAG with document processing ✓
- [x] **Phase 2**: Email inbox integration ✓
  - IMAP client with SSL/TLS support
  - Email parsing and whitelist validation
  - Attachment extraction and KB ingestion
  - Message tracking and deduplication
  - Email service daemon
  - Configurable forwarded email detection
- [x] **Phase 3**: Email query handler (automated replies) ✓
  - SMTP email sender with TLS support
  - RAG-powered query processing
  - Professional HTML + plain text email formatting
  - Source citations in responses
  - Email threading support
  - Integration with EmailProcessor
- [x] **Phase 4**: Web frontend with chat interface ✓
  - FastAPI REST API with authentication
  - OTP-based passwordless authentication via email
  - Modern chat interface with real-time queries
  - Session management with configurable timeout
  - Conversation history persistence
  - Source citations and attachment downloads
  - Mobile-responsive design
  - Dynamic branding from environment variables
  - Admin panel with whitelist and document management
  - Data backup functionality with email notifications
  - Audit logging for administrative actions
- [x] **Phase 5**: Docker deployment and CI/CD ✓
  - Multi-stage Dockerfile for production
  - Docker Compose with optional MariaDB
  - Multi-platform builds (amd64, arm64)
  - GitHub Actions CI/CD pipeline
  - Automated testing and linting
  - Container registry publishing

## API Providers

Berengario works with OpenAI-compatible APIs:

- **[Naga.ac](https://naga.ac)**: Recommended - cheaper, same models
- **[OpenAI](https://openai.com)**: Original provider
- **[OpenRouter](https://openrouter.ai)**: Multi-provider access

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[QUICKSTART.md](docs/QUICKSTART.md)** - Quick start guide
- **[DATA_STRUCTURE.md](docs/DATA_STRUCTURE.md)** - Data directory structure and Docker volumes
- **[EMAIL_PROCESSING_RULES.md](docs/EMAIL_PROCESSING_RULES.md)** - Email processing logic and decision tree
- **[DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md)** - Database abstraction layer (SQLite/MariaDB)
- **[EMAIL_AUTH_ISSUE.md](docs/EMAIL_AUTH_ISSUE.md)** - Office 365 authentication troubleshooting
- **[PHASE2_PLAN.md](docs/PHASE2_PLAN.md)** - Phase 2 implementation architecture

## Support

- 📖 [Documentation](docs/)
- 🐛 [Issue Tracker](https://github.com/gilestrolab/berengar.io/issues)
- 💬 [Discussions](https://github.com/gilestrolab/berengar.io/discussions)

## Credits

Developed by [Giorgio Gilestro](https://github.com/gilestrolab) for flexible, email-integrated RAG deployments.
