# Phase 2: Email Inbox Integration - Implementation Plan

> **📜 HISTORICAL DOCUMENT**: This was the planning document for Phase 2 implementation.
> **Status**: Phase 2 is now complete (as of 2025-10-29).
> **Current Documentation**: See [EMAIL_PROCESSING_RULES.md](EMAIL_PROCESSING_RULES.md) and [README.md](../README.md) for current system behavior.

## Overview

Phase 2 adds email inbox monitoring to Berengario, enabling automatic knowledge base updates from CC'd emails with attachments. This allows instances to receive documents via email instead of manual uploads.

## Scope

**In Scope:**
- IMAP inbox monitoring for CC'd emails
- Attachment extraction (PDF, DOCX, TXT, CSV)
- Automatic KB ingestion from email attachments
- Email body processing (when no attachments)
- Message tracking to prevent duplicates
- Background service for continuous monitoring

**Out of Scope (Phase 3):**
- Email query responses (TO emails)
- SMTP sending
- Interactive email conversations

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Email Service                        │
│  ┌────────────────────────────────────────────────┐    │
│  │  Polling Loop (every 5 min)                    │    │
│  └────────────────────────────────────────────────┘    │
│                        ↓                                │
│  ┌────────────────────────────────────────────────┐    │
│  │  IMAP Client                                   │    │
│  │  - Connect to Office 365                       │    │
│  │  - Fetch unread emails                         │    │
│  │  - SSL/TLS connection                          │    │
│  └────────────────────────────────────────────────┘    │
│                        ↓                                │
│  ┌────────────────────────────────────────────────┐    │
│  │  Email Parser                                  │    │
│  │  - Parse headers (From, To, CC)                │    │
│  │  - Extract body (text/html)                    │    │
│  │  - Identify CC'd emails                        │    │
│  └────────────────────────────────────────────────┘    │
│                        ↓                                │
│  ┌────────────────────────────────────────────────┐    │
│  │  Message Tracker (SQLite)                      │    │
│  │  - Check if already processed                  │    │
│  │  - Prevent duplicate processing                │    │
│  └────────────────────────────────────────────────┘    │
│                        ↓                                │
│  ┌────────────────────────────────────────────────┐    │
│  │  Attachment Handler                            │    │
│  │  - Extract attachments                         │    │
│  │  - Validate file types                         │    │
│  │  - Save to temp directory                      │    │
│  └────────────────────────────────────────────────┘    │
│                        ↓                                │
│  ┌────────────────────────────────────────────────┐    │
│  │  Document Processor (Phase 1)                  │    │
│  │  - Process attachments                         │    │
│  │  - Add metadata (sender, subject, date)        │    │
│  │  - Update KB                                   │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. Database Abstraction Layer

**Purpose:** Configurable database support for SQLite (dev) and MariaDB (production)

**Components:**
- `src/email/db_models.py` - SQLAlchemy ORM models
- `src/email/db_manager.py` - Database connection management
- `src/email/message_tracker.py` - High-level message tracking interface

**Database Options:**
- **SQLite** (default): File-based, zero config, perfect for development
- **MariaDB**: Production-ready, containerization-friendly, scalable

**See:** `DATABASE_DESIGN.md` for full architecture details

**Key Models:**
- `ProcessedMessage` - Tracks all processed emails
- `ProcessingStats` - Daily statistics

**Key Methods:**
- `is_processed(message_id: str) -> bool`
- `mark_processed(message_id: str, sender: str, subject: str, ...)`
- `get_stats(days: int) -> dict`
- `cleanup_old_records(days: int = 90)`

### 2. EmailClient (`src/email/email_client.py`)
**Purpose:** IMAP connection management

**Features:**
- SSL/TLS connection to IMAP server
- Authentication with retry logic
- Connection health monitoring
- Automatic reconnection on failures
- Fetch unread emails
- Mark emails as read/seen

**Key Methods:**
- `connect() -> bool`
- `disconnect()`
- `is_connected() -> bool`
- `fetch_unread_emails() -> List[EmailMessage]`
- `mark_as_read(message_id: str)`

### 3. EmailParser (`src/email/email_parser.py`)
**Purpose:** Parse email messages

**EmailMessage Model (Pydantic):**
```python
class EmailMessage:
    message_id: str
    from_address: str
    to_addresses: List[str]
    cc_addresses: List[str]
    subject: str
    date: datetime
    body_text: str
    body_html: str
    attachments: List[Attachment]

    def is_cc_only(self, target_address: str) -> bool
```

**Features:**
- Parse RFC822 email format
- Extract all headers
- Convert HTML to text
- Validate email addresses
- Extract inline attachments

### 4. AttachmentHandler (`src/email/attachment_handler.py`)
**Purpose:** Extract and validate attachments

**Attachment Model:**
```python
class Attachment:
    filename: str
    content_type: str
    size: int
    data: bytes
```

**Features:**
- Extract all attachments from email
- Validate file types (PDF, DOCX, TXT, CSV only)
- Size limit enforcement (10MB default)
- Safe filename sanitization
- Temporary file management
- Automatic cleanup

**Key Methods:**
- `extract_attachments(email_msg) -> List[Attachment]`
- `save_to_temp(attachment: Attachment) -> Path`
- `cleanup_temp_files()`
- `is_valid_attachment(attachment: Attachment) -> bool`

### 5. EmailProcessor (`src/email/email_processor.py`)
**Purpose:** Main orchestration logic

