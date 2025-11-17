# Data Directory Structure

**Last Updated**: 2025-10-29

## Overview

All persistent data for DoLS-GPT is stored under the `data/` directory. This consolidation simplifies Docker volume mounting and backup procedures.

---

## Directory Layout

```
data/
├── kb/                     # Knowledge Base content
│   ├── documents/         # All KB documents (from any source)
│   │   ├── *.pdf          # PDF documents (attachments + manual uploads)
│   │   ├── *.docx         # Word documents
│   │   ├── *.txt          # Text files
│   │   ├── *.csv          # CSV files
│   │   └── ...
│   └── emails/            # Saved email copies (without attachments)
│       └── Email from *.txt
├── documents/             # Optional: Legacy watched folder for manual drops
│   └── ...                # Files here can be manually added
├── chroma_db/             # ChromaDB vector database (persistent)
│   ├── chroma.sqlite3     # Metadata and index
│   └── {collection_id}/   # Vector embeddings (binary)
├── config/                # Configuration files
│   ├── allowed_teachers.txt # Teaching whitelist
│   ├── allowed_queriers.txt # Query whitelist
│   └── allowed_admins.txt   # Admin whitelist
├── logs/                  # Application logs
│   └── dols_gpt.log       # Main log file
├── temp_attachments/      # Temporary email attachments (ephemeral)
│   └── email_{id}_{msg}/  # Temporary subdirectories per email
└── message_tracker.db     # SQLite database for email tracking
```

---

## Directory Details

### `data/kb/`
**Purpose**: Knowledge base content storage

This is the primary location for all knowledge base content, organized into two subdirectories:

#### `data/kb/documents/`
**Purpose**: All documents ingested into the knowledge base (from ANY source)

**Contents**:
- Email attachments (PDF, DOCX, TXT, CSV, etc.)
- Web interface uploads (via admin panel)
- Any document that becomes part of the knowledge base

**Size**: Grows with KB content (typically same size as source documents)

**Backup**: **CRITICAL** - Contains all source documents

**Docker Mount**:
```yaml
volumes:
  - ./data/kb/documents:/app/data/kb/documents
```

**Configuration**:
```bash
KB_DOCUMENTS_PATH=data/kb/documents
```

#### `data/kb/emails/`
**Purpose**: Saved copies of emails without attachments

**Contents**:
- Email body text files with descriptive filenames
- Format: `Email from {sender} on {date} - {subject}.txt`
- Attachments are saved separately in `data/kb/documents/`

**Size**: Small (typically <10MB total)

**Backup**: **RECOMMENDED** - Useful for re-ingestion

**Docker Mount**:
```yaml
volumes:
  - ./data/kb/emails:/app/data/kb/emails
```

**Configuration**:
```bash
KB_EMAILS_PATH=data/kb/emails
```

---

### `data/documents/`
**Purpose**: Legacy/optional watched folder for manual document drops

**Usage**:
- Can still be used for manual file drops (optional)
- Maintained for backward compatibility
- Not actively used by email processing or web uploads

**Docker Mount**:
```yaml
volumes:
  - ./data/documents:/app/data/documents
```

**Configuration**:
```bash
DOCUMENTS_PATH=data/documents
```

---

### `data/chroma_db/`
**Purpose**: Persistent vector database storage

**Contents**:
- `chroma.sqlite3`: Metadata, document hashes, and indexes
- Collection folders: Binary vector embeddings and HNSW index

**Size**: Grows with document count (typically ~100KB per document)

**Backup**: **CRITICAL** - Contains all embedded knowledge

**Docker Mount**:
```yaml
volumes:
  - chroma_db_data:/app/data/chroma_db  # Named volume for persistence
```

**Configuration**:
```bash
CHROMA_DB_PATH=data/chroma_db
```

---

### `data/config/`
**Purpose**: Configuration files for runtime behavior

**Contents**:
- `allowed_teachers.txt`: Email whitelist for KB contributions (teaching permission)
- `allowed_queriers.txt`: Email whitelist for RAG queries (query permission)
- `allowed_admins.txt`: Email whitelist for admin panel access (admin permission)
- `custom_prompt.txt` (optional): Custom system prompt additions
- `email_footer.txt` (optional): Custom email footer

**Usage**:
- **Dual Whitelist System**: Separate permissions for teaching vs querying
  - **Teachers**: Can add content to KB via CC'd/BCC'd/forwarded emails
  - **Queriers**: Can send direct questions and receive RAG-powered replies
  - **Admins**: Have full access (can teach, query, and access admin panel)
- **Hierarchical**: Admins can do everything teachers can; teachers can query
- Supports domain wildcards (e.g., `@imperial.ac.uk`)
- Comments start with `#`
- One address/domain per line

**Size**: Very small (<10KB typically)

