"""
Unit tests for attachment archival functionality.

Tests the archive_attachments method to ensure email attachments are
permanently saved to the documents folder.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.email.attachment_handler import AttachmentHandler, AttachmentInfo


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    docs_dir = Path(tempfile.mkdtemp())

    yield temp_dir, docs_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.rmtree(docs_dir, ignore_errors=True)


@pytest.fixture
def attachment_handler(temp_dirs):
    """Create attachment handler with test directories."""
    temp_dir, _ = temp_dirs
    return AttachmentHandler(temp_dir=temp_dir)


def test_archive_single_attachment(attachment_handler, temp_dirs):
    """Test archiving a single attachment."""
    temp_dir, docs_dir = temp_dirs

    # Create a test file
    test_file = temp_dir / "test_doc.pdf"
    test_file.write_text("Test content")

    attachment = AttachmentInfo(
        filename="test_doc.pdf",
        filepath=test_file,
        size=12,
        mime_type="application/pdf",
        extension=".pdf"
    )

    # Archive the attachment
    archived = attachment_handler.archive_attachments([attachment], docs_dir)

    # Verify
    assert archived == 1
    assert (docs_dir / "test_doc.pdf").exists()
    assert (docs_dir / "test_doc.pdf").read_text() == "Test content"


def test_archive_identical_file_not_duplicated(attachment_handler, temp_dirs):
    """Test that identical files are detected and not duplicated."""
    temp_dir, docs_dir = temp_dirs

    # Create identical file in both locations
    test_content = "Identical content"
    existing_file = docs_dir / "existing.pdf"
    existing_file.write_text(test_content)

    new_file = temp_dir / "existing.pdf"
    new_file.write_text(test_content)

    attachment = AttachmentInfo(
        filename="existing.pdf",
        filepath=new_file,
        size=len(test_content),
        mime_type="application/pdf",
        extension=".pdf"
    )

    # Archive the attachment
    archived = attachment_handler.archive_attachments([attachment], docs_dir)

    # Verify - should be counted as archived but not create duplicate
    assert archived == 1
    # Only one file should exist (no timestamp suffix)
    files = list(docs_dir.glob("existing*.pdf"))
    assert len(files) == 1
    assert files[0].name == "existing.pdf"


def test_archive_different_file_gets_timestamp(attachment_handler, temp_dirs):
    """Test that different files with same name get timestamp suffix."""
    temp_dir, docs_dir = temp_dirs

    # Create different file in docs folder
    existing_file = docs_dir / "document.pdf"
    existing_file.write_text("Original content")

    # Create new file with same name but different content
    new_file = temp_dir / "document.pdf"
    new_file.write_text("New content")

    attachment = AttachmentInfo(
        filename="document.pdf",
        filepath=new_file,
        size=11,
        mime_type="application/pdf",
        extension=".pdf"
    )

    # Archive the attachment
    archived = attachment_handler.archive_attachments([attachment], docs_dir)

    # Verify
    assert archived == 1
    # Two files should exist - original and timestamped
    files = list(docs_dir.glob("document*.pdf"))
    assert len(files) == 2

    # Check original still exists
    assert existing_file.exists()
    assert existing_file.read_text() == "Original content"

    # Check new file has timestamp suffix
    timestamped_files = [f for f in files if f.name != "document.pdf"]
    assert len(timestamped_files) == 1
    assert timestamped_files[0].read_text() == "New content"


def test_archive_multiple_attachments(attachment_handler, temp_dirs):
    """Test archiving multiple attachments at once."""
    temp_dir, docs_dir = temp_dirs

    # Create multiple test files
    attachments = []
    for i in range(3):
        test_file = temp_dir / f"doc_{i}.pdf"
        test_file.write_text(f"Content {i}")

        attachment = AttachmentInfo(
            filename=f"doc_{i}.pdf",
            filepath=test_file,
            size=9,
            mime_type="application/pdf",
            extension=".pdf"
        )
        attachments.append(attachment)

    # Archive all attachments
    archived = attachment_handler.archive_attachments(attachments, docs_dir)

    # Verify
    assert archived == 3
    for i in range(3):
        assert (docs_dir / f"doc_{i}.pdf").exists()
        assert (docs_dir / f"doc_{i}.pdf").read_text() == f"Content {i}"


def test_archive_missing_file_skipped(attachment_handler, temp_dirs):
    """Test that missing files are skipped gracefully."""
    temp_dir, docs_dir = temp_dirs

    # Create attachment info for non-existent file
    attachment = AttachmentInfo(
        filename="missing.pdf",
        filepath=temp_dir / "missing.pdf",
        size=100,
        mime_type="application/pdf",
        extension=".pdf"
    )

    # Archive should skip missing file
    archived = attachment_handler.archive_attachments([attachment], docs_dir)

    # Verify
    assert archived == 0
    assert not (docs_dir / "missing.pdf").exists()


def test_archive_creates_docs_folder(attachment_handler, temp_dirs):
    """Test that archive creates documents folder if it doesn't exist."""
    temp_dir, _ = temp_dirs

    # Use non-existent docs directory
    docs_dir = temp_dir / "non_existent_docs"
    assert not docs_dir.exists()

    # Create test file
    test_file = temp_dir / "test.pdf"
    test_file.write_text("Test")

    attachment = AttachmentInfo(
        filename="test.pdf",
        filepath=test_file,
        size=4,
        mime_type="application/pdf",
        extension=".pdf"
    )

    # Archive should create the directory
    archived = attachment_handler.archive_attachments([attachment], docs_dir)

    # Verify
    assert archived == 1
    assert docs_dir.exists()
    assert (docs_dir / "test.pdf").exists()
