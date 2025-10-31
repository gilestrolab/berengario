"""
Email attachment handler for document extraction.

This module provides attachment handling with:
- File extraction from email messages
- File type validation
- Size limit enforcement
- Temporary file management
- Cleanup utilities
"""

import logging
import mimetypes
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from imap_tools import MailMessage

from src.config import settings

logger = logging.getLogger(__name__)


# Supported document types
SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".rtf",
    ".odt",
    # Spreadsheets
    ".xls",
    ".xlsx",
    ".csv",
    ".ods",
    # Presentations
    ".ppt",
    ".pptx",
    ".odp",
    # Other
    ".html",
    ".htm",
    ".xml",
    ".json",
}

# MIME types that are allowed
SUPPORTED_MIME_TYPES = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    # Spreadsheets
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/vnd.oasis.opendocument.spreadsheet",
    # Presentations
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.presentation",
    # Other
    "text/html",
    "application/xml",
    "text/xml",
    "application/json",
}


class AttachmentError(Exception):
    """Base exception for attachment handling errors."""
    pass


class FileSizeError(AttachmentError):
    """Exception raised when file size exceeds limit."""
    pass


class FileTypeError(AttachmentError):
    """Exception raised when file type is not supported."""
    pass


class AttachmentInfo:
    """
    Information about a saved attachment.

    Attributes:
        filename: Original filename
        filepath: Path to saved file
        size: File size in bytes
        mime_type: MIME type
        extension: File extension
    """

    def __init__(
        self,
        filename: str,
        filepath: Path,
        size: int,
        mime_type: str = "",
        extension: str = "",
    ):
        """
        Initialize attachment info.

        Args:
            filename: Original filename
            filepath: Path to saved file
            size: File size in bytes
            mime_type: MIME type
            extension: File extension
        """
        self.filename = filename
        self.filepath = filepath
        self.size = size
        self.mime_type = mime_type
        self.extension = extension

    def __repr__(self) -> str:
        """String representation."""
        return f"AttachmentInfo(filename='{self.filename}', size={self.size}, type={self.mime_type})"