**Backup**: Recommended (important for security)

**Docker Mount**:
```yaml
volumes:
  - ./data/config:/app/data/config
```

**Configuration**:
```bash
# Teaching whitelist (who can add content to KB)
EMAIL_TEACH_WHITELIST_FILE=data/config/allowed_teachers.txt
EMAIL_TEACH_WHITELIST_ENABLED=true

# Query whitelist (who can ask questions)
EMAIL_QUERY_WHITELIST_FILE=data/config/allowed_queriers.txt
EMAIL_QUERY_WHITELIST_ENABLED=true

# Admin whitelist (who can access admin panel)
EMAIL_ADMIN_WHITELIST_FILE=data/config/allowed_admins.txt
EMAIL_ADMIN_WHITELIST_ENABLED=true
```

**See Also**: `docs/EMAIL_PROCESSING_RULES.md` for detailed whitelist validation logic

---

### `data/logs/`
**Purpose**: Application log files

**Contents**:
- `dols_gpt.log`: Main application log (rotating)

**Usage**:
- Debugging and troubleshooting
- Monitoring email processing
- Audit trail for operations

**Size**: Grows over time (configure log rotation)

**Backup**: Optional (useful for debugging but not critical)

**Docker Mount**:
```yaml
volumes:
  - ./data/logs:/app/data/logs
```

**Configuration**:
```bash
LOG_LEVEL=INFO
LOG_FILE=data/logs/dols_gpt.log
```

---

### `data/temp_attachments/`
**Purpose**: Temporary storage for email attachments during processing

**Lifecycle**:
- Created when email attachment is extracted
- Processed by DocumentProcessor
- **Automatically deleted** after processing (success or failure)
- Old files cleaned up periodically (7 days)

**Size**: Should remain small (<100MB typically)

**Backup**: Not required (ephemeral data)

**Docker Mount**:
```yaml
volumes:
  - /tmp/email_attachments:/app/data/temp_attachments  # Can use tmpfs
```

**Configuration**:
```bash
EMAIL_TEMP_DIR=data/temp_attachments
MAX_ATTACHMENT_SIZE=10485760  # 10MB default
```

---

### `data/message_tracker.db`
**Purpose**: SQLite database tracking processed emails

**Schema**:
- `processed_messages`: Message IDs, status, timestamps, chunk counts
- `processing_stats`: Daily aggregated statistics

**Size**: Grows slowly (~1KB per email)

**Backup**: Recommended (prevents duplicate processing)

**Docker Mount**:
```yaml
volumes:
  - ./data/message_tracker.db:/app/data/message_tracker.db
```

**Configuration**:
```bash
DB_TYPE=sqlite
SQLITE_DB_PATH=data/message_tracker.db
```

**Alternative (Production)**: MariaDB via `DB_TYPE=mariadb`

---

## Docker Volume Strategy

### Development (docker-compose.yml)

```yaml
version: '3.8'

services:
  raginbox:
    image: raginbox:latest
    volumes:
      # Documents folder (bind mount for easy access)
      - ./data/documents:/app/data/documents

      # Vector database (named volume for performance)
      - chroma_db_data:/app/data/chroma_db

      # Message tracker (bind mount for easy backup)
      - ./data/message_tracker.db:/app/data/message_tracker.db

      # Temp attachments (tmpfs for performance)
      - type: tmpfs
        target: /app/data/temp_attachments
        tmpfs:
          size: 100M

volumes:
  chroma_db_data:
    driver: local
```

### Production Considerations

1. **ChromaDB**: Use named volume with backup strategy
2. **Documents**: Bind mount for easy file management
3. **Message Tracker**: External MariaDB recommended
4. **Temp Attachments**: tmpfs or local SSD for performance

---

## Backup Strategy

### Critical (Must Backup)
- ✅ `data/chroma_db/` - Vector database (all knowledge)
- ✅ `data/message_tracker.db` - Email processing history
- ✅ `data/kb/documents/` - Source documents (all KB content)
- ✅ `data/kb/emails/` - Saved email copies

### Optional (Nice to Have)
- ⚠️ Configuration files (`.env`, `data/config/allowed_*.txt`, `data/logs/`)

### Not Required
- ❌ `data/temp_attachments/` - Temporary files (auto-deleted)
- ❌ `.venv/` - Virtual environment (reproducible)
- ❌ `__pycache__/` - Python cache (regenerated)

### Backup Command

```bash
# Create backup
tar -czf backup_$(date +%Y%m%d).tar.gz \
    data/chroma_db/ \
    data/kb/ \
    data/message_tracker.db \
    .env \
    data/config/

# Restore backup
tar -xzf backup_20251029.tar.gz
```

---

## Migration from Old Structure

### Migration to KB Structure (2025-11-13)

