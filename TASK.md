# DoLS-GPT KB System - Task List

## Project Initialization - 2025-10-28

### Phase 1: Core RAG Setup ✓ COMPLETED

#### Project Structure & Configuration
- [✓] Create project directory structure - 2025-10-28
- [✓] Write PLANNING.md documentation - 2025-10-28
- [✓] Create TASK.md for task tracking - 2025-10-28
- [✓] Create requirements.txt with all dependencies - 2025-10-28
- [✓] Create .env.example template - 2025-10-28
- [✓] Create .env with actual credentials - 2025-10-28
- [✓] Create .gitignore for security - 2025-10-28

#### Core Implementation
- [✓] Implement config.py with Pydantic settings management - 2025-10-28
- [✓] Implement document_processor.py for parsing multiple formats - 2025-10-28
- [✓] Implement kb_manager.py for ChromaDB vector operations - 2025-10-28
- [✓] Implement file_watcher.py for monitoring Documents folder - 2025-10-28
- [✓] Implement rag_engine.py for LlamaIndex query engine - 2025-10-28
- [✓] Create query_handler.py for processing queries - 2025-10-28

#### Testing
- [✓] Write unit tests for document_processor.py - 2025-10-28
- [✓] Write unit tests for kb_manager.py - 2025-10-28
- [✓] Create pytest configuration (conftest.py) - 2025-10-28

#### Documentation
- [✓] Create README.md with setup instructions - 2025-10-28
- [✓] Create demo_phase1.py script - 2025-10-28
- [✓] Add inline code documentation - 2025-10-28

---

### Phase 2: Email Inbox Integration (IN PROGRESS) - Started 2025-10-29

#### Step 1: Database Abstraction Layer ✓ COMPLETED - 2025-10-29

**Sub-step 1a: Database Models**
- [x] Create `src/email/db_models.py` module
- [x] Define SQLAlchemy `Base` declarative base
- [x] Implement `ProcessedMessage` model (message_id, sender, subject, etc.)
- [x] Implement `ProcessingStats` model for daily statistics
- [x] Add appropriate indexes for performance
- [x] Write unit tests for models

**Sub-step 1b: Database Manager**
- [x] Create `src/email/db_manager.py` module
- [x] Implement `DatabaseManager` class
- [x] Add `_create_engine()` method supporting SQLite and MariaDB
- [x] Implement session management with context manager
- [x] Add `init_db()` method to create tables
- [x] Handle connection pooling for MariaDB
- [x] Write unit tests with in-memory SQLite

**Sub-step 1c: Message Tracker Interface**
- [x] Create `src/email/message_tracker.py` module
- [x] Implement `MessageTracker` class using database manager
- [x] Add methods: `is_processed()`, `mark_processed()`, `get_stats()`
- [x] Implement `cleanup_old_records(days=90)`
- [x] Add daily stats aggregation
- [x] Write comprehensive unit tests

#### Step 2: IMAP Client Implementation ✓ COMPLETED - 2025-10-29
- [x] Create `src/email/email_client.py` module
- [x] Implement `EmailClient` class with IMAP connection
- [x] Add SSL/TLS connection support
- [x] Add STARTTLS support for port 143
- [x] Implement authentication using config credentials
- [x] Add connection health check method
- [x] Implement automatic reconnection on failures
- [x] Add methods: `connect()`, `disconnect()`, `is_connected()`
- [x] Handle common IMAP errors (auth failure, timeout, network errors)
- [x] Write unit tests with mock IMAP server

#### Step 3: Email Message Parser ✓ COMPLETED - 2025-10-29
- [x] Create `src/email/email_parser.py` module
- [x] Create `src/email/whitelist_validator.py` module
- [x] Implement email whitelist with domain wildcards
- [x] Implement file-based whitelist configuration
- [x] Implement email header parsing (From, To, CC, Subject, Date, Message-ID)
- [x] Add email body extraction (prefer text/plain, fallback to text/html)
- [x] Implement HTML to text conversion (using html2text)
- [x] Add email address parsing and validation
- [x] Create `EmailMessage` Pydantic model for structured data
- [x] Handle tuple-based To/CC fields from imap-tools
- [x] Write unit tests with sample email messages

#### Step 4: Attachment Handler ✓ COMPLETED - 2025-10-29
- [x] Create `src/email/attachment_handler.py` module
- [x] Implement attachment extraction from email messages
- [x] Add file type validation (PDF, DOCX, TXT, CSV, XLSX, PPTX, etc.)
- [x] Create temporary directory for attachment storage
- [x] Implement safe filename sanitization
- [x] Add file size limits (configurable, default 10MB)
- [x] Implement cleanup of temporary files
- [x] Handle corrupted/invalid attachments gracefully
- [x] Write unit tests for attachment extraction

