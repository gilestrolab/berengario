import pytest

from src.email.attachment_handler import AttachmentHandler


@pytest.fixture
def attachment_handler(tmp_path):
    return AttachmentHandler(temp_dir=tmp_path)


def test_save_attachment_from_bytes(attachment_handler):
    filename = "test.txt"
    content = b"Hello World"

    info = attachment_handler.save_attachment_from_bytes(filename, content)

    assert info is not None
    assert info.filename == filename
    assert info.size == len(content)
    assert info.filepath.exists()
    assert info.filepath.read_bytes() == content


def test_save_attachment_from_bytes_subdir(attachment_handler):
    filename = "test.txt"
    content = b"Hello World"
    subdir = "mysubdir"

    info = attachment_handler.save_attachment_from_bytes(
        filename, content, subdir=subdir
    )

    assert info is not None
    assert info.filepath.parent.name == subdir
    assert info.filepath.exists()


def test_save_attachment_from_bytes_duplicate(attachment_handler):
    filename = "test.txt"
    content = b"Hello World"

    info1 = attachment_handler.save_attachment_from_bytes(filename, content)
    info2 = attachment_handler.save_attachment_from_bytes(filename, content)

    assert info1.filename == "test.txt"
    assert info2.filename == "test.txt"  # Original filename is preserved
    assert info1.filepath.name == "test.txt"
    assert info2.filepath.name == "test_1.txt"
    assert info1.filepath != info2.filepath
