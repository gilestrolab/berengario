# RAGInbox

**A configurable RAG (Retrieval-Augmented Generation) system with email integration for knowledge base management.**

RAGInbox is a flexible infrastructure that combines document processing, vector search, and LLM-powered question answering with unique email integration capabilities. Deploy multiple instances with different configurations for various organizations or departments.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 📄 **Multi-format Document Processing**: PDF, DOCX, TXT, CSV support
- 🔍 **Semantic Search**: ChromaDB vector database for efficient retrieval
- 🤖 **LLM Integration**: OpenAI-compatible API support (OpenAI, Naga.ac, etc.)
- 📧 **Email Integration**:
  - IMAP inbox monitoring with SSL/TLS
  - Automatic KB updates from CC'd/forwarded emails
  - Email whitelist for security
  - Configurable forwarded email detection
  - Message tracking and deduplication
- ⚙️ **Instance Configuration**: Deploy multiple customized instances
- 🔄 **Auto-monitoring**: Watch folders for automatic document updates
- 📊 **Source Citations**: All responses include source references
- 🗄️ **Flexible Storage**: SQLite or MariaDB for email tracking

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/gilestrolab/RAGInbox.git
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

```bash
# Process documents from data/documents folder
python src/demo_phase1.py --mode process

# Query the knowledge base
python src/demo_phase1.py --mode query --query "What are the key policies?"

# Watch for new documents (runs continuously)
python src/demo_phase1.py --mode watch

# Run email service (monitors inbox for KB updates)
python run_email_service.py
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
   - Email parser with HTML-to-text conversion
   - Whitelist validation with domain wildcards
   - Attachment handler with file type validation
   - Message tracking (SQLite/MariaDB)
   - Email service daemon with auto-reconnection
   - Configurable forwarded email detection
   - Processing rules: Direct emails → Query, CC/BCC/Forwarded → KB ingestion

### Tech Stack

- **Python 3.11+**
- **LlamaIndex**: RAG framework
- **ChromaDB**: Vector database
- **FastAPI**: Web framework (Phase 4)
- **OpenAI-compatible APIs**: Naga.ac, OpenAI, etc.

## Configuration Options

### Instance Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `INSTANCE_NAME` | Name of your assistant | `DoLS-GPT` |
| `INSTANCE_DESCRIPTION` | Purpose description | `AI assistant for...` |
| `ORGANIZATION` | Organization name | `Imperial College` |

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
| `IMAP_SERVER` | IMAP server address | `imap.gmail.com` |
| `IMAP_PORT` | IMAP port (993 SSL, 143 STARTTLS) | `993` |
| `EMAIL_WHITELIST_FILE` | Path to allowed senders list | `data/config/allowed_senders.txt` |
| `FORWARD_TO_KB_ENABLED` | Treat forwarded emails as KB content | `true` |
| `FORWARD_SUBJECT_PREFIXES` | Forwarding prefixes (e.g., fw,fwd) | `fw,fwd` |

See [`.env.example`](.env.example) for complete configuration options.

## Development

### Project Structure

```
RAGInbox/
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
│   ├── email/ (Phase 2)
│   └── api/ (Phase 4)
├── tests/                         # Unit tests
├── data/                          # All persistent data (Docker volumes)
│   ├── documents/                 # Source documents (watched folder)
│   ├── chroma_db/                 # Vector database storage
│   ├── config/                    # Configuration files
│   │   └── allowed_senders.txt    # Email whitelist
│   ├── logs/                      # Application logs
│   │   └── dols_gpt.log           # Main log file
│   ├── temp_attachments/          # Temporary email attachments
│   └── message_tracker.db         # Email processing tracking
├── docs/                          # Documentation
│   ├── QUICKSTART.md              # Quick start guide
│   ├── DATA_STRUCTURE.md          # Data directory structure
│   ├── EMAIL_PROCESSING_RULES.md  # Email processing logic
│   └── ...                        # See docs/README.md for full list
├── pyproject.toml                 # Package configuration
├── PLANNING.md                    # Architecture documentation
├── TASK.md                        # Task tracking
└── README.md                      # This file
```

### Email Integration

RAGInbox includes comprehensive email integration for automatic knowledge base updates:

**How it works:**
- **Direct emails** (To: bot) → Queries (will trigger RAG replies in Phase 3)
- **CC/BCC emails** → Silent KB ingestion
- **Forwarded emails** (Fw:, Fwd:) → KB ingestion (configurable)

**Security:**
- Whitelist-based sender validation
- Support for domain wildcards (`@imperial.ac.uk`)
- File-based whitelist configuration

**Features:**
- SSL/TLS and STARTTLS support
- Attachment processing (PDF, DOCX, TXT, CSV)
- Email body processing when no attachments
- Message tracking and deduplication
- Background service daemon with auto-reconnection

See [`docs/EMAIL_PROCESSING_RULES.md`](docs/EMAIL_PROCESSING_RULES.md) for detailed processing logic and configuration.

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
pytest tests/test_email_parser.py -v      # Email parsing tests
pytest tests/test_document_processor.py -v # Document processing tests
pytest tests/test_kb_manager.py -v        # Knowledge base tests

# Current status: 220 of 226 tests passing
```

### Code Quality

```bash
# Format with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/
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
- [ ] **Phase 3**: Email query handler (automated replies)
- [ ] **Phase 4**: Web frontend with chat interface
- [ ] **Phase 5**: Docker deployment with docker-compose

## API Providers

RAGInbox works with OpenAI-compatible APIs:

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
- 🐛 [Issue Tracker](https://github.com/gilestrolab/RAGInbox/issues)
- 💬 [Discussions](https://github.com/gilestrolab/RAGInbox/discussions)

## Credits

Developed by [Giorgio Gilestro](https://github.com/gilestrolab) for flexible, email-integrated RAG deployments.
