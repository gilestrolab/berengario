"""
Tenant backup importer.

Imports a single-tenant backup ZIP as a new tenant in the multi-tenant
platform, uploading documents to S3 and placing ChromaDB locally.
"""

import logging
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from src.platform.db_manager import TenantDBManager
from src.platform.provisioning import TenantProvisioner
from src.platform.storage import StorageBackend

logger = logging.getLogger(__name__)

# Max uncompressed size: 2 GB (same as BackupManager)
MAX_IMPORT_SIZE = 2 * 1024 * 1024 * 1024

# Directories in the backup ZIP that contain uploadable documents
DOCUMENT_DIRS = ["kb/documents", "kb/emails", "documents"]


class ImportError(Exception):
    """Error during tenant backup import."""


class TenantBackupImporter:
    """
    Imports a single-tenant Berengario backup as a new multi-tenant tenant.

    Handles:
    - Backup validation
    - Tenant provisioning (DB, storage, encryption, admin user)
    - Document upload to S3 storage backend
    - ChromaDB collection rename and placement
    - Optional conversation migration
    - Rollback on failure
    """

    def __init__(
        self,
        provisioner: TenantProvisioner,
        storage: StorageBackend,
        db_manager: TenantDBManager,
    ):
        self.provisioner = provisioner
        self.storage = storage
        self.db_manager = db_manager

    @staticmethod
    def _detect_data_root(zip_path: Path) -> tuple[str, str | None]:
        """
        Detect the data root within a backup ZIP.

        Supports two layouts:
        - Single-tenant: files under data/kb/documents/, data/chroma_db/, etc.
        - Multi-tenant: files under data/tenants/{slug}/kb/documents/, etc.

        Returns:
            Tuple of (data_root_prefix, source_slug).
            - Single-tenant: ("data/", None)
            - Multi-tenant: ("data/tenants/{slug}/", "{slug}")
        """
        with zipfile.ZipFile(zip_path, "r") as zf:
            tenant_slugs = set()
            has_single_tenant_content = False

            for info in zf.infolist():
                name = info.filename
                if not name.startswith("data/") or info.is_dir():
                    continue

                rel = name[len("data/") :]

                # Check for multi-tenant layout: tenants/{slug}/...
                if rel.startswith("tenants/"):
                    parts = rel.split("/", 3)  # ["tenants", slug, rest...]
                    if len(parts) >= 3 and parts[1]:
                        tenant_slugs.add(parts[1])

                # Check for single-tenant layout
                for doc_dir in DOCUMENT_DIRS:
                    if rel.startswith(doc_dir + "/"):
                        has_single_tenant_content = True
                if rel.startswith("chroma_db/"):
                    has_single_tenant_content = True

            if tenant_slugs:
                # Prefer multi-tenant layout when tenants exist.
                # Root-level chroma_db/config are just scaffolding in
                # multi-tenant backups and should not override detection.
                source_slug = sorted(tenant_slugs)[0]
                if len(tenant_slugs) > 1:
                    logger.warning(
                        f"Multiple tenants found in backup: {tenant_slugs}. "
                        f"Using '{source_slug}'."
                    )
                return f"data/tenants/{source_slug}/", source_slug

        return "data/", None

    def validate_backup(self, zip_path: Path) -> dict:
        """
        Validate a backup ZIP for tenant import.

        Checks ZIP structure, path safety, and presence of importable content.
        Supports both single-tenant (data/...) and multi-tenant
        (data/tenants/{slug}/...) backup layouts.

        Returns:
            dict with keys: valid, errors, warnings, file_count, total_size,
            has_documents, has_chromadb, has_config, document_count,
            data_root, source_slug.
        """
        result = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "file_count": 0,
            "total_size": 0,
            "has_documents": False,
            "has_chromadb": False,
            "has_config": False,
            "document_count": 0,
            "data_root": "data/",
            "source_slug": None,
        }

        if not zip_path.exists():
            result["errors"].append(f"File not found: {zip_path}")
            return result

        if not zipfile.is_zipfile(zip_path):
            result["errors"].append("File is not a valid ZIP archive")
            return result

        try:
            # Detect layout
            data_root, source_slug = self._detect_data_root(zip_path)
            result["data_root"] = data_root
            result["source_slug"] = source_slug

            if source_slug:
                result["warnings"].append(
                    f"Multi-tenant backup detected (source tenant: '{source_slug}')"
                )

            with zipfile.ZipFile(zip_path, "r") as zf:
                doc_count = 0
                has_chroma = False
                has_config = False
                has_docs = False

                for info in zf.infolist():
                    name = info.filename

                    # Safety: reject path traversal
                    if ".." in name or name.startswith("/"):
                        result["errors"].append(f"Path traversal detected: {name}")
                        continue

                    # All entries must start with data/
                    if not name.startswith("data/"):
                        result["errors"].append(f"Entry outside data/ prefix: {name}")
                        continue

                    # Skip directories
                    if info.is_dir():
                        continue

                    result["file_count"] += 1
                    result["total_size"] += info.file_size

                    # Check for ZIP bomb
                    if result["total_size"] > MAX_IMPORT_SIZE:
                        result["errors"].append(
                            f"Uncompressed size exceeds {MAX_IMPORT_SIZE // (1024**3)} GB limit"
                        )
                        return result

                    # Only inspect files under the detected data root
                    if not name.startswith(data_root):
                        continue

                    # Strip data root prefix for content detection
                    rel = name[len(data_root) :]

                    # Detect content types
                    for doc_dir in DOCUMENT_DIRS:
                        if rel.startswith(doc_dir + "/"):
                            has_docs = True
                            doc_count += 1

                    if rel.startswith("chroma_db/"):
                        has_chroma = True

                    if rel.startswith("config/"):
                        has_config = True

                    # Skip backups dir
                    if rel.startswith("backups/"):
                        result["warnings"].append(
                            "Backup contains nested backups (will be skipped)"
                        )

                result["has_documents"] = has_docs
                result["has_chromadb"] = has_chroma
                result["has_config"] = has_config
                result["document_count"] = doc_count

                if not has_docs and not has_chroma:
                    result["errors"].append(
                        "No importable content found (need documents or chroma_db)"
                    )

                if not result["errors"]:
                    result["valid"] = True

        except zipfile.BadZipFile:
            result["errors"].append("Corrupted ZIP file")
        except Exception as e:
            result["errors"].append(f"Validation error: {e}")

        return result

    def import_tenant(
        self,
        zip_path: Path,
        slug: str,
        name: str,
        admin_email: str,
        description: Optional[str] = None,
        organization: Optional[str] = None,
        skip_chromadb: bool = False,
        skip_conversations: bool = False,
    ) -> dict:
        """
        Import a single-tenant backup as a new tenant.

        Steps:
        1. Validate backup
        2. Extract to temp directory
        3. Create tenant via provisioner
        4. Upload documents to S3
        5. Copy and rename ChromaDB collection
        6. Optionally migrate conversations
        7. Rollback on failure

        Returns:
            dict with keys: success, slug, documents_uploaded, chromadb_imported,
            conversations_migrated, config_applied, errors.
        """
        result = {
            "success": False,
            "slug": slug,
            "documents_uploaded": 0,
            "chromadb_imported": False,
            "conversations_migrated": 0,
            "config_applied": False,
            "errors": [],
        }

        # Step 1: Validate
        validation = self.validate_backup(zip_path)
        if not validation["valid"]:
            result["errors"] = validation["errors"]
            return result

        tenant_created = False
        temp_dir = None

        try:
            # Step 2: Extract ZIP to temp directory
            temp_dir = Path(tempfile.mkdtemp(prefix="berengario_import_"))
            logger.info(f"Extracting backup to {temp_dir}")

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            # Resolve the data root within the extracted directory
            # For single-tenant: data/  For multi-tenant: data/tenants/{slug}/
            data_root = validation.get("data_root", "data/")
            extracted_data = temp_dir / data_root.rstrip("/")
            if not extracted_data.is_dir():
                result["errors"].append(f"Data root not found in backup: {data_root}")
                return result

            # Step 3: Read config files for tenant creation
            custom_prompt = None
            custom_prompt_file = extracted_data / "config" / "custom_prompt.txt"
            if custom_prompt_file.exists():
                custom_prompt = custom_prompt_file.read_text(encoding="utf-8").strip()
                result["config_applied"] = True
                logger.info("Found custom prompt in backup")

            # Step 4: Create tenant via provisioner
            logger.info(f"Creating tenant: slug={slug}, name={name}")
            self.provisioner.create_tenant(
                slug=slug,
                name=name,
                admin_email=admin_email,
                description=description,
                organization=organization,
                custom_prompt=custom_prompt,
            )
            tenant_created = True

            # Step 5: Upload documents to S3
            docs_uploaded = self._upload_documents_to_s3(extracted_data, slug)
            result["documents_uploaded"] = docs_uploaded

            # Step 6: Copy and rename ChromaDB
            if not skip_chromadb and validation["has_chromadb"]:
                chroma_src = extracted_data / "chroma_db"
                if chroma_src.is_dir():
                    self._import_chromadb(chroma_src, slug)
                    result["chromadb_imported"] = True

            # Step 7: Migrate conversations
            if not skip_conversations:
                tracker_db = extracted_data / "message_tracker.db"
                if tracker_db.exists():
                    count = self._migrate_conversations(tracker_db, slug)
                    result["conversations_migrated"] = count

            result["success"] = True
            logger.info(
                f"Tenant import completed: slug={slug}, "
                f"docs={docs_uploaded}, chromadb={result['chromadb_imported']}"
            )

        except Exception as e:
            logger.error(f"Import failed for {slug}: {e}", exc_info=True)
            result["errors"].append(str(e))

            # Rollback: delete tenant if it was created
            if tenant_created:
                logger.warning(f"Rolling back: deleting tenant {slug}")
                try:
                    self.provisioner.delete_tenant(slug, crypto_shred=False)
                except Exception as rollback_err:
                    logger.error(f"Rollback failed: {rollback_err}")
                    result["errors"].append(f"Rollback failed: {rollback_err}")

        finally:
            # Always clean up temp directory
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temp dir: {temp_dir}")

        return result

    def _upload_documents_to_s3(self, extracted_data: Path, slug: str) -> int:
        """
        Upload documents from extracted backup to tenant storage.

        Walks kb/documents/, kb/emails/, and documents/ directories
        and uploads each file via the storage backend.

        Returns:
            Number of files uploaded.
        """
        uploaded = 0

        for doc_dir in DOCUMENT_DIRS:
            source_dir = extracted_data / doc_dir
            if not source_dir.is_dir():
                continue

            for file_path in source_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                # Key is relative to extracted_data (e.g., "kb/documents/report.pdf")
                key = str(file_path.relative_to(extracted_data))
                data = file_path.read_bytes()

                try:
                    self.storage.put(slug, key, data)
                    uploaded += 1
                    logger.debug(f"Uploaded: {key} ({len(data)} bytes)")
                except Exception as e:
                    logger.error(f"Failed to upload {key}: {e}")
                    raise

        logger.info(f"Uploaded {uploaded} documents for tenant {slug}")
        return uploaded

    def _import_chromadb(self, chroma_src: Path, slug: str) -> None:
        """
        Copy ChromaDB from backup to local cache and rename the collection.

        ChromaDB always lives locally (even with S3 storage) at:
        data/cache/{slug}/chroma_db/

        The collection is renamed from its original name to {slug}_kb
        (the multi-tenant convention).
        """
        chroma_dest = Path(f"data/cache/{slug}/chroma_db")
        chroma_dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy the entire chroma_db directory
        if chroma_dest.exists():
            shutil.rmtree(chroma_dest)
        shutil.copytree(chroma_src, chroma_dest)
        logger.info(f"Copied ChromaDB to {chroma_dest}")

        # Rename collection
        new_name = f"{slug}_kb"
        self._rename_chromadb_collection(chroma_dest, new_name)

    @staticmethod
    def _rename_chromadb_collection(chroma_path: Path, new_name: str) -> None:
        """
        Rename the ChromaDB collection via direct SQLite UPDATE.

        ChromaDB stores collection metadata in chroma.sqlite3.
        This renames the single collection to the new name without
        touching embeddings or other data.

        Args:
            chroma_path: Path to the chroma_db directory.
            new_name: New collection name (e.g., "my-tenant_kb").
        """
        sqlite_file = chroma_path / "chroma.sqlite3"
        if not sqlite_file.exists():
            logger.warning(f"ChromaDB SQLite file not found: {sqlite_file}")
            return

        conn = sqlite3.connect(str(sqlite_file))
        try:
            cursor = conn.cursor()

            # Check how many collections exist
            cursor.execute("SELECT id, name FROM collections")
            collections = cursor.fetchall()

            if not collections:
                logger.warning("No collections found in ChromaDB")
                return

            if len(collections) > 1:
                logger.warning(
                    f"Multiple collections found ({len(collections)}), "
                    f"renaming all to {new_name}"
                )

            old_names = [c[1] for c in collections]
            cursor.execute(
                "UPDATE collections SET name = ?",
                (new_name,),
            )
            conn.commit()
            logger.info(f"Renamed ChromaDB collection(s): {old_names} -> {new_name}")
        finally:
            conn.close()

    def _migrate_conversations(self, tracker_db: Path, slug: str) -> int:
        """
        Migrate conversations from single-tenant SQLite to tenant MariaDB.

        Reads ProcessedMessage and Conversation/ConversationMessage records
        from the backup's message_tracker.db and inserts them into the
        tenant's MariaDB database.

        Returns:
            Number of records migrated.
        """
        db_name = f"berengario_tenant_{slug.replace('-', '_')}"
        migrated = 0

        try:
            # Read from SQLite backup
            conn = sqlite3.connect(str(tracker_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check which tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            # Migrate processed_messages
            if "processed_messages" in tables:
                cursor.execute("SELECT * FROM processed_messages")
                rows = cursor.fetchall()

                if rows:
                    from src.email.db_models import ProcessedMessage

                    with self.db_manager.get_tenant_session_by_name(db_name) as session:
                        for row in rows:
                            msg = ProcessedMessage(
                                message_id=row["message_id"],
                                sender=row["sender"],
                                subject=(
                                    row["subject"] if "subject" in row.keys() else None
                                ),
                                status=(
                                    row["status"]
                                    if "status" in row.keys()
                                    else "success"
                                ),
                                attachment_count=(
                                    row["attachment_count"]
                                    if "attachment_count" in row.keys()
                                    else 0
                                ),
                                chunks_created=(
                                    row["chunks_created"]
                                    if "chunks_created" in row.keys()
                                    else 0
                                ),
                            )
                            session.merge(msg)
                            migrated += 1

            # Migrate conversations and messages
            if "conversations" in tables and "conversation_messages" in tables:
                from src.email.db_models import (
                    ChannelType,
                    Conversation,
                    ConversationMessage,
                    MessageType,
                )

                cursor.execute("SELECT * FROM conversations")
                conv_rows = cursor.fetchall()

                cursor.execute("SELECT * FROM conversation_messages")
                msg_rows = cursor.fetchall()

                if conv_rows or msg_rows:
                    with self.db_manager.get_tenant_session_by_name(db_name) as session:
                        # Map old IDs to new IDs
                        id_map = {}
                        for row in conv_rows:
                            conv = Conversation(
                                thread_id=row["thread_id"],
                                sender=row["sender"],
                                channel=(
                                    ChannelType(row["channel"])
                                    if "channel" in row.keys()
                                    else ChannelType.EMAIL
                                ),
                            )
                            session.add(conv)
                            session.flush()
                            id_map[row["id"]] = conv.id
                            migrated += 1

                        for row in msg_rows:
                            old_conv_id = row["conversation_id"]
                            new_conv_id = id_map.get(old_conv_id)
                            if new_conv_id is None:
                                logger.warning(
                                    f"Skipping message with unknown conversation_id: {old_conv_id}"
                                )
                                continue

                            msg = ConversationMessage(
                                conversation_id=new_conv_id,
                                message_type=MessageType(row["message_type"]),
                                content=row["content"],
                                sender=row["sender"],
                                subject=(
                                    row["subject"] if "subject" in row.keys() else None
                                ),
                                message_order=(
                                    row["message_order"]
                                    if "message_order" in row.keys()
                                    else 0
                                ),
                            )
                            session.add(msg)
                            migrated += 1

            conn.close()
            logger.info(f"Migrated {migrated} records for tenant {slug}")

        except Exception as e:
            logger.warning(f"Conversation migration failed (non-fatal): {e}")
            # Non-fatal: conversations are optional

        return migrated
