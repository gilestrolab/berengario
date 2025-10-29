# RAGInbox - Planning Document

## Project Overview

RAGInbox is a configurable RAG (Retrieval-Augmented Generation) infrastructure designed for flexible deployment across different organizations and use cases. It provides automated knowledge base management and query handling through email integration and web interfaces. Multiple instances can be deployed with customized configurations (e.g., DoLS-GPT for Imperial College's Department of Life Sciences, HR-Assistant for corporate HR, etc.).

## Architecture

### Core Components

1. **Document Processing & KB Management**
   - Monitor `/Documents` folder for new files
   - Parse multiple formats: PDF, DOCX, TXT, CSV
   - Chunk documents intelligently using LlamaIndex
   - Generate embeddings and store in ChromaDB
   - Maintain metadata (filename, upload date, document type)

2. **Email-Based KB Ingestion** (Phase 2)
   - IMAP connection to configured inbox
   - Process CC'd/BCC'd/forwarded emails as KB content
   - Extract email body and attachments
   - Process attachments as documents
   - Mark processed emails to prevent duplicates
   - Whitelist validation for security

3. **Email Query Handler** (Phase 3)
   - Monitor direct emails (To: bot account) as queries
   - Extract query from email body
   - Query RAG system with context retrieval
   - Generate instance-specific LLM responses
   - Send reply via SMTP
   - Log all interactions

4. **Web Frontend**
   - Simple FastAPI-based interface
   - No authentication required
   - Cookie-based session management
   - Chat interface with history
   - Source citations

### Technology Stack

- **Language**: Python 3.11+
- **RAG Framework**: LlamaIndex
- **Vector Database**: ChromaDB (persistent storage)
- **Email**: IMAP (imaplib/imap-tools) + SMTP
- **LLM**: OpenAI API (configurable)
- **Web Framework**: FastAPI
- **Frontend**: HTML/CSS/JavaScript (vanilla)
- **Data Validation**: Pydantic
- **Environment Management**: python-dotenv
- **Deployment**: Docker + Docker Compose

### Project Structure

```
RAGInbox/
├── Documents/                      # Source documents for KB
├── data/
│   └── chroma_db/                 # Vector database storage
├── src/
│   ├── __init__.py
│   ├── config.py                  # Configuration management
│   ├── demo_phase1.py             # CLI interface (raginbox command)
│   ├── document_processing/
│   │   ├── __init__.py
│   │   ├── document_processor.py  # Document parsing and chunking
│   │   ├── file_watcher.py        # Monitor Documents folder
│   │   └── kb_manager.py          # Vector DB operations
│   ├── email/                     # Phase 2
│   │   ├── __init__.py
│   │   ├── email_client.py        # IMAP connection
│   │   ├── email_processor.py     # Email parsing and filtering
│   │   └── email_sender.py        # SMTP email sending
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── rag_engine.py          # LlamaIndex query engine
│   │   └── query_handler.py       # Query processing logic
│   └── api/                       # Phase 4
│       ├── __init__.py
│       ├── api.py                 # FastAPI application
│       └── static/                # Frontend files
│           ├── index.html
│           ├── style.css
│           └── app.js
├── tests/
│   ├── __init__.py
│   ├── test_document_processor.py
│   ├── test_kb_manager.py
│   ├── test_email_client.py
│   └── test_rag_engine.py
├── docker/                        # Phase 5
│   ├── Dockerfile
│   └── docker-compose.yml
├── .env.example                   # Environment variables template
├── .env                           # Instance-specific configuration
├── pyproject.toml                 # Package configuration
├── PLANNING.md                    # This file
├── TASK.md                        # Task tracking
├── docs/                          # Documentation
│   ├── QUICKSTART.md              # Quick start guide
│   ├── DATA_STRUCTURE.md          # Data directory structure
│   ├── EMAIL_PROCESSING_RULES.md  # Email processing logic
│   ├── DATABASE_DESIGN.md         # Database design
│   ├── EMAIL_AUTH_ISSUE.md        # Authentication troubleshooting
│   └── PHASE2_PLAN.md             # Phase 2 implementation plan
└── README.md                      # Setup and usage instructions
```

## Design Decisions

### Vector Database: ChromaDB

**Rationale**: ChromaDB is lightweight, easy to set up, supports persistent storage, and works well in Docker containers. It's perfect for departmental-scale deployments without complex infrastructure requirements.

### Document Processing Strategy

- **Chunking**: Use LlamaIndex's SentenceSplitter with overlap to maintain context
- **Metadata**: Store filename, upload date, document type, source (manual/email)
- **Deduplication**: Track document hashes to avoid reprocessing unchanged files
- **Incremental Updates**: Only process new or modified documents

### Email Processing

- **IMAP Polling**: Check inbox every 5 minutes (configurable)
- **Message Filtering**:
  - Primary recipient → Query (send to query handler)
  - CC'd → Knowledge base ingestion
- **Duplicate Prevention**: Track processed message IDs in SQLite DB
- **Attachment Handling**: Save temporarily, process, then delete

### RAG Query Strategy

- **Retrieval**: Top-k similarity search (k=5, configurable)
- **Context Window**: Concatenate retrieved chunks with metadata
- **Prompt Template**: Include instruction to cite sources
- **Response Format**: Answer + list of source documents

### Security Considerations

- **Email Credentials**: Store securely in .env file (not committed)
- **No Authentication**: Web interface is open but logged
- **Input Validation**: Sanitize all user inputs and email content
- **Rate Limiting**: Prevent abuse of LLM API

## Development Workflow

### Phase 1: Core RAG Setup (Current)
1. Project structure setup
2. Configuration management
3. Document processor implementation
4. Vector DB integration
5. Basic query engine
6. Unit tests

### Phase 2: Email Inbox Integration (Current)
1. **IMAP Client Implementation**
   - Connect to IMAP server with SSL/TLS
   - Authenticate using credentials from .env
   - Handle connection errors and reconnection
   - Implement health check mechanism

2. **Email Message Processing**
   - Fetch unread emails from inbox
   - Parse email headers (From, To, CC, Subject, Date)
   - Processing rules:
     * Direct emails (To: bot) → Query (send RAG reply)
     * Forwarded emails (Fw:, Fwd:) → KB ingestion (configurable)
     * CC/BCC emails → KB ingestion (silent)
   - Extract email body (text/html with HTML-to-text conversion)
   - Support multilingual forwarded detection (configurable prefixes)
   - Mark processed emails appropriately

3. **Message Tracking System**
   - Create SQLite database for tracking processed messages
   - Store message IDs to prevent duplicate processing
   - Track processing status and timestamps
   - Implement cleanup for old records

4. **Attachment Extraction**
   - Extract attachments from email messages
   - Support multiple attachment types (PDF, DOCX, TXT, CSV)
   - Save attachments to temporary directory
   - Clean up temporary files after processing
   - Handle attachment errors gracefully

5. **Integration with Document Processor**
   - Pass extracted attachments to document_processor
   - Process email body as text document if no attachments (for KB ingestion emails)
   - Add metadata (sender, date, subject) to chunks
   - Support duplicate detection via file hash
   - Update KB with new email content

6. **Email Service Daemon**
   - Create background service for continuous monitoring
   - Implement configurable polling interval
   - Add graceful shutdown handling
   - Include logging for all email operations

7. **Testing**
   - Mock IMAP server for unit tests
   - Test email filtering (TO vs CC)
   - Test attachment extraction
   - Test message tracking
   - Integration tests with document processor

### Phase 3: Email Response
1. Query detection and routing
2. RAG query integration
3. Response generation
4. SMTP email sending
5. Logging and monitoring
6. Unit tests

### Phase 4: Web Frontend
1. FastAPI endpoints
2. Chat interface UI
3. Session management
4. Response streaming (optional)
5. Frontend tests

### Phase 5: Docker & Deployment
1. Dockerfile creation
2. Docker Compose configuration
3. Environment setup
4. Volume management
5. Service orchestration

## Code Style & Conventions

- **PEP8 compliance** with Black formatting
- **Type hints** for all function signatures
- **Pydantic models** for data validation
- **Google-style docstrings** for all functions
- **Relative imports** within packages
- **Maximum file length**: 500 lines
- **Virtual environment**: Use `.venv` for all Python commands

## Testing Strategy

- **Pytest** for all unit tests
- **Test coverage**: Minimum 70%
- **Test structure**: Mirror source structure in `/tests`
- **Test categories**:
  - Expected behavior
  - Edge cases
  - Failure scenarios
- **Mocking**: Mock external services (LLM API, email server)

## Configuration Management

All configuration via environment variables in `.env` file:

### Instance Configuration (Customizable per deployment)
- `INSTANCE_NAME`: Name of this assistant instance (e.g., "DoLS-GPT", "HR-Assistant")
- `INSTANCE_DESCRIPTION`: Purpose description (used in system prompts)
- `ORGANIZATION`: Organization name (optional)

### API Configuration
- `OPENAI_API_KEY`: API key for embeddings (supports Naga.ac, OpenAI)
- `OPENAI_API_BASE`: API base URL (default: OpenAI, or Naga.ac)
- `OPENAI_EMBEDDING_MODEL`: Embedding model name
- `OPENROUTER_API_KEY`: API key for LLM queries
- `OPENROUTER_API_BASE`: LLM API base URL
- `OPENROUTER_MODEL`: LLM model name

### Document Processing
- `DOCUMENTS_PATH`: Path to source documents folder
- `CHROMA_DB_PATH`: Path to vector database
- `CHUNK_SIZE`, `CHUNK_OVERLAP`: Document chunking parameters
- `TOP_K_RETRIEVAL`: Number of documents to retrieve for context

### Email Configuration (Phase 2)
- `IMAP_SERVER`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`: Email inbox (IMAP)
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`: Email sending (SMTP)
- `EMAIL_CHECK_INTERVAL`: Polling frequency (seconds)
- `EMAIL_TARGET_ADDRESS`: Target email address for this instance
- `EMAIL_DISPLAY_NAME`: Display name in email responses

## Example Instance Deployments

RAGInbox supports multiple deployment scenarios:

### 1. DoLS-GPT (Department Assistant)
```env
INSTANCE_NAME=DoLS-GPT
INSTANCE_DESCRIPTION=AI assistant for the Department of Life Sciences
ORGANIZATION=Imperial College London
EMAIL_TARGET_ADDRESS=dols.gpt@imperial.ac.uk
```
**Use Case**: Departmental knowledge base for policies, procedures, and academic information.

### 2. HR-Assistant (Corporate HR)
```env
INSTANCE_NAME=HR-Assistant
INSTANCE_DESCRIPTION=Human Resources policy assistant
ORGANIZATION=Acme Corporation
EMAIL_TARGET_ADDRESS=hr.bot@acme.com
```
**Use Case**: Employee self-service for HR policies, benefits, and onboarding documentation.

### 3. TechDocs-AI (Technical Documentation)
```env
INSTANCE_NAME=TechDocs-AI
INSTANCE_DESCRIPTION=Technical documentation assistant
ORGANIZATION=Tech Startup Inc
EMAIL_TARGET_ADDRESS=docs@techstartup.io
```
**Use Case**: Developer documentation and API reference queries.

## Monitoring & Logging

- **Structured logging** using Python's logging module
- **Log levels**: DEBUG for development, INFO for production
- **Log rotation**: Daily rotation with 30-day retention
- **Metrics to track**:
  - Documents processed
  - Queries handled
  - Email processing time
  - LLM API usage
  - Error rates

## Future Enhancements

- Multi-user authentication for web interface
- Advanced analytics dashboard
- Integration with Microsoft Teams/Slack
- Support for more document formats (PPT, Excel)
- Semantic caching to reduce LLM costs
- Fine-tuning on departmental data
- Multilingual support
