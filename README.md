# Berengario

**A configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management.**

Berengario is a flexible infrastructure that combines document processing, vector search, and LLM-powered question answering with unique email integration capabilities. Deploy multiple instances with different configurations for various organizations or departments.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/gilestrolab/berengar.io/workflows/CI/badge.svg)](https://github.com/gilestrolab/berengar.io/actions/workflows/ci.yml)
[![Docker Build](https://github.com/gilestrolab/berengar.io/workflows/Docker%20Build/badge.svg)](https://github.com/gilestrolab/berengar.io/actions/workflows/docker.yml)
[![codecov](https://codecov.io/gh/gilestrolab/berengar.io/branch/master/graph/badge.svg)](https://codecov.io/gh/gilestrolab/berengar.io)

## Features

- **Multi-format Document Processing**: PDF, DOCX, TXT, CSV, XLS, XLSX support
- **Document Enhancement**: LLM-based enhancement for structured data (CSV/Excel) — converts tables to narrative text and generates Q&A pairs for improved RAG retrieval
- **Semantic Search**: ChromaDB vector database for efficient retrieval
- **Query Optimization**: Automatic query rewriting, expansion, and context-aware enhancement for better retrieval accuracy
- **LLM Integration**: OpenAI-compatible API support (OpenAI, Naga.ac, OpenRouter)
- **Function Calling / Tool System**: Calendar event creation, CSV/JSON export, web search, database queries, team management
- **Web Crawling**: Ingest content from URLs directly into the knowledge base
- **Email Integration**:
  - IMAP inbox monitoring with SSL/TLS and STARTTLS
  - Automatic KB updates from CC'd/forwarded emails
  - Automated RAG-powered email replies
  - SMTP email sending with HTML formatting
  - Customizable email format (text, markdown, or HTML)
  - Custom email footers
  - Role-based access control (teach vs query permissions)
  - Configurable forwarded email detection
  - Message tracking and deduplication
- **Web Interface**:
  - Modern chat interface with real-time query processing
  - OTP-based passwordless authentication via email
  - Session management with configurable timeout
  - Source citations and attachment downloads
  - Conversation history persistence
  - Response feedback system (thumbs up/down with comments)
  - Mobile-responsive design
  - Dynamic branding from environment variables
- **Admin Panel**:
  - Team management (queriers, teachers, admins)
  - Document browser with view/download/delete
  - Query optimization analytics (optimization rate, expansion ratio)
  - Source document usage analytics (citation counts, relevance scores)
  - Response feedback analytics
  - Data backup with email notifications
  - Audit logging for all admin actions
  - Role-based access control
- **Instance Configuration**: Deploy multiple customized instances
  - Custom system prompts for AI behavior tuning
  - Instance-specific branding and naming
  - Dynamic frontend customization from .env
- **Multi-Tenancy** (optional): Isolated per-tenant databases, storage, and email routing
- **Auto-monitoring**: Watch folders for automatic document updates
- **Source Citations**: All responses include source references
- **Flexible Storage**: SQLite or MariaDB for tracking; local filesystem or S3/MinIO for documents

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
docker-compose logs -f berengario-web
```

Docker images are automatically built and published to GitHub Container Registry:

```bash
# Pull latest image
docker pull ghcr.io/gilestrolab/berengar.io:latest
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
INSTANCE_NAME=Berengario
INSTANCE_DESCRIPTION=AI assistant for my organization
ORGANIZATION=My Organization

# API Configuration
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1  # or https://api.naga.ac/v1
```

### Usage

#### Web Interface (Recommended)

```bash
# Run web service with Docker Compose
docker-compose up -d

# Access the web interface at http://localhost:8000
# Login with your registered email to receive an OTP code
```

The web interface provides:
- **Authentication**: OTP-based passwordless login via email
- **Chat Interface**: Real-time queries with source citations
- **Conversation History**: Persistent session management
- **Attachments**: Download generated files (calendar events, CSV exports, etc.)
- **Feedback**: Rate responses with thumbs up/down and comments
- **Dynamic Branding**: Instance name and description from .env
- **Admin Panel**: Team, document, analytics, and backup management (for admin users)

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
   - Multi-format parser (PDF, DOCX, TXT, CSV, XLS, XLSX)
   - LLM-based enhancement for structured data (CSV/Excel)
   - Intelligent chunking with overlap
   - Web crawling for URL ingestion
   - File monitoring for auto-updates

2. **Knowledge Base** (`src/document_processing/kb_manager.py`)
   - ChromaDB vector storage
   - Deduplication via file hashing
   - Efficient semantic search

3. **RAG Engine** (`src/rag/`)
   - LlamaIndex query engine with customizable prompts
   - Query optimization (expansion, rewriting, context-aware enhancement)
   - Function calling / tool system (calendar, export, web search, database, team management)
   - Source citation

4. **Email Integration** (`src/email/`)
   - IMAP client with SSL/TLS and STARTTLS support
   - SMTP email sender with TLS encryption
   - Email parser with HTML-to-text conversion
   - Role-based access control with TenantUser lookup
   - Attachment handler with file type validation
   - Conversation manager with Q&A tracking
   - Message tracking (SQLite/MariaDB)
   - Email service daemon with auto-reconnection
   - Tenant email routing (multi-tenancy)

5. **Web API** (`src/api/`)
   - FastAPI REST endpoints organized into modular routes
   - OTP-based authentication system with session management
   - Admin panel with analytics dashboard
   - Response feedback collection
   - Tenant onboarding flow (multi-tenancy)

6. **Platform Layer** (`src/platform/`) — Multi-tenancy
   - Tenant provisioning and lifecycle management
   - Per-tenant database isolation (TenantDBManager)
   - Storage abstraction (local filesystem or S3/MinIO)
   - Envelope encryption (master key encrypts per-tenant keys)
   - Component factory and resolver for DI

7. **CLI** (`src/cli/`)
   - Unified administration tool (Typer + Rich)
   - Knowledge base, database, and backup commands

### Tech Stack

- **Python 3.11+**
- **LlamaIndex**: RAG framework
- **ChromaDB**: Vector database
- **FastAPI**: Web API and authentication
- **Uvicorn**: ASGI web server
- **SQLAlchemy**: Database ORM (SQLite/MariaDB)
- **Typer + Rich**: CLI framework
- **OpenAI-compatible APIs**: Naga.ac, OpenAI, OpenRouter

## Configuration Options

### Instance Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `INSTANCE_NAME` | Name of your assistant | `Berengario` |
| `INSTANCE_DESCRIPTION` | Purpose description | `AI assistant for...` |
| `ORGANIZATION` | Organization name | `My Organization` |
| `WEB_BASE_URL` | Base URL for web interface | `http://localhost:8000` |

### API Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | API key for embeddings | Required |
| `OPENAI_API_BASE` | Embedding API endpoint URL | `https://api.openai.com/v1` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENROUTER_API_KEY` | API key for LLM queries | Required |
| `OPENROUTER_API_BASE` | LLM API endpoint URL | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | LLM model name | `anthropic/claude-3.5-sonnet` |

### Document Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCUMENTS_PATH` | Path to documents folder | `data/kb/documents` |
| `KB_DOCUMENTS_PATH` | KB documents storage | `data/kb/documents` |
| `KB_EMAILS_PATH` | KB email content storage | `data/kb/emails` |
| `CHROMA_DB_PATH` | Vector database path | `data/chroma_db` |
| `CHUNK_SIZE` | Text chunk size | `1024` |
| `CHUNK_OVERLAP` | Chunk overlap | `200` |
| `TOP_K_RETRIEVAL` | Number of chunks to retrieve | `5` |
| `SIMILARITY_THRESHOLD` | Minimum similarity score | `0.7` |

### Document Enhancement Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOC_ENHANCEMENT_ENABLED` | Enable LLM enhancement for CSV/Excel | `true` |
| `DOC_ENHANCEMENT_MODEL` | Model for enhancement | Same as `OPENROUTER_MODEL` |
| `DOC_ENHANCEMENT_MAX_TOKENS` | Max tokens for enhancement | `4000` |
| `DOC_ENHANCEMENT_TYPES` | Enhancement types: `narrative`, `qa` | `narrative,qa` |

### Query Optimization Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `QUERY_OPTIMIZATION_ENABLED` | Enable automatic query optimization | `true` |
| `QUERY_OPTIMIZATION_MODEL` | Model for optimization | Same as `OPENROUTER_MODEL` |
| `QUERY_OPTIMIZATION_MAX_TOKENS` | Max tokens for optimization | `500` |
| `QUERY_OPTIMIZATION_TEMPERATURE` | Temperature (lower = more consistent) | `0.3` |
| `QUERY_OPTIMIZATION_TIMEOUT` | API timeout in seconds | `10` |

### Email Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `EMAIL_TARGET_ADDRESS` | Bot's email address | Required |
| `EMAIL_DISPLAY_NAME` | Bot's display name in emails | `Berengario` |
| `IMAP_SERVER` | IMAP server address | Required |
| `IMAP_PORT` | IMAP port (993 SSL, 143 STARTTLS) | `993` |
| `SMTP_SERVER` | SMTP server address | Required |
| `SMTP_PORT` | SMTP port (587 STARTTLS, 465 SSL) | `587` |
| `SMTP_USER` | SMTP username | Same as IMAP user |
| `SMTP_PASSWORD` | SMTP password | Required |
| `SMTP_USE_TLS` | Use STARTTLS encryption | `true` |
| `EMAIL_CHECK_INTERVAL` | Polling frequency in seconds | `300` |
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
| `API_HOST` | Web server host | `0.0.0.0` |
| `API_PORT` | Web server port | `8000` |

**Authentication:** Web interface uses OTP-based passwordless authentication. Users must have a TenantUser account with query permissions to access the web interface.

### RAG Customization

| Variable | Description | Default |
|----------|-------------|---------|
| `RAG_CUSTOM_PROMPT_FILE` | Custom system prompt additions (optional) | None |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `LOG_FILE` | Log file path | `data/logs/berengario.log` |

See [`.env.example`](.env.example) for complete configuration options including multi-tenancy settings.

## Development

### Project Structure

```
RAGInbox/
├── .github/
│   └── workflows/                        # CI/CD pipelines
│       ├── ci.yml                        # Testing and linting
│       ├── docker.yml                    # Docker build and publish
│       └── release.yml                   # Release automation
├── src/
│   ├── config.py                         # Pydantic Settings configuration
│   ├── document_processing/
│   │   ├── document_processor.py         # Multi-format parser (PDF, DOCX, TXT, CSV, XLS, XLSX)
│   │   ├── enhancement_processor.py      # LLM enhancement for structured data
│   │   ├── kb_manager.py                 # ChromaDB vector storage
│   │   ├── file_watcher.py               # File monitoring for auto-updates
│   │   ├── description_generator.py      # Auto-generate document descriptions
│   │   └── web_crawler.py                # URL content ingestion
│   ├── rag/
│   │   ├── rag_engine.py                 # LlamaIndex query engine
│   │   ├── query_handler.py              # High-level query processing
│   │   ├── query_optimizer.py            # LLM-based query optimization
│   │   ├── example_questions.py          # Example question generation
│   │   ├── topic_clustering.py           # Topic clustering
│   │   └── tools/                        # Function calling system
│   │       ├── base.py                   # Tool registry and base classes
│   │       ├── tool_executor.py          # Tool execution engine
│   │       ├── context.py                # Execution context management
│   │       ├── pending_actions.py        # Pending action tracking
│   │       ├── calendar_tools.py         # Calendar event creation (.ics)
│   │       ├── export_tools.py           # CSV, JSON, text file export
│   │       ├── web_search_tools.py       # Web search via DuckDuckGo
│   │       ├── rag_tools.py              # Knowledge base search
│   │       ├── database_tools.py         # Conversation history and analytics queries
│   │       └── team_tools.py             # Team management (admin only)
│   ├── email/
│   │   ├── email_client.py               # IMAP client (SSL/TLS, STARTTLS)
│   │   ├── email_parser.py               # Header/body parsing, forwarding detection
│   │   ├── email_sender.py               # SMTP sending (HTML/Markdown/Text)
│   │   ├── attachment_handler.py          # Attachment extraction and validation
│   │   ├── email_processor.py            # Pipeline orchestration
│   │   ├── email_service.py              # Background daemon with auto-reconnection
│   │   ├── conversation_manager.py       # Message history with Q&A tracking
│   │   ├── message_tracker.py            # Deduplication tracking
│   │   ├── db_manager.py                 # Database abstraction (SQLite/MariaDB)
│   │   ├── db_models.py                  # SQLAlchemy models
│   │   └── tenant_email_router.py        # Multi-tenant email routing
│   ├── api/
│   │   ├── api.py                        # FastAPI app initialization
│   │   ├── models.py                     # Request/response models
│   │   ├── auth/                         # Authentication
│   │   │   ├── dependencies.py           # FastAPI dependency injection
│   │   │   ├── otp_manager.py            # One-time password handling
│   │   │   └── session_manager.py        # Session management
│   │   ├── admin/                        # Admin panel utilities
│   │   │   ├── document_manager.py       # Document management
│   │   │   ├── backup_manager.py         # Data backup
│   │   │   └── audit_logger.py           # Admin audit logging
│   │   ├── routes/                       # API endpoint routes
│   │   │   ├── auth.py                   # Authentication endpoints
│   │   │   ├── query.py                  # Query/RAG endpoints
│   │   │   ├── conversations.py          # Conversation history
│   │   │   ├── admin.py                  # Admin endpoints
│   │   │   ├── analytics.py              # Analytics dashboard
│   │   │   ├── feedback.py               # Response feedback
│   │   │   ├── onboarding.py             # Tenant onboarding flow
│   │   │   ├── team.py                   # Team management (MT)
│   │   │   └── tenant_admin.py           # Tenant admin (MT)
│   │   └── static/                       # Frontend files
│   │       ├── index.html                # Chat interface
│   │       ├── app.js                    # Chat app logic
│   │       ├── login.html / login.js     # Login page
│   │       ├── verify.html / verify.js   # OTP verification
│   │       ├── admin.html / admin.js     # Admin panel
│   │       ├── admin-usage.js            # Usage analytics
│   │       ├── admin-feedback.js         # Feedback analytics
│   │       ├── feedback.html / feedback.js # Feedback interface
│   │       ├── onboarding.html / onboarding.js # Tenant onboarding
│   │       ├── style.css                 # Chat styles
│   │       └── auth.css                  # Authentication styles
│   ├── platform/                         # Multi-tenancy platform layer
│   │   ├── models.py                     # Tenant, TenantUser, TenantEncryptionKey models
│   │   ├── tenant_context.py             # TenantContext configuration bundle
│   │   ├── db_manager.py                 # Per-tenant database engine management
│   │   ├── storage.py                    # Storage backend ABC (Local/S3)
│   │   ├── encryption.py                 # Envelope encryption (MEK/TEK)
│   │   ├── provisioning.py               # Tenant provisioning with rollback
│   │   ├── component_factory.py          # Per-tenant component creation
│   │   ├── component_resolver.py         # ST/MT routing bridge
│   │   └── db_session_adapter.py         # Database session adapter
│   └── cli/
│       ├── main.py                       # CLI entry point (Typer)
│       ├── utils.py                      # CLI utilities (Rich formatting)
│       └── commands/                     # CLI command implementations
│           ├── kb.py                     # Knowledge base commands
│           ├── db.py                     # Database commands
│           └── backup.py                 # Backup commands
├── tests/                                # Pytest test suite
├── data/                                 # All persistent data (Docker volumes)
│   ├── kb/                               # Knowledge base storage
│   │   ├── documents/                    # Source documents (watched folder)
│   │   ├── emails/                       # Email-ingested content
│   │   └── archive/                      # Archived documents
│   ├── chroma_db/                        # Vector database storage
│   ├── config/                           # Configuration files
│   │   ├── custom_prompt.txt             # Custom system prompt (optional)
│   │   └── email_footer.txt              # Custom email footer (optional)
│   ├── logs/                             # Application logs
│   │   ├── berengario.log                # Main log file
│   │   └── admin_audit.log               # Admin actions audit log
│   ├── backups/                          # Data backups (ZIP files)
│   ├── temp_attachments/                 # Temporary email attachments
│   ├── tenants/                          # Per-tenant data (multi-tenancy)
│   └── message_tracker.db                # Email processing tracking (SQLite)
├── docs/                                 # Documentation
│   ├── QUICKSTART.md                     # Quick start guide
│   ├── CLI.md                            # CLI usage documentation
│   ├── DATA_STRUCTURE.md                 # Data directory structure
│   ├── DATABASE_DESIGN.md                # Database schema
│   ├── EMAIL_PROCESSING_RULES.md         # Email processing logic
│   ├── MULTI_TENANCY.md                  # Multi-tenancy deployment guide
│   ├── PRE_COMMIT_HOOK.md                # Pre-commit hook documentation
│   └── EMAIL_AUTH_ISSUE.md               # Office 365 auth troubleshooting
├── Dockerfile                            # Multi-stage build (production + dev)
├── docker-compose.yml                    # Docker Compose configuration
├── pyproject.toml                        # Package configuration
├── .env.example                          # Environment configuration template
├── PLANNING.md                           # Architecture documentation
└── README.md                             # This file
```

### Email Integration

Berengario includes comprehensive email integration for automatic knowledge base updates and intelligent email replies:

**How it works:**
- **Direct emails** (To: bot) → RAG-powered query processing + automated reply
- **CC/BCC emails** → Silent KB ingestion
- **Forwarded emails** (Fw:, Fwd:) → KB ingestion (configurable)
- **Teach address emails** (To/CC: teach address) → KB ingestion (optional dedicated address)

**Security (Role-Based Access Control):**
- **Separate permissions** for teaching (KB ingestion) vs querying
- TenantUser lookup determines who can add content via CC/BCC/forwarding
- TenantUser lookup determines who can ask questions and get RAG replies
- Users can have one role, multiple roles, or none
- Support for domain wildcards (`@example.com`)
- Database-backed configuration via team management

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
- Attachment processing (PDF, DOCX, TXT, CSV, XLS, XLSX)
- Email body processing when no attachments
- Message tracking and deduplication
- Background service daemon with auto-reconnection

See [`docs/EMAIL_PROCESSING_RULES.md`](docs/EMAIL_PROCESSING_RULES.md) for detailed processing logic and configuration.

### Web Authentication

Berengario's web interface uses OTP-based passwordless authentication for secure access:

**How it works:**
1. User enters their email address on the login page
2. System validates email via TenantUser lookup for query permissions
3. If authorized, generates a 6-digit one-time code
4. Sends OTP code via email using your configured SMTP settings
5. User enters the code to authenticate and access the chat interface

**Security Features:**
- **Access Validation**: Only users with a TenantUser account and query permissions can access the web interface
- **OTP Expiry**: Codes expire after 5 minutes
- **Attempt Limiting**: Maximum 5 verification attempts per code
- **Session Management**: Configurable timeout (default 24 hours via `WEB_SESSION_TIMEOUT`)
- **Secure Cookies**: HTTP-only cookies for session management
- **No Password Storage**: Completely passwordless system

**Configuration:**
```bash
# .env
WEB_SESSION_TIMEOUT=86400  # Session timeout in seconds (24 hours)
```

Users must have a TenantUser account with query permissions to receive OTP codes. Manage users via the admin panel's team management interface. The system uses your existing SMTP configuration for sending authentication emails.

### Admin Panel

Berengario includes a comprehensive admin panel for managing your instance:

**Access:** Users with the admin role will see an admin button after logging in to the web interface.

**Features:**

1. **Team Management**
   - Add/remove users with query, teacher, and admin roles
   - Support for email addresses and domain wildcards
   - Real-time access control updates without service restart

2. **Document Management**
   - Browse all documents in the knowledge base
   - View email content that was ingested
   - Download original document files (PDF, DOCX, etc.)
   - Delete documents from the knowledge base
   - See document metadata (type, source, hash)

3. **Analytics Dashboard**
   - Query optimization analytics (optimization rate, average expansion ratio, before/after samples)
   - Source document usage analytics (citation counts, average relevance scores)
   - Response feedback analytics (satisfaction rates, comment analysis)
   - Time range filtering (7 days, 30 days, 90 days, all time)

4. **Data Backup**
   - Create full backups of the data directory
   - Backups created asynchronously (non-blocking)
   - Email notification with download link when complete
   - List and download previous backups
   - Automatic cleanup (keeps last 5, deletes older than 7 days)
   - Backup files named with instance: `berengario_backup_YYYYMMDD_HHMMSS.zip`

5. **Audit Logging**
   - All admin actions logged to `data/logs/admin_audit.log`
   - Includes user, action, timestamp, and outcome
   - Helps track changes and troubleshoot issues

**Configuration:**
```bash
# .env
WEB_BASE_URL=http://localhost:8000  # Used in backup notification emails
```

Admin access is managed via TenantUser roles in the team management interface.

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
   This response was generated by Berengario, your AI assistant.

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

All tests should be run inside the Docker dev container to ensure a consistent environment:

```bash
# Run all tests (auto-starts dev container)
docker-compose run --rm berengario-dev pytest tests/ -v

# Run specific test file
docker-compose run --rm berengario-dev pytest tests/test_email_parser.py -v

# Run tests matching a pattern
docker-compose run --rm berengario-dev pytest tests/ -v -k "email"

# Run with coverage report
docker-compose run --rm berengario-dev pytest tests/ -v --cov=src --cov-report=term-missing
```

See the project's [CLAUDE.md](.claude/CLAUDE.md) for full Docker testing workflow details.

### Code Quality

Berengario includes a pre-commit hook that automatically runs before each commit:

1. **Black** - Code formatting
2. **Ruff** - Linting
3. **Pytest** - Full test suite in Docker

```bash
# Format with Black
docker-compose run --rm berengario-dev black src/ tests/

# Lint with Ruff
docker-compose run --rm berengario-dev ruff check src/ tests/ --fix

# Or use local tools if installed
black src/ tests/
ruff check src/ tests/
```

See [`docs/PRE_COMMIT_HOOK.md`](docs/PRE_COMMIT_HOOK.md) for pre-commit hook documentation.

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

- [x] **Phase 1**: Core RAG with document processing
- [x] **Phase 2**: Email inbox integration (IMAP, parsing, attachments, tracking)
- [x] **Phase 3**: Email query handler (SMTP, RAG replies, HTML formatting)
- [x] **Phase 4**: Web frontend (authentication, chat, admin, analytics, feedback)
- [x] **Phase 5**: Docker deployment and CI/CD
- [x] **Phase 6**: Multi-tenancy (per-tenant isolation, S3 storage, encryption, team management)

## Multi-Tenancy

Berengario can run in multi-tenant mode, serving multiple organizations from a single deployment with fully isolated data. Each tenant gets its own database, document storage, ChromaDB collection, and email routing.

Key capabilities:
- **Isolated tenants** — separate databases, document stores, and ChromaDB per tenant
- **Storage backends** — local filesystem (default) or S3/MinIO for object storage
- **Encryption** — optional per-tenant envelope encryption with a master key
- **Team management** — invite codes, join requests, and role-based access (owner, admin, member)
- **Email routing** — automatic per-tenant email address mapping

Minimal configuration to enable:

```env
MULTI_TENANT=true
PLATFORM_DB_HOST=mariadb
PLATFORM_DB_PASSWORD=your_password
```

See [`docs/MULTI_TENANCY.md`](docs/MULTI_TENANCY.md) for the full deployment guide.

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
- **[CLI.md](docs/CLI.md)** - CLI administration tool documentation
- **[DATA_STRUCTURE.md](docs/DATA_STRUCTURE.md)** - Data directory structure and Docker volumes
- **[EMAIL_PROCESSING_RULES.md](docs/EMAIL_PROCESSING_RULES.md)** - Email processing logic and decision tree
- **[DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md)** - Database abstraction layer (SQLite/MariaDB)
- **[MULTI_TENANCY.md](docs/MULTI_TENANCY.md)** - Multi-tenancy deployment guide
- **[PRE_COMMIT_HOOK.md](docs/PRE_COMMIT_HOOK.md)** - Pre-commit hook setup and troubleshooting
- **[EMAIL_AUTH_ISSUE.md](docs/EMAIL_AUTH_ISSUE.md)** - Office 365 authentication troubleshooting

## Support

- [Documentation](docs/)
- [Issue Tracker](https://github.com/gilestrolab/berengar.io/issues)
- [Discussions](https://github.com/gilestrolab/berengar.io/discussions)

## Credits

Developed by [Giorgio Gilestro](https://github.com/gilestrolab) for flexible, email-integrated RAG deployments.