**Workflow:**
1. Fetch unread emails from IMAP
2. Parse each email
3. Check if CC'd to target address
4. Check if already processed (MessageTracker)
5. Extract attachments
6. Process attachments via DocumentProcessor
7. Add email metadata to chunks
8. Mark as processed
9. Clean up temp files

**Key Methods:**
- `process_inbox() -> ProcessingStats`
- `process_single_email(email_msg: EmailMessage)`
- `should_process_email(email_msg: EmailMessage) -> bool`

### 6. EmailService (`src/email/email_service.py`)
**Purpose:** Background daemon for continuous monitoring

**Features:**
- Configurable polling interval
- Graceful shutdown (SIGTERM/SIGINT)
- Exponential backoff on errors
- Health monitoring
- Comprehensive logging
- Service statistics

**Key Methods:**
- `start()`
- `stop()`
- `run_forever()`
- `get_status() -> ServiceStatus`

## Configuration

**New Environment Variables:**
```bash
# Email Server (IMAP)
IMAP_SERVER=outlook.office365.com
IMAP_PORT=993
IMAP_USER=dolsbot@ic.ac.uk
IMAP_PASSWORD=your-password
IMAP_USE_SSL=true

# Email Processing
EMAIL_CHECK_INTERVAL=300  # seconds
EMAIL_TARGET_ADDRESS=dols.gpt@imperial.ac.uk
EMAIL_TEMP_DIR=./data/temp_attachments
MAX_ATTACHMENT_SIZE=10485760  # 10MB in bytes

# Database Configuration (Message Tracking)
DB_TYPE=sqlite  # or 'mariadb' for production

# SQLite (development)
SQLITE_DB_PATH=./data/message_tracker.db

# MariaDB (production/docker)
# DB_HOST=mariadb
# DB_PORT=3306
# DB_NAME=berengario
# DB_USER=berengario
# DB_PASSWORD=secure_password
# DB_POOL_SIZE=5
# DB_POOL_RECYCLE=3600
```

## Implementation Order

Follow this sequence to minimize dependencies:

1. **Database Layer** - Foundation for everything
   - `db_models.py` - SQLAlchemy models
   - `db_manager.py` - Database connection management
   - `message_tracker.py` - High-level tracking interface

2. **EmailClient** - Uses config only, independent

3. **EmailParser** - Uses imap-tools and html2text, independent

4. **AttachmentHandler** - Independent module

5. **EmailProcessor** - Integrates all above + DocumentProcessor

6. **EmailService** - Uses EmailProcessor

7. **Database Migrations** - Alembic setup for schema management

8. **CLI Integration** - Add to demo_phase1.py

9. **Docker Support** - docker-compose with MariaDB

10. **Testing** - Throughout all steps

## Testing Strategy

### Unit Tests
- Mock IMAP server responses
- Test email parsing with various formats
- Test attachment extraction
- Test message tracking

### Integration Tests
- Test with real IMAP connection (use test account)
- Test end-to-end flow
- Test error handling and recovery

### Test Data
Create fixtures with:
- Email with single PDF attachment
- Email with multiple attachments
- Email with HTML body only
- Email with invalid attachments
- Malformed emails

## Success Criteria

Phase 2 is complete when:

1. ✅ Email service can connect to Office 365 IMAP
2. ✅ Service identifies CC'd emails correctly
3. ✅ Attachments are extracted and processed
4. ✅ Documents are added to knowledge base
5. ✅ Duplicate emails are prevented
6. ✅ Service runs continuously in background
7. ✅ All error cases are handled gracefully
8. ✅ Unit tests pass with >80% coverage
9. ✅ Integration tests pass with real IMAP
10. ✅ Documentation is complete

## CLI Commands

After Phase 2:

```bash
# Start email monitoring service
berengario --mode email

# Check email service status
berengario --mode email --status

# View processing statistics
berengario --mode email --stats

# Process inbox once (no daemon)
berengario --mode email --once
```

## Security Considerations

1. **Credentials**: Stored in .env, never logged
2. **Attachment Validation**:
   - File type whitelist only
   - Size limits enforced
   - Filename sanitization
3. **HTML Content**: Sanitize before processing
4. **Rate Limiting**: Don't overwhelm IMAP server
5. **Error Logging**: Never log email content, only metadata

## Performance

**Expected Load:**
- ~10 emails per day
- Average 1-2 attachments per email
- Average attachment size: 1-5MB

**Performance Targets:**
- Process single email: <5 seconds
- Polling overhead: <1 second
- No memory leaks on long-running service

## Dependencies

**New (Required):**
- `html2text>=2024.2.26` - HTML to plain text conversion
- `sqlalchemy>=2.0.0` - Database ORM (already via llama-index)
- `alembic>=1.13.0` - Database migrations

**New (Optional - MariaDB):**
- `pymysql>=1.1.0` - MariaDB/MySQL driver
- `cryptography>=42.0.0` - SSL support for pymysql

**Installation:**
```bash
# Base installation (SQLite)
pip install -e .

# With MariaDB support
pip install -e ".[mariadb]"
```

**Existing:**
- `imap-tools>=1.7.0` - Already in requirements.txt

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| IMAP connection drops | High | Auto-reconnection with exponential backoff |
| Large attachments crash service | Medium | Size limits + memory monitoring |
| Malformed emails break parser | Low | Try-except blocks, skip invalid emails |
| Duplicate processing | Medium | SQLite tracking with message IDs |
| Office 365 rate limiting | Low | Reasonable polling interval (5 min) |

## Next Steps After Phase 2

Phase 3 will add:
- Query detection (TO emails)
- RAG integration for queries
- SMTP email responses
- Interactive conversations