**Before**:
```
data/
  ├── documents/
  │   ├── *.pdf (mixed)
  │   ├── attachments/  # Email attachments
  │   └── emails/       # Saved emails
  ├── chroma_db/
  └── ...
```

**After**:
```
data/
  ├── kb/
  │   ├── documents/    # All documents (attachments + uploads)
  │   └── emails/       # Saved email copies
  ├── documents/        # Legacy (optional)
  ├── chroma_db/
  └── ...
```

**Migration Steps**:
```bash
# Step 1: Preview migration (dry run)
python migrate_kb_structure.py

# Step 2: Execute migration
python migrate_kb_structure.py --execute

# Step 3: Verify new structure
ls -la data/kb/documents/
ls -la data/kb/emails/

# Step 4: (Optional) Clean up old empty directories
rm -rf data/documents/attachments/
rm -rf data/documents/emails/

# Step 5: Restart services to use new paths
docker-compose restart
```

### Previous Migration (2025-10-29)

**Before 2025-10-29**:
```
Documents/          # Watched folder
data/
  ├── chroma_db/
  └── temp_attachments/
```

**After 2025-10-29**:
```
data/
  ├── documents/         # Moved from Documents/
  ├── chroma_db/
  ├── temp_attachments/
  └── message_tracker.db
```

---

## Storage Requirements

### Minimal Setup (Testing)
- Documents: 100 MB
- ChromaDB: 50 MB
- Message Tracker: 1 MB
- Temp: 10 MB
- **Total**: ~200 MB

### Small Deployment (50-100 documents)
- Documents: 500 MB
- ChromaDB: 500 MB
- Message Tracker: 5 MB
- Temp: 50 MB
- **Total**: ~1 GB

### Medium Deployment (500-1000 documents)
- Documents: 5 GB
- ChromaDB: 5 GB
- Message Tracker: 50 MB
- Temp: 100 MB
- **Total**: ~10 GB

### Large Deployment (5000+ documents)
- Documents: 50 GB
- ChromaDB: 50 GB
- Message Tracker: 500 MB
- Temp: 500 MB
- **Total**: ~100 GB

---

## Monitoring Disk Usage

```bash
# Check data directory size
du -sh data/*

# Check ChromaDB size
du -sh data/chroma_db/

# Check number of documents
ls -1 data/documents/ | wc -l

# Check temp attachments (should be small)
du -sh data/temp_attachments/

# Check message tracker size
du -sh data/message_tracker.db
```

---

## Cleanup Operations

### Clean Old Temp Files
```bash
# Via Python API
python -c "
from src.email.email_processor import email_processor
deleted = email_processor.cleanup_old_temp_files(days=7)
print(f'Deleted {deleted} old temp files')
"
```

### Clean Old Message Tracker Records
```bash
# Via Python API
python -c "
from src.email.message_tracker import MessageTracker
tracker = MessageTracker()
deleted = tracker.cleanup_old_records(days=90)
print(f'Deleted {deleted} old records')
"
```

### Reset ChromaDB (Caution!)
```bash
# WARNING: This deletes all embedded knowledge
rm -rf data/chroma_db/
mkdir -p data/chroma_db/

# Rebuild from documents
python src/demo_phase1.py --mode rebuild
```

---

## Security Considerations

### File Permissions
```bash
# Recommended permissions
chmod 755 data/
chmod 755 data/documents/
chmod 644 data/documents/*
chmod 700 data/chroma_db/
chmod 600 data/message_tracker.db
chmod 700 data/temp_attachments/
```

### Docker User
```dockerfile
# Run as non-root user
USER 1000:1000

# Ensure data directory ownership
RUN chown -R 1000:1000 /app/data
```

### Sensitive Data
- Do NOT commit `data/` to version control (already in `.gitignore`)
- Encrypt backups containing sensitive documents
- Use secure file transfer for backup uploads
- Consider encryption at rest for ChromaDB volumes

---

## Troubleshooting

### "No such file or directory: data/documents"
**Solution**: Create missing directory
```bash
mkdir -p data/documents data/chroma_db data/temp_attachments
```

### "Permission denied" when writing to data/
**Solution**: Fix ownership
```bash
sudo chown -R $USER:$USER data/
chmod 755 data/
```

### ChromaDB "Collection not found"
**Solution**: Reinitialize KB
```bash
python -c "from src.document_processing.kb_manager import KnowledgeBaseManager; KnowledgeBaseManager()"
```

### Temp attachments directory full
**Solution**: Clean old files
```bash
find data/temp_attachments/ -mtime +7 -delete
```

---

## See Also

- `PLANNING.md` - System architecture
- `README.md` - Setup instructions
- `EMAIL_PROCESSING_RULES.md` - Email processing logic
- `.env.example` - Configuration template