class AttachmentHandler:
    """
    Handles email attachments with validation and temporary storage.

    This class extracts attachments from email messages, validates them
    against size and type restrictions, and saves them to a temporary
    directory for processing.

    Attributes:
        temp_dir: Directory for temporary attachment storage
        max_size: Maximum allowed file size in bytes
        supported_extensions: Set of allowed file extensions
        supported_mime_types: Set of allowed MIME types
    """

    def __init__(
        self,
        temp_dir: Optional[Path] = None,
        max_size: Optional[int] = None,
        supported_extensions: Optional[set] = None,
        supported_mime_types: Optional[set] = None,
    ):
        """
        Initialize attachment handler.

        Args:
            temp_dir: Temporary directory path (defaults to settings)
            max_size: Maximum file size in bytes (defaults to settings)
            supported_extensions: Set of allowed extensions (defaults to global)
            supported_mime_types: Set of allowed MIME types (defaults to global)
        """
        self.temp_dir = temp_dir or settings.email_temp_dir
        self.max_size = max_size or settings.max_attachment_size
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS
        self.supported_mime_types = supported_mime_types or SUPPORTED_MIME_TYPES

        # Ensure temp directory exists
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"AttachmentHandler initialized: temp_dir={self.temp_dir}, "
            f"max_size={self.max_size / (1024*1024):.1f}MB"
        )

    def validate_file_type(self, filename: str, content_type: str = "") -> bool:
        """
        Validate file type by extension and MIME type.

        Args:
            filename: Filename to validate
            content_type: MIME type from email

        Returns:
            True if file type is supported, False otherwise.
        """
        # Check extension
        extension = Path(filename).suffix.lower()
        if extension not in self.supported_extensions:
            logger.warning(f"Unsupported file extension: {extension} for {filename}")
            return False

        # Check MIME type if provided
        if content_type:
            # Sometimes MIME type includes charset, e.g., "text/plain; charset=utf-8"
            mime_type = content_type.split(";")[0].strip().lower()
            if mime_type not in self.supported_mime_types:
                logger.warning(f"Unsupported MIME type: {mime_type} for {filename}")
                return False

        return True

    def validate_file_size(self, size: int, filename: str = "") -> bool:
        """
        Validate file size against maximum limit.

        Args:
            size: File size in bytes
            filename: Optional filename for logging

        Returns:
            True if size is within limit, False otherwise.
        """
        if size > self.max_size:
            size_mb = size / (1024 * 1024)
            max_mb = self.max_size / (1024 * 1024)
            logger.warning(
                f"File size ({size_mb:.2f}MB) exceeds limit ({max_mb:.2f}MB): {filename}"
            )
            return False

        return True

    def extract_attachments(
        self, message: MailMessage, message_id: str = ""
    ) -> List[AttachmentInfo]:
        """
        Extract and save attachments from email message.

        Args:
            message: MailMessage from imap-tools
            message_id: Message ID for organizing files

        Returns:
            List of AttachmentInfo for successfully saved attachments.

        Raises:
            AttachmentError: If extraction fails.
        """
        attachments = []

        if not message.attachments:
            logger.debug(f"No attachments in message {message_id}")
            return attachments

        logger.info(f"Processing {len(message.attachments)} attachments from {message_id}")

        # Create message-specific subdirectory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_msg_id = message_id.replace("<", "").replace(">", "").replace("/", "_")[:50]
        msg_dir = self.temp_dir / f"{timestamp}_{safe_msg_id}"
        msg_dir.mkdir(parents=True, exist_ok=True)

        for idx, attachment in enumerate(message.attachments, 1):
            try:
                filename = attachment.filename or f"attachment_{idx}"
                content_type = attachment.content_type or ""
                size = len(attachment.payload)

                logger.debug(
                    f"Attachment {idx}: {filename} ({size} bytes, {content_type})"
                )

                # Validate file type
                if not self.validate_file_type(filename, content_type):
                    logger.warning(f"Skipping unsupported file: {filename}")
                    continue

                # Validate file size
                if not self.validate_file_size(size, filename):
                    logger.warning(f"Skipping oversized file: {filename}")
                    continue

                # Save attachment
                safe_filename = self._sanitize_filename(filename)
                filepath = msg_dir / safe_filename

                # Handle duplicate filenames
                if filepath.exists():
                    base = filepath.stem
                    suffix = filepath.suffix
                    counter = 1
                    while filepath.exists():
                        filepath = msg_dir / f"{base}_{counter}{suffix}"
                        counter += 1

                # Write file
                with open(filepath, "wb") as f:
                    f.write(attachment.payload)

                extension = filepath.suffix.lower()
                info = AttachmentInfo(
                    filename=filename,
                    filepath=filepath,
                    size=size,
                    mime_type=content_type,
                    extension=extension,
                )

                attachments.append(info)
                logger.info(f"Saved attachment: {filepath} ({size} bytes)")

            except Exception as e:
                logger.error(f"Error processing attachment {idx} ({filename}): {e}")
                # Continue with other attachments

        logger.info(f"Extracted {len(attachments)} valid attachments from {message_id}")
        return attachments

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for safe filesystem storage.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename.
        """
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        sanitized = filename
        for char in unsafe_chars:
            sanitized = sanitized.replace(char, "_")

        # Limit length
        if len(sanitized) > 255:
            # Keep extension
            name = Path(sanitized).stem[:240]
            ext = Path(sanitized).suffix
            sanitized = name + ext

        return sanitized

    def archive_attachments(
        self, attachments: List[AttachmentInfo], documents_path: Optional[Path] = None
    ) -> int:
        """
        Archive attachment files to permanent documents folder.

        Copies attachment files from temporary storage to the permanent documents
        folder for future reference and re-processing. Handles filename conflicts
        by appending timestamp suffix.

        Args:
            attachments: List of AttachmentInfo to archive
            documents_path: Path to documents folder (defaults to settings)

        Returns:
            Number of files successfully archived.
        """
        import shutil

        documents_path = documents_path or settings.documents_path
        archived = 0

        # Ensure documents folder exists
        documents_path.mkdir(parents=True, exist_ok=True)

        for attachment in attachments:
            try:
                if not attachment.filepath.exists():
                    logger.warning(f"Attachment file not found for archival: {attachment.filepath}")
                    continue

                # Determine destination filename
                dest_filename = attachment.filepath.name
                dest_path = documents_path / dest_filename

                # Handle filename conflicts by appending timestamp
                if dest_path.exists():
                    # Check if files are identical (same hash)
                    import hashlib
                    with open(attachment.filepath, 'rb') as f1:
                        hash1 = hashlib.sha256(f1.read()).hexdigest()
                    with open(dest_path, 'rb') as f2:
                        hash2 = hashlib.sha256(f2.read()).hexdigest()

                    if hash1 == hash2:
                        logger.info(f"Identical file already exists in documents: {dest_filename}")
                        archived += 1
                        continue

                    # Files differ - add timestamp suffix
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    dest_path = documents_path / f"{stem}_{timestamp}{suffix}"

                    logger.info(f"File exists with different content, archiving as: {dest_path.name}")

                # Copy file to documents folder
                shutil.copy2(attachment.filepath, dest_path)
                archived += 1
                logger.info(f"Archived attachment: {attachment.filename} -> {dest_path}")

            except Exception as e:
                logger.error(f"Error archiving attachment {attachment.filepath}: {e}")

        logger.info(f"Archived {archived}/{len(attachments)} attachments to {documents_path}")
        return archived

    def cleanup_attachments(self, attachments: List[AttachmentInfo]) -> int:
        """
        Delete attachment files from disk.

        Args:
            attachments: List of AttachmentInfo to delete

        Returns:
            Number of files successfully deleted.
        """
        deleted = 0

        for attachment in attachments:
            try:
                if attachment.filepath.exists():
                    attachment.filepath.unlink()
                    deleted += 1
                    logger.debug(f"Deleted attachment: {attachment.filepath}")

                # Try to remove parent directory if empty
                parent = attachment.filepath.parent
                if parent != self.temp_dir and parent.exists():
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                            logger.debug(f"Removed empty directory: {parent}")
                    except OSError:
                        pass  # Directory not empty or other error

            except Exception as e:
                logger.error(f"Error deleting attachment {attachment.filepath}: {e}")

        logger.info(f"Cleaned up {deleted}/{len(attachments)} attachments")
        return deleted

    def cleanup_old_temp_files(self, days: int = 7) -> int:
        """
        Clean up temporary files older than specified days.

        Args:
            days: Delete files older than this many days

        Returns:
            Number of files deleted.
        """
        if not self.temp_dir.exists():
            return 0

        cutoff_time = datetime.now().timestamp() - (days * 86400)
        deleted = 0

        try:
            for item in self.temp_dir.rglob("*"):
                if item.is_file():
                    try:
                        if item.stat().st_mtime < cutoff_time:
                            item.unlink()
                            deleted += 1
                            logger.debug(f"Deleted old temp file: {item}")
                    except Exception as e:
                        logger.error(f"Error deleting old file {item}: {e}")

            # Clean up empty directories
            for item in sorted(self.temp_dir.rglob("*"), reverse=True):
                if item.is_dir() and item != self.temp_dir:
                    try:
                        if not any(item.iterdir()):
                            item.rmdir()
                            logger.debug(f"Removed empty directory: {item}")
                    except OSError:
                        pass

        except Exception as e:
            logger.error(f"Error during temp file cleanup: {e}")

        logger.info(f"Cleaned up {deleted} old temporary files (>{days} days)")
        return deleted

    def get_temp_dir_size(self) -> int:
        """
        Get total size of temporary directory.

        Returns:
            Total size in bytes.
        """
        if not self.temp_dir.exists():
            return 0

        total_size = 0
        for item in self.temp_dir.rglob("*"):
            if item.is_file():
                try:
                    total_size += item.stat().st_size
                except Exception:
                    pass

        return total_size


# Global attachment handler instance
attachment_handler = AttachmentHandler()