#### Step 5: Email Processor (Main Logic) ✓ COMPLETED - 2025-10-29
- [x] Create `src/email/email_processor.py` module
- [x] Implement `EmailProcessor` class integrating all components
- [x] Add email filtering logic (identify CC'd emails for queries vs KB ingestion)
- [x] Integrate with `MessageTracker` for duplicate prevention
- [x] Integrate with `AttachmentHandler` for file extraction
- [x] Integrate with `DocumentProcessor` for KB updates
- [x] Add metadata enrichment (sender, subject, date to chunks)
- [x] Process email body as document if no attachments
- [x] Implement error handling and logging
- [x] Write integration tests
- [x] Real-world testing with mailu.gilest.ro server
- [x] Successfully processed 2 emails from g.gilestro@imperial.ac.uk

#### Step 6: Email Service Daemon ✓ COMPLETED - 2025-10-29
- [x] Create `src/email/email_service.py` module
- [x] Implement background polling service
- [x] Add configurable polling interval (EMAIL_CHECK_INTERVAL)
- [x] Implement graceful shutdown on SIGTERM/SIGINT
- [x] Add service health monitoring (is_running, get_status)
- [x] Implement exponential backoff on failures
- [x] Add comprehensive logging for all operations
- [x] Create CLI command for running email service (run_email_service.py)
- [x] Write tests for service lifecycle (24 tests, all passing)

#### Step 7: Database Migrations
- [ ] Install alembic dependency
- [ ] Initialize alembic in project (`alembic init alembic`)
- [ ] Configure `alembic.ini` to use settings.get_database_url()
- [ ] Update `alembic/env.py` with models metadata
- [ ] Create initial migration for processed_messages table
- [ ] Create migration for processing_stats table
- [ ] Test migrations with both SQLite and MariaDB
- [ ] Document migration commands in README

#### Step 8: Configuration Updates
- [x] Add email-specific settings to `src/config.py`
- [x] Add database configuration to `src/config.py`
- [x] Update `.env.example` with email and database configuration
- [ ] Add configuration validation tests
- [ ] Document all new environment variables in README

#### Step 9: CLI Integration
- [ ] Update `src/demo_phase1.py` with new `--mode email` option
- [ ] Add email service start/stop commands
- [ ] Add command to check email service status
- [ ] Add command to view processing statistics
- [ ] Update help documentation

#### Step 10: Docker & Documentation
- [ ] Create `docker/Dockerfile` for RAGInbox
- [ ] Create `docker-compose.yml` with MariaDB service
- [ ] Add health checks and depends_on conditions
- [ ] Test Docker deployment with MariaDB
- [ ] Update README.md with Phase 2 features
- [ ] Update README.md with Docker deployment instructions
- [ ] Update QUICKSTART.md with email setup instructions
- [ ] Write end-to-end integration test
- [ ] Test with real IMAP server (Office 365)
- [ ] Test with various email formats and attachments
- [ ] Document common troubleshooting issues
- [ ] Performance testing with batch emails

---

## Discovered During Phase 2 Planning - 2025-10-29

#### Database Abstraction Layer
- [x] Design database abstraction to support SQLite and MariaDB
- [x] Create DATABASE_DESIGN.md documentation
- [x] Add database configuration to config.py
- [x] Update pyproject.toml with database dependencies
- [x] Add optional mariadb extras for pip install
- [x] Update .env.example with database options
- [ ] Update README.md with Phase 2 features
- [ ] Update QUICKSTART.md with email setup instructions
- [ ] Write end-to-end integration test
- [ ] Test with real IMAP server (Office 365)
- [ ] Test with various email formats and attachments
- [ ] Document common troubleshooting issues
- [ ] Performance testing with batch emails

---

### Phase 3: Email Query Handler (Upcoming)

#### Query Processing
- [ ] Implement query detection (TO vs CC filtering)
- [ ] Integrate RAG engine with email queries
- [ ] Implement email_sender.py with SMTP
- [ ] Add response formatting with source citations
- [ ] Implement query/response logging

#### Testing
- [ ] Write unit tests for query_handler.py
- [ ] Write unit tests for email_sender.py
- [ ] End-to-end email query tests

---

### Phase 4: Web Frontend (Upcoming)

#### API Development
- [ ] Implement FastAPI endpoints in api.py
- [ ] Add query endpoint with RAG integration
- [ ] Implement session management with cookies
- [ ] Add chat history retrieval endpoint

#### Frontend Development
- [ ] Create index.html with chat interface
- [ ] Create style.css for UI styling
- [ ] Create app.js for frontend logic
- [ ] Implement cookie-based session storage

#### Testing
- [ ] Write API endpoint tests
- [ ] Test session management
- [ ] Frontend functionality testing

---

### Phase 5: Docker & Deployment (Upcoming)

#### Containerization
- [ ] Create Dockerfile for application
- [ ] Create docker-compose.yml for orchestration
- [ ] Configure volume mounts for persistence
- [ ] Add health checks
- [ ] Document deployment process

#### Production Readiness
- [ ] Add logging configuration
- [ ] Implement error monitoring
- [ ] Add rate limiting
- [ ] Security audit
- [ ] Performance optimization

---

## Discovered During Work

### Phase 2 Email Integration - 2025-10-29

**Authentication Issues Resolved:**
- [x] Diagnosed Office 365 basic auth disabled at policy level - 2025-10-29
- [x] Created diagnostic scripts (diagnose_email.py, check_server_caps.py, test_auth_methods.py) - 2025-10-29
- [x] Documented issue and solutions in EMAIL_AUTH_ISSUE.md - 2025-10-29
- [x] Switched to alternative server (mailu.gilest.ro) for testing - 2025-10-29
- [x] Fixed STARTTLS support in email_client.py for port 143 - 2025-10-29
- [x] Fixed tuple handling bug in email_parser.py for To/CC fields - 2025-10-29

**Testing Achievements:**
- [x] All 173 unit tests passing (database, email client, parser, attachment, tracker, service) - 2025-10-29
- [x] Successfully connected to mailu.gilest.ro with STARTTLS - 2025-10-29
- [x] Successfully processed 2 real emails from g.gilestro@imperial.ac.uk - 2025-10-29
- [x] Whitelist validation working with domain wildcards (@imperial.ac.uk, @gilest.ro) - 2025-10-29
- [x] Message tracking and deduplication verified - 2025-10-29
- [x] Email service daemon with exponential backoff and graceful shutdown - 2025-10-29

**Email Processing Rules Update - 2025-10-29:**
- [x] Reversed email processing logic: To: bot = query, CC/BCC = KB ingestion - 2025-10-29
- [x] Implemented configurable forwarded email detection - 2025-10-29
- [x] Added FORWARD_TO_KB_ENABLED and FORWARD_SUBJECT_PREFIXES environment variables - 2025-10-29
- [x] Created is_forwarded() method with case-insensitive prefix matching - 2025-10-29
- [x] Added support for multilingual forwarding prefixes (Italian "i", Spanish "rv", etc.) - 2025-10-29
- [x] Updated email processor to handle emails without attachments (process body as document) - 2025-10-29
- [x] Created comprehensive test suite (19 new tests in test_forwarded_detection.py) - 2025-10-29
- [x] Updated documentation (EMAIL_PROCESSING_RULES.md with decision tree and FAQ) - 2025-10-29
- [x] Real-world test: Successfully processed forwarded email "Fw: HoD Awards 2025" as KB ingestion - 2025-10-29
- [x] All 220 email-related tests passing (226 total tests in suite) - 2025-10-29

**Data Directory Reorganization - 2025-10-29:**
- [x] Moved Documents/ to data/documents/ for Docker volume consolidation - 2025-10-29
- [x] Updated config.py default path to data/documents - 2025-10-29
- [x] Updated .env and .env.example to use relative paths (Docker-friendly) - 2025-10-29
- [x] Updated .gitignore with clarified comments - 2025-10-29
- [x] Created comprehensive DATA_STRUCTURE.md documentation - 2025-10-29
- [x] Updated README.md with new directory structure - 2025-10-29
- [x] Verified FileWatcher works with new path - 2025-10-29
- [x] All data now under data/ directory: documents/, chroma_db/, temp_attachments/, message_tracker.db - 2025-10-29

**Production Deployment Notes:**
- [ ] Contact Imperial IT to enable IMAP basic auth for dolsbot@ic.ac.uk
- [ ] OR implement OAuth2 authentication for Office 365 (more secure)
- [ ] Test with emails containing attachments for full KB ingestion workflow
- [ ] Test query processing (CC'd email without attachments → RAG query → email response)

---

## Completed Tasks Archive

### Phase 1 Completion - 2025-10-28
- Project structure created with all necessary directories
- PLANNING.md completed with full architecture documentation
- TASK.md initialized and maintained
- requirements.txt created with all dependencies
- .env.example and .env files configured
- .gitignore created for security
- config.py implemented with Pydantic settings
- document_processor.py implemented (PDF, DOCX, TXT, CSV support)
- kb_manager.py implemented (ChromaDB integration)
- file_watcher.py implemented (automatic file monitoring)
- rag_engine.py implemented (query processing with LlamaIndex)
- query_handler.py implemented (high-level query interface)
- Unit tests created for document_processor and kb_manager
- pytest configuration (conftest.py) created
- README.md created with comprehensive documentation
- demo_phase1.py script created for testing Phase 1 functionality
- All code includes type hints and Google-style docstrings
