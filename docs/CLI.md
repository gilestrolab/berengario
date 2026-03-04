# Berengario CLI Documentation

Command-line interface for Berengario administration and management.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
- [Commands](#commands)
  - [Knowledge Base Commands](#knowledge-base-commands)
  - [Database Commands](#database-commands)
  - [Backup Commands](#backup-commands)
  - [System Commands](#system-commands)
- [Examples](#examples)

## Overview

The Berengario CLI (`berengario-cli`) provides a unified command-line interface for managing your Berengario instance. It offers commands for:

- **Knowledge Base management** - List, stats, reingest, delete documents
- **Database operations** - Initialize, test connection, view statistics
- **Backup management** - Create, list, delete, and cleanup backups
- **System information** - View configuration and instance details

## Installation

The CLI is included with Berengario and runs inside the Docker container:

```bash
# Access the CLI inside the container
docker exec berengario-web python -m src.cli.main [COMMAND]
```

For convenience, you can create an alias:

```bash
# Add to your ~/.bashrc or ~/.zshrc
alias berengario="docker exec berengario-web python -m src.cli.main"

# Then use it directly
berengario kb list
berengario db stats
```

## Usage

### Basic Syntax

```bash
python -m src.cli.main [OPTIONS] COMMAND [ARGS]
```

### Global Options

- `--verbose, -v` - Enable verbose output
- `--debug` - Enable debug logging
- `--help` - Show help message

### Getting Help

```bash
# General help
python -m src.cli.main --help

# Command group help
python -m src.cli.main kb --help
python -m src.cli.main db --help
python -m src.cli.main backup --help

# Specific command help
python -m src.cli.main kb list --help
python -m src.cli.main db init --help
```

## Commands

### Knowledge Base Commands

Manage documents in the Berengario knowledge base (ChromaDB).

#### `kb list`

List all documents in the knowledge base.

```bash
python -m src.cli.main kb list
```

**Output:**
- Filename
- Hash (shortened SHA-256)
- Number of chunks
- Source type (file/email/manual)
- File type (.pdf, .docx, etc.)

#### `kb stats`

Show knowledge base statistics.

```bash
python -m src.cli.main kb stats
```

**Output:**
- Total documents and chunks
- Average chunks per document
- Breakdown by source type
- Breakdown by file type
- Storage path and size

#### `kb reingest`

Reingest all documents from `data/documents/` directory.

```bash
python -m src.cli.main kb reingest
```

**Features:**
- Processes all supported files (PDF, DOCX, TXT, CSV)
- Shows progress bar during processing
- Provides success/error summary
- Updates knowledge base with latest content

**Use cases:**
- After changing embedding models
- After updating chunk size settings
- To rebuild the knowledge base from scratch

#### `kb delete`

Delete a document from the knowledge base by its hash.

```bash
python -m src.cli.main kb delete <HASH> [--force]
```

**Arguments:**
- `HASH` - File hash (SHA-256) of document to delete (can use shortened version from `kb list`)

**Options:**
- `--force, -f` - Skip confirmation prompt

**Example:**
```bash
# Find document hash
python -m src.cli.main kb list

# Delete document (with confirmation)
python -m src.cli.main kb delete ac6342edf580

# Delete without confirmation
python -m src.cli.main kb delete ac6342edf580 --force
```

#### `kb clear`

Clear the entire knowledge base.

```bash
python -m src.cli.main kb clear [--force]
```

**Options:**
- `--force, -f` - Skip confirmation prompt

**Warning:** This deletes ALL documents from the knowledge base and cannot be undone!

### Database Commands

Manage database operations and view statistics.

#### `db init`

Initialize database tables.

```bash
python -m src.cli.main db init
```

**Features:**
- Creates all required tables if they don't exist
- Safe to run multiple times (idempotent)
- Equivalent to `scripts/init_conversation_db.py`

**Use cases:**
- First-time setup
- After database migrations
- Recreating tables after manual deletion

#### `db test`

Test database connection.

```bash
python -m src.cli.main db test
```

**Output:**
- Connection status
- Database type (MariaDB/SQLite)
- Database URL (sanitized)
- Driver name

**Use cases:**
- Troubleshooting connection issues
- Verifying database configuration
- Checking database availability

#### `db info`

Show database information and configuration.

```bash
python -m src.cli.main db info
```

**Output:**
- Database type, URL, and driver
- Configuration details (host, port, database name, user)
- File path (for SQLite)

#### `db stats`

Show database statistics.

```bash
python -m src.cli.main db stats [--days N]
```

**Options:**
- `--days, -d` - Number of days to show in activity report (default: 7)

**Output:**
- Overall message processing statistics
- Success/error counts and rates
- Daily activity breakdown
- Conversation statistics (email vs webchat)

#### `db cleanup`

Clean up old message tracking records.

```bash
python -m src.cli.main db cleanup [--days N] [--force]
```

**Options:**
- `--days, -d` - Delete records older than N days (default: 90)
- `--force, -f` - Skip confirmation prompt

**Behavior:**
- Deletes individual message records older than the specified number of days
- Daily aggregate statistics are preserved (only detailed records are removed)
- Helps prevent unbounded database growth

**Example:**
```bash
# Clean up records older than 90 days (with confirmation)
python -m src.cli.main db cleanup

# Clean up records older than 30 days, skip confirmation
python -m src.cli.main db cleanup --days 30 --force
```

### Backup Commands

Create and manage system backups.

#### `backup create`

Create a new backup of the data directory.

```bash
python -m src.cli.main backup create
```

**Features:**
- Creates compressed ZIP file
- Includes all data (KB, documents, config, logs)
- Shows progress during creation
- Displays backup filename and size

**Backup contents:**
- `data/documents/` - Source documents
- `data/chroma_db/` - Vector database
- `data/config/` - Configuration files
- `data/logs/` - Application logs
- Database (if using SQLite)

#### `backup list`

List all available backups.

```bash
python -m src.cli.main backup list
```

**Output:**
- Filename
- File size
- Creation date/time

**Note:** Backups are sorted by creation time (newest first).

#### `backup delete`

Delete a specific backup file.

```bash
python -m src.cli.main backup delete <FILENAME> [--force]
```

**Arguments:**
- `FILENAME` - Backup filename to delete (from `backup list`)

**Options:**
- `--force, -f` - Skip confirmation prompt

**Example:**
```bash
# List backups
python -m src.cli.main backup list

# Delete specific backup
python -m src.cli.main backup delete berengario_backup_20251101_153045.zip
```

#### `backup cleanup`

Clean up old backups automatically.

```bash
python -m src.cli.main backup cleanup [--keep N] [--days N] [--force]
```

**Options:**
- `--keep, -k` - Number of recent backups to keep (default: 5)
- `--days, -d` - Delete backups older than N days (default: 7)
- `--force, -f` - Skip confirmation prompt

**Behavior:**
- Always keeps the N most recent backups
- Deletes backups older than specified days
- Shows what will be deleted before confirmation

**Example:**
```bash
# Keep last 3 backups, delete anything older than 14 days
python -m src.cli.main backup cleanup --keep 3 --days 14
```

### System Commands

View system information and configuration.

#### `version`

Show Berengario version and instance information.

```bash
python -m src.cli.main version
```

**Output:**
- Instance name, organization, description
- LLM model
- Embedding model
- Database type
- Knowledge base path

#### `info`

Show detailed system information and configuration.

```bash
python -m src.cli.main info
```

**Output:**
- Instance details
- Model configuration
- RAG parameters (chunk size, top-k, similarity threshold)
- Database configuration
- File paths

## Examples

### Daily Operations

```bash
# Check system status
python -m src.cli.main version
python -m src.cli.main kb stats
python -m src.cli.main db stats

# List documents
python -m src.cli.main kb list

# Create backup
python -m src.cli.main backup create
```

### Maintenance Tasks

```bash
# Reingest all documents (after changing settings)
python -m src.cli.main kb reingest

# Initialize database tables (first-time setup)
python -m src.cli.main db init

# Clean up old message tracking records
python -m src.cli.main db cleanup --days 90

# Clean up old backups
python -m src.cli.main backup cleanup --keep 5 --days 7
```

### Troubleshooting

```bash
# Test database connection
python -m src.cli.main db test

# View detailed database info
python -m src.cli.main db info

# Check knowledge base statistics
python -m src.cli.main kb stats --verbose

# View recent activity
python -m src.cli.main db stats --days 30
```

### Docker Alias Setup

For easier access, create a shell alias:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias berengario="docker exec berengario-web python -m src.cli.main"

# Reload shell
source ~/.bashrc  # or source ~/.zshrc

# Now use commands directly
berengario kb list
berengario db stats
berengario backup create
```

### Scripting and Automation

The CLI can be used in scripts and automation:

```bash
#!/bin/bash
# Daily backup and cleanup script

# Create backup
docker exec berengario-web python -m src.cli.main backup create

# Clean up old backups (keep last 7, delete older than 30 days)
docker exec berengario-web python -m src.cli.main backup cleanup \
  --keep 7 --days 30 --force

# Check statistics
docker exec berengario-web python -m src.cli.main kb stats
docker exec berengario-web python -m src.cli.main db stats
```

## Migration from Scripts

The CLI replaces the scripts in the `scripts/` folder:

| Old Script | New CLI Command |
|-----------|----------------|
| `scripts/reingest.sh` | `berengario kb reingest` |
| `scripts/init_conversation_db.py` | `berengario db init` |
| Manual backup | `berengario backup create` |

## Exit Codes

The CLI uses standard exit codes:

- `0` - Success
- `1` - General error
- `130` - Cancelled by user (Ctrl+C)

## Output Formatting

- **Colorized output** - Uses rich library for colorful, formatted output
- **Progress bars** - Shows progress for long operations (reingest, backup)
- **Tables** - Pretty-printed tables for list commands
- **Interactive prompts** - Confirmation for destructive operations

## Best Practices

1. **Always create backups before major operations**
   ```bash
   berengario backup create
   berengario kb clear  # or other destructive operation
   ```

2. **Use verbose mode for troubleshooting**
   ```bash
   berengario --verbose kb reingest
   ```

3. **Regular maintenance**
   ```bash
   # Weekly: Clean up old backups
   berengario backup cleanup --keep 5 --days 7

   # Monthly: Clean up old message records and check statistics
   berengario db cleanup --days 90 --force
   berengario kb stats
   berengario db stats --days 30
   ```

4. **Test database connection after configuration changes**
   ```bash
   berengario db test
   berengario db info
   ```

## Troubleshooting

### Command not found

**Problem:** `bash: python: command not found`

**Solution:** Make sure you're running commands inside the Docker container:
```bash
docker exec berengario-web python -m src.cli.main --help
```

### Permission denied

**Problem:** Permission errors when creating backups or accessing files

**Solution:** The CLI runs as the `berengario` user inside the container. File permissions should be correct by default.

### Import errors

**Problem:** `ImportError: cannot import name '...'`

**Solution:** Ensure dependencies are installed:
```bash
docker exec berengario-web pip install typer rich
```

## Future Enhancements

Planned additions for future releases:

- `user` commands - Manage user roles and permissions
- `conversation` commands - View and manage conversations
- `config` commands - Modify configuration settings
- `service` commands - Manage running services
- JSON output option for scripting (`--json` flag)
- Host system support (run CLI outside Docker)

## See Also

- [Berengario Documentation](../README.md)
- [Configuration Guide](../.env.example)
- [Docker Deployment](../docker-compose.yml)
- [Admin Web Panel](http://localhost:8000/admin)
