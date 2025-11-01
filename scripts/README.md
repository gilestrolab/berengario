# RAGInbox Scripts

Utility scripts for managing the RAGInbox system.

## Available Scripts

### 📄 `reingest.sh`

**Purpose**: Re-process all documents from `data/documents/` into the knowledge base.

**Use when**:
- Embedding model configuration changes
- ChromaDB needs to be rebuilt
- Documents need to be reprocessed with new settings

**Usage**:
```bash
./scripts/reingest.sh
```

**How it works**:
1. Stops raginbox-web and raginbox-email containers
2. Runs `reingest_documents.py` in a temporary container
3. Restarts the containers

---

### 🐍 `reingest_documents.py`

**Purpose**: Python script that actually processes documents (called by `reingest.sh`).

**Usage**: Normally not called directly - use `reingest.sh` instead.

If needed to run manually in Docker:
```bash
docker-compose run --rm raginbox-web python /app/scripts/reingest_documents.py
```

---

### 💬 `init_conversation_db.py`

**Purpose**: Initialize or update conversation database schema.

**Use when**:
- Setting up a new database
- Database schema needs updating

**Usage**:
```bash
docker exec raginbox-web python /app/scripts/init_conversation_db.py
```

---

## Common Tasks

### Rebuild Knowledge Base (after config changes)

```bash
./scripts/reingest.sh
```

### Upload New Documents

Use the admin web panel at http://localhost:8000/admin instead of scripts for uploading new documents.
