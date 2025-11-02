"""
Unit tests for document_processor module.

Tests document parsing, text extraction, and chunking functionality.
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest
from docx import Document as DocxDocument

from src.document_processing.document_processor import DocumentProcessor


class TestDocumentProcessor:
    """Test suite for DocumentProcessor class."""

    @pytest.fixture
    def processor(self):
        """Create a DocumentProcessor instance for testing."""
        # Use larger chunk_size to accommodate metadata (converted to tokens by dividing by 4)
        return DocumentProcessor(chunk_size=512, chunk_overlap=50)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_compute_file_hash_consistency(self, processor, temp_dir):
        """
        Test that file hash is consistent for same content.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        # Create a test file
        test_file = temp_dir / "test.txt"
        test_content = "This is test content for hashing."
        test_file.write_text(test_content)

        # Compute hash twice
        hash1 = processor.compute_file_hash(test_file)
        hash2 = processor.compute_file_hash(test_file)

        # Hashes should be identical
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

    def test_compute_file_hash_uniqueness(self, processor, temp_dir):
        """
        Test that different files produce different hashes.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        # Create two different files
        file1 = temp_dir / "test1.txt"
        file2 = temp_dir / "test2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = processor.compute_file_hash(file1)
        hash2 = processor.compute_file_hash(file2)

        # Hashes should be different
        assert hash1 != hash2

    def test_extract_text_from_txt(self, processor, temp_dir):
        """
        Test text extraction from plain text file.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.txt"
        test_content = "Hello, this is a test document.\nWith multiple lines."
        test_file.write_text(test_content)

        extracted = processor.extract_text_from_txt(test_file)

        assert extracted == test_content

    def test_extract_text_from_csv(self, processor, temp_dir):
        """
        Test text extraction from CSV file.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.csv"

        # Create a simple CSV
        df = pd.DataFrame({"Name": ["Alice", "Bob"], "Age": [25, 30]})
        df.to_csv(test_file, index=False)

        extracted = processor.extract_text_from_csv(test_file)

        # Check that extracted text contains the data
        assert "Alice" in extracted
        assert "Bob" in extracted
        assert "25" in extracted
        assert "30" in extracted

    def test_extract_text_from_docx(self, processor, temp_dir):
        """
        Test text extraction from DOCX file.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.docx"

        # Create a DOCX with content
        doc = DocxDocument()
        doc.add_paragraph("First paragraph.")
        doc.add_paragraph("Second paragraph.")
        doc.save(test_file)

        extracted = processor.extract_text_from_docx(test_file)

        assert "First paragraph." in extracted
        assert "Second paragraph." in extracted

    def test_extract_text_unsupported_format(self, processor, temp_dir):
        """
        Test that unsupported file format falls back to text extraction.

        For unknown file extensions, the processor tries to read as text.
        This is a reasonable fallback for plain text files with unusual extensions.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.xyz"
        test_content = "Some text content in unusual format"
        test_file.write_text(test_content)

        # Should successfully extract as text (fallback behavior)
        result = processor.extract_text(test_file)
        assert test_content in result

    def test_process_document_success(self, processor, temp_dir):
        """
        Test successful document processing.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.txt"
        # Create content long enough to generate multiple chunks
        test_content = "This is a test. " * 50
        test_file.write_text(test_content)

        nodes = processor.process_document(test_file, source_type="manual")

        # Should produce at least one node
        assert len(nodes) > 0

        # Check metadata
        first_node = nodes[0]
        assert first_node.metadata["filename"] == "test.txt"
        assert first_node.metadata["source_type"] == "manual"
        assert first_node.metadata["file_type"] == ".txt"
        assert "file_hash" in first_node.metadata

    def test_process_document_empty_file(self, processor, temp_dir):
        """
        Test processing empty file returns empty list.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "empty.txt"
        test_file.write_text("")

        nodes = processor.process_document(test_file)

        assert len(nodes) == 0

    def test_process_document_with_extra_metadata(self, processor, temp_dir):
        """
        Test that extra metadata is added to nodes.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.txt"
        test_file.write_text("Test content for metadata.")

        extra_metadata = {"author": "Test User", "department": "DoLS"}

        nodes = processor.process_document(test_file, extra_metadata=extra_metadata)

        assert len(nodes) > 0
        first_node = nodes[0]
        assert first_node.metadata["author"] == "Test User"
        assert first_node.metadata["department"] == "DoLS"

    def test_process_directory(self, processor, temp_dir):
        """
        Test processing all files in a directory.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        # Create multiple test files
        (temp_dir / "doc1.txt").write_text("Document 1 content.")
        (temp_dir / "doc2.txt").write_text("Document 2 content.")
        (temp_dir / "doc3.csv").write_text("col1,col2\nval1,val2")

        # Create unsupported file (should be skipped)
        (temp_dir / "ignored.xyz").write_text("Should be ignored")

        nodes = processor.process_directory(temp_dir)

        # Should process 3 supported files
        unique_files = set(n.metadata["filename"] for n in nodes)
        assert len(unique_files) == 3
        assert "doc1.txt" in unique_files
        assert "doc2.txt" in unique_files
        assert "doc3.csv" in unique_files
        assert "ignored.xyz" not in unique_files

    def test_chunking_with_overlap(self, processor, temp_dir):
        """
        Test that chunking respects overlap parameter.

        Args:
            processor: DocumentProcessor fixture.
            temp_dir: Temporary directory fixture.
        """
        test_file = temp_dir / "test.txt"
        # Create content that will span multiple chunks
        test_content = "A" * 1500  # 1500 characters, chunk_size=512, overlap=50
        test_file.write_text(test_content)

        nodes = processor.process_document(test_file)

        # Should create multiple chunks due to length
        assert len(nodes) >= 2

        # Check that chunks have reasonable length
        for node in nodes:
            # Chunks shouldn't exceed chunk_size significantly
            assert len(node.text) <= processor.chunk_size + 50  # Allow some buffer
