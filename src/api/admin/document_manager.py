"""
Document Manager for admin interface.

Handles document listing, uploading, deletion, and archival operations.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    Manager for document operations in the admin interface.

    Handles:
    - Listing documents from knowledge base
    - Uploading new documents
    - Deleting documents (move to archive + remove from KB)
    - Bulk operations
    """

    # Supported file types
    SUPPORTED_TYPES = {
        ".pdf": "PDF",
        ".docx": "DOCX",
        ".doc": "DOC",
        ".txt": "TXT",
        ".csv": "CSV",
    }

    # Maximum file sizes (in bytes)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB per file
    MAX_BATCH_SIZE = 200 * 1024 * 1024  # 200MB per batch

    def __init__(self, kb_manager, document_processor, base_path: Path = None):
        """
        Initialize DocumentManager.

        Args:
            kb_manager: KnowledgeBaseManager instance
            document_processor: DocumentProcessor instance
            base_path: Base path for document storage (default: project root)
        """
        from src.config import settings

        self.kb_manager = kb_manager
        self.document_processor = document_processor
        self.base_path = base_path or Path.cwd()

        # Use new KB structure exclusively
        self.kb_documents_path = settings.kb_documents_path
        self.kb_emails_path = settings.kb_emails_path
        self.archive_path = self.base_path / "data" / "kb" / "archive"

        # Ensure directories exist
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self.kb_documents_path.mkdir(parents=True, exist_ok=True)
        self.kb_emails_path.mkdir(parents=True, exist_ok=True)

        logger.info("DocumentManager initialized with KB structure")

    def list_documents(self) -> List[Dict]:
        """
        List all documents in the knowledge base.

        Returns:
            List of document metadata dictionaries with:
                - filename: Document filename
                - file_hash: SHA-256 hash
                - source_type: Source type (file/email)
                - file_type: File extension
                - chunks: Number of chunks (estimated from KB)
                - date_added: Date added (from filesystem if available)
        """
        try:
            # Get unique documents from KB
            documents = self.kb_manager.get_unique_documents()

            # Enhance with filesystem metadata and age calculation
            enhanced_docs = []
            for doc in documents:
                enhanced_doc = doc.copy()

                # Calculate age from file_mtime if available
                file_mtime = doc.get("file_mtime")
                if file_mtime:
                    try:
                        doc_datetime = datetime.fromtimestamp(file_mtime)
                        enhanced_doc["date_added"] = doc_datetime.isoformat()
                        enhanced_doc["age_days"] = (datetime.now() - doc_datetime).days
                    except (ValueError, OSError) as e:
                        logger.warning(
                            f"Invalid timestamp for {doc.get('filename')}: {e}"
                        )
                        enhanced_doc["age_days"] = None
                else:
                    enhanced_doc["age_days"] = None

                # Try to get file size if it exists on filesystem
                file_path = None
                source_type = doc.get("source_type")

                if source_type == "email":
                    # Email text files in KB emails path
                    candidate = self.kb_emails_path / doc["filename"]
                    if candidate.exists():
                        file_path = candidate
                else:
                    # All other documents (attachments, manual uploads, files) in KB documents path
                    candidate = self.kb_documents_path / doc["filename"]
                    if candidate.exists():
                        file_path = candidate

                if file_path:
                    stats = file_path.stat()
                    enhanced_doc["size_bytes"] = stats.st_size

                # Add estimated chunk count (would need KB query)
                enhanced_doc["chunks"] = "?"  # Placeholder

                enhanced_docs.append(enhanced_doc)

            logger.info(f"Listed {len(enhanced_docs)} documents")
            return enhanced_docs

        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise

    def delete_document(self, file_hash: str, archive: bool = True) -> Dict[str, any]:
        """
        Delete document from KB and optionally archive the file.

        Args:
            file_hash: SHA-256 hash of document to delete
            archive: If True, move file to archive; if False, delete permanently

        Returns:
            Dictionary with:
                - success: Whether operation succeeded
                - filename: Name of deleted file
                - archived: Whether file was archived
                - chunks_removed: Number of chunks removed from KB
        """
        try:
            # Get document info before deletion
            docs = self.kb_manager.get_unique_documents()
            doc = next((d for d in docs if d.get("file_hash") == file_hash), None)

            if not doc:
                raise ValueError(f"Document not found with hash: {file_hash}")

            filename = doc["filename"]
            source_type = doc.get("source_type", "unknown")

            # Delete from KB
            chunks_removed = self.kb_manager.delete_document_by_hash(file_hash)

            # Handle file archival/deletion
            archived = False
            file_path = None

            # Find the file in appropriate location based on source_type
            if source_type == "email":
                # Email text files in KB emails path
                candidate = self.kb_emails_path / filename
                if candidate.exists():
                    file_path = candidate
            else:
                # All other documents in KB documents path
                candidate = self.kb_documents_path / filename
                if candidate.exists():
                    file_path = candidate

            if file_path:
                if archive:
                    # Move to archive
                    archive_file = (
                        self.archive_path
                        / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                    )
                    shutil.move(str(file_path), str(archive_file))
                    archived = True
                    logger.info(f"Archived file: {filename} -> {archive_file.name}")
                else:
                    # Permanent deletion
                    file_path.unlink()
                    logger.info(f"Permanently deleted file: {filename}")
            else:
                logger.warning(f"Source file not found: {filename}")

            logger.info(f"Deleted document: {filename} ({chunks_removed} chunks)")

            return {
                "success": True,
                "filename": filename,
                "archived": archived,
                "chunks_removed": chunks_removed,
                "file_hash": file_hash,
            }

        except Exception as e:
            logger.error(f"Error deleting document {file_hash}: {e}")
            raise

    def bulk_delete(
        self, file_hashes: List[str], archive: bool = True
    ) -> Dict[str, any]:
        """
        Delete multiple documents in bulk.

        Args:
            file_hashes: List of file hashes to delete
            archive: If True, archive files; if False, delete permanently

        Returns:
            Dictionary with:
                - success: Whether all operations succeeded
                - deleted: List of successfully deleted files
                - failed: List of failed deletions with errors
                - total_chunks_removed: Total chunks removed
        """
        deleted = []
        failed = []
        total_chunks = 0

        for file_hash in file_hashes:
            try:
                result = self.delete_document(file_hash, archive=archive)
                deleted.append(result)
                total_chunks += result["chunks_removed"]
            except Exception as e:
                failed.append(
                    {
                        "file_hash": file_hash,
                        "error": str(e),
                    }
                )
                logger.error(f"Failed to delete {file_hash}: {e}")

        logger.info(
            f"Bulk delete complete: {len(deleted)} succeeded, "
            f"{len(failed)} failed, {total_chunks} chunks removed"
        )

        return {
            "success": len(failed) == 0,
            "deleted": deleted,
            "failed": failed,
            "total_chunks_removed": total_chunks,
        }

    def upload_document(
        self, filename: str, content: bytes, process: bool = True
    ) -> Dict[str, any]:
        """
        Upload and process a new document.

        Args:
            filename: Name of the file
            content: File content as bytes
            process: If True, process into KB immediately

        Returns:
            Dictionary with:
                - success: Whether operation succeeded
                - filename: Saved filename
                - file_path: Path where file was saved
                - size_bytes: File size
                - processed: Whether file was processed into KB
                - chunks_added: Number of chunks added (if processed)
        """
        # Validate file type
        file_ext = Path(filename).suffix.lower()
        if file_ext not in self.SUPPORTED_TYPES:
            raise ValueError(
                f"Unsupported file type: {file_ext}. "
                f"Supported: {', '.join(self.SUPPORTED_TYPES.keys())}"
            )

        # Validate file size
        if len(content) > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {len(content)} bytes. "
                f"Maximum: {self.MAX_FILE_SIZE} bytes"
            )

        # Sanitize filename (remove path components)
        safe_filename = Path(filename).name

        # Check if file already exists
        file_path = self.kb_documents_path / safe_filename
        if file_path.exists():
            # Add timestamp to avoid overwriting
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name_parts = safe_filename.rsplit(".", 1)
            safe_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            file_path = self.kb_documents_path / safe_filename

        try:
            # Save file
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Saved uploaded file: {safe_filename} ({len(content)} bytes)")

            # Process into KB if requested
            chunks_added = 0
            if process:
                try:
                    # Process document into chunks
                    nodes = self.document_processor.process_document(
                        file_path,
                        source_type="manual",
                        extra_metadata={"uploaded_via": "admin_interface"},
                    )

                    # Add chunks to knowledge base
                    if nodes:
                        self.kb_manager.add_documents(nodes)
                        chunks_added = len(nodes)
                        logger.info(
                            f"Processed document into KB: {safe_filename} ({chunks_added} chunks)"
                        )

                        # Generate and save document description
                        try:
                            from src.document_processing.description_generator import (
                                description_generator,
                            )

                            # Calculate relative path from project root
                            relative_path = str(file_path.relative_to(self.base_path))

                            description_generator.generate_and_save(
                                file_path=relative_path,
                                filename=safe_filename,
                                chunks=nodes,
                                file_size=len(content),
                                file_type=file_ext.lstrip("."),
                            )
                            logger.info(f"Generated description for: {safe_filename}")
                        except Exception as e:
                            # Don't fail the upload if description generation fails
                            logger.error(
                                f"Error generating description: {e}", exc_info=True
                            )
                    else:
                        logger.warning(f"No chunks extracted from {safe_filename}")
                except Exception as e:
                    logger.error(f"Error processing document: {e}")
                    # Keep file but note processing failed
                    raise

            return {
                "success": True,
                "filename": safe_filename,
                "file_path": str(file_path),
                "size_bytes": len(content),
                "processed": process,
                "chunks_added": chunks_added,
            }

        except Exception as e:
            # Cleanup on error
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            logger.error(f"Error uploading document: {e}")
            raise

    def validate_file(self, filename: str, size: int) -> Tuple[bool, str]:
        """
        Validate file before upload.

        Args:
            filename: Name of file
            size: Size in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file type
        file_ext = Path(filename).suffix.lower()
        if file_ext not in self.SUPPORTED_TYPES:
            return False, f"Unsupported file type: {file_ext}"

        # Check size
        if size > self.MAX_FILE_SIZE:
            return False, f"File too large: {size} bytes (max: {self.MAX_FILE_SIZE})"

        return True, ""

    def get_stats(self) -> Dict[str, any]:
        """
        Get document statistics.

        Returns:
            Dictionary with statistics about documents
        """
        try:
            docs = self.list_documents()

            # Count by type
            type_counts = {}
            total_size = 0

            for doc in docs:
                file_type = doc.get("file_type", "unknown")
                type_counts[file_type] = type_counts.get(file_type, 0) + 1
                total_size += doc.get("size_bytes", 0)

            # Count archived files
            archived_count = (
                len(list(self.archive_path.glob("*")))
                if self.archive_path.exists()
                else 0
            )

            return {
                "total_documents": len(docs),
                "by_type": type_counts,
                "total_size_bytes": total_size,
                "archived_count": archived_count,
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            raise
