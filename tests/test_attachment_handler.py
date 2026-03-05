"""
Unit tests for attachment handler.

Tests attachment extraction, validation, and file management.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from src.email.attachment_handler import (
    SUPPORTED_EXTENSIONS,
    AttachmentHandler,
    AttachmentInfo,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def handler(temp_dir):
    """Create attachment handler with temp directory."""
    return AttachmentHandler(temp_dir=temp_dir, max_size=10 * 1024 * 1024)  # 10MB


def create_mock_attachment(
    filename="test.pdf", content=b"test content", content_type="application/pdf"
):
    """Create mock attachment."""
    att = MagicMock()
    att.filename = filename
    att.payload = content
    att.content_type = content_type
    return att


class TestAttachmentHandler:
    """Tests for AttachmentHandler class."""

    def test_init_creates_temp_dir(self, temp_dir):
        """Test initialization creates temp directory."""
        _ = AttachmentHandler(temp_dir=temp_dir / "new_dir")

        assert (temp_dir / "new_dir").exists()

    def test_validate_file_type_pdf(self, handler):
        """Test validation of PDF files."""
        assert handler.validate_file_type("document.pdf", "application/pdf") is True

    def test_validate_file_type_docx(self, handler):
        """Test validation of DOCX files."""
        assert (
            handler.validate_file_type(
                "document.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            is True
        )

    def test_validate_file_type_txt(self, handler):
        """Test validation of text files."""
        assert handler.validate_file_type("document.txt", "text/plain") is True

    def test_validate_file_type_unsupported_extension(self, handler):
        """Test rejection of unsupported file extension."""
        assert handler.validate_file_type("malware.exe", "") is False

    def test_validate_file_type_unsupported_mime(self, handler):
        """Test rejection of unsupported MIME type."""
        assert (
            handler.validate_file_type("test.pdf", "application/x-executable") is False
        )

    def test_validate_file_type_mime_with_charset(self, handler):
        """Test MIME type validation with charset parameter."""
        assert (
            handler.validate_file_type("test.txt", "text/plain; charset=utf-8") is True
        )

    def test_validate_file_size_within_limit(self, handler):
        """Test file size within limit."""
        size = 5 * 1024 * 1024  # 5MB
        assert handler.validate_file_size(size, "test.pdf") is True

    def test_validate_file_size_exceeds_limit(self, handler):
        """Test file size exceeds limit."""
        size = 15 * 1024 * 1024  # 15MB (over 10MB limit)
        assert handler.validate_file_size(size, "huge.pdf") is False

    def test_validate_file_size_at_limit(self, handler):
        """Test file size exactly at limit."""
        size = 10 * 1024 * 1024  # Exactly 10MB
        assert handler.validate_file_size(size, "test.pdf") is True

    def test_extract_attachments_none(self, handler):
        """Test extraction with no attachments."""
        message = MagicMock()
        message.attachments = []

        attachments = handler.extract_attachments(message, "test@example.com")

        assert len(attachments) == 0

    def test_extract_attachments_single_pdf(self, handler):
        """Test extraction of single PDF attachment."""
        mock_att = create_mock_attachment("document.pdf", b"PDF content")
        message = MagicMock()
        message.attachments = [mock_att]

        attachments = handler.extract_attachments(message, "msg_123")

        assert len(attachments) == 1
        assert attachments[0].filename == "document.pdf"
        assert attachments[0].size == len(b"PDF content")
        assert attachments[0].filepath.exists()
        assert attachments[0].filepath.read_bytes() == b"PDF content"

    def test_extract_attachments_multiple_files(self, handler):
        """Test extraction of multiple attachments."""
        mock_att1 = create_mock_attachment("doc1.pdf", b"Content 1")
        mock_att2 = create_mock_attachment(
            "doc2.docx",
            b"Content 2",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        message = MagicMock()
        message.attachments = [mock_att1, mock_att2]

        attachments = handler.extract_attachments(message, "msg_123")

        assert len(attachments) == 2
        assert attachments[0].filename == "doc1.pdf"
        assert attachments[1].filename == "doc2.docx"

    def test_extract_attachments_unsupported_type(self, handler):
        """Test extraction skips unsupported file types."""
        mock_att1 = create_mock_attachment("document.pdf", b"PDF content")
        mock_att2 = create_mock_attachment(
            "malware.exe", b"Bad content", "application/x-executable"
        )
        message = MagicMock()
        message.attachments = [mock_att1, mock_att2]

        attachments = handler.extract_attachments(message, "msg_123")

        # Only PDF should be extracted
        assert len(attachments) == 1
        assert attachments[0].filename == "document.pdf"

    def test_extract_attachments_oversized_file(self, handler):
        """Test extraction skips oversized files."""
        small_content = b"Small" * 100
        large_content = b"X" * (15 * 1024 * 1024)  # 15MB

        mock_att1 = create_mock_attachment("small.pdf", small_content)
        mock_att2 = create_mock_attachment("large.pdf", large_content)
        message = MagicMock()
        message.attachments = [mock_att1, mock_att2]

        attachments = handler.extract_attachments(message, "msg_123")

        # Only small file should be extracted
        assert len(attachments) == 1
        assert attachments[0].filename == "small.pdf"

    def test_extract_attachments_duplicate_filename(self, handler):
        """Test extraction handles duplicate filenames."""
        mock_att1 = create_mock_attachment("document.pdf", b"Content 1")
        mock_att2 = create_mock_attachment("document.pdf", b"Content 2")
        message = MagicMock()
        message.attachments = [mock_att1, mock_att2]

        attachments = handler.extract_attachments(message, "msg_123")

        assert len(attachments) == 2
        # Second file should have counter
        assert attachments[0].filepath.name == "document.pdf"
        assert attachments[1].filepath.name == "document_1.pdf"

    def test_extract_attachments_creates_subdirectory(self, handler, temp_dir):
        """Test extraction creates message-specific subdirectory."""
        mock_att = create_mock_attachment("doc.pdf", b"Content")
        message = MagicMock()
        message.attachments = [mock_att]

        attachments = handler.extract_attachments(message, "msg_123")

        # Check subdirectory was created
        assert attachments[0].filepath.parent != temp_dir
        assert attachments[0].filepath.parent.parent == temp_dir

    def test_sanitize_filename_unsafe_chars(self, handler):
        """Test filename sanitization removes unsafe characters."""
        unsafe = "file<name>:with/bad\\chars|?.pdf"
        safe = handler._sanitize_filename(unsafe)

        assert "<" not in safe
        assert ">" not in safe
        assert ":" not in safe
        assert "/" not in safe
        assert "\\" not in safe

    def test_sanitize_filename_long_name(self, handler):
        """Test filename sanitization truncates long names."""
        long_name = "a" * 300 + ".pdf"
        safe = handler._sanitize_filename(long_name)

        assert len(safe) <= 255
        assert safe.endswith(".pdf")

    def test_cleanup_attachments_single(self, handler):
        """Test cleanup of single attachment."""
        mock_att = create_mock_attachment("doc.pdf", b"Content")
        message = MagicMock()
        message.attachments = [mock_att]

        attachments = handler.extract_attachments(message, "msg_123")
        filepath = attachments[0].filepath

        assert filepath.exists()

        deleted = handler.cleanup_attachments(attachments)

        assert deleted == 1
        assert not filepath.exists()

    def test_cleanup_attachments_multiple(self, handler):
        """Test cleanup of multiple attachments."""
        mock_att1 = create_mock_attachment("doc1.pdf", b"Content 1")
        mock_att2 = create_mock_attachment("doc2.pdf", b"Content 2")
        message = MagicMock()
        message.attachments = [mock_att1, mock_att2]

        attachments = handler.extract_attachments(message, "msg_123")

        deleted = handler.cleanup_attachments(attachments)

        assert deleted == 2
        for att in attachments:
            assert not att.filepath.exists()

    def test_cleanup_attachments_removes_empty_directory(self, handler):
        """Test cleanup removes empty parent directory."""
        mock_att = create_mock_attachment("doc.pdf", b"Content")
        message = MagicMock()
        message.attachments = [mock_att]

        attachments = handler.extract_attachments(message, "msg_123")
        parent_dir = attachments[0].filepath.parent

        assert parent_dir.exists()

        handler.cleanup_attachments(attachments)

        # Parent directory should be removed if empty
        assert not parent_dir.exists()

    def test_cleanup_old_temp_files(self, handler, temp_dir):
        """Test cleanup of old temporary files."""
        import time

        # Create old file
        old_file = temp_dir / "old_file.txt"
        old_file.write_text("old content")

        # Set modification time to 10 days ago
        old_time = time.time() - (10 * 86400)
        import os

        os.utime(old_file, (old_time, old_time))

        # Create recent file
        recent_file = temp_dir / "recent_file.txt"
        recent_file.write_text("recent content")

        assert old_file.exists()
        assert recent_file.exists()

        # Cleanup files older than 7 days
        deleted = handler.cleanup_old_temp_files(days=7)

        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_get_temp_dir_size(self, handler, temp_dir):
        """Test getting total size of temp directory."""
        # Create some files
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        file1.write_bytes(b"x" * 1000)
        file2.write_bytes(b"y" * 2000)

        size = handler.get_temp_dir_size()

        assert size == 3000

    def test_get_temp_dir_size_empty(self, handler, temp_dir):
        """Test getting size of empty directory."""
        size = handler.get_temp_dir_size()

        assert size == 0

    def test_extract_attachments_no_filename(self, handler):
        """Test extraction with missing filename uses default."""
        # When filename is missing, it gets default "attachment_N" but needs extension
        # For this test, let's verify the handler skips files without valid extensions
        mock_att = create_mock_attachment(filename="", content=b"Content")
        mock_att.filename = ""
        message = MagicMock()
        message.attachments = [mock_att]

        attachments = handler.extract_attachments(message, "msg_123")

        # Should skip due to missing extension
        assert len(attachments) == 0

    def test_attachment_info_repr(self):
        """Test AttachmentInfo string representation."""
        info = AttachmentInfo(
            filename="test.pdf",
            filepath=Path("/tmp/test.pdf"),
            size=1024,
            mime_type="application/pdf",
        )

        repr_str = repr(info)

        assert "test.pdf" in repr_str
        assert "1024" in repr_str

    def test_supported_extensions_includes_common_types(self):
        """Test supported extensions include common document types."""
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS
        assert ".xlsx" in SUPPORTED_EXTENSIONS
        assert ".pptx" not in SUPPORTED_EXTENSIONS
