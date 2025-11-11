"""
Tests for document age tracking functionality.

Tests the age calculation logic in document_manager.py to ensure
documents are properly tracked with timestamps and age metadata.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest


class TestDocumentAgeCalculation:
    """Test document age calculation and formatting."""

    @pytest.fixture
    def mock_kb_manager(self):
        """Mock KnowledgeBaseManager for testing."""
        kb_manager = Mock()
        kb_manager.get_unique_documents = Mock(return_value=[])
        return kb_manager

    @pytest.fixture
    def mock_document_processor(self):
        """Mock DocumentProcessor for testing."""
        processor = Mock()
        return processor

    @pytest.fixture
    def document_manager(self, mock_kb_manager, mock_document_processor, tmp_path):
        """Create DocumentManager instance with mocked dependencies."""
        from src.api.admin.document_manager import DocumentManager

        manager = DocumentManager(
            kb_manager=mock_kb_manager,
            document_processor=mock_document_processor,
            base_path=tmp_path,
        )
        return manager

    def test_age_calculation_recent_document(self, document_manager, mock_kb_manager):
        """Test age calculation for a document added 5 days ago."""
        # Create a document with timestamp 5 days ago
        five_days_ago = datetime.now() - timedelta(days=5)
        timestamp = five_days_ago.timestamp()

        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "test.pdf",
                "file_hash": "abc123",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": timestamp,
            }
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        assert len(result) == 1
        doc = result[0]
        assert doc["filename"] == "test.pdf"
        assert doc["age_days"] == 5
        assert "date_added" in doc
        assert isinstance(doc["date_added"], str)  # Should be ISO format

    def test_age_calculation_old_document(self, document_manager, mock_kb_manager):
        """Test age calculation for a document added over 1 year ago."""
        # Create a document with timestamp 400 days ago
        long_ago = datetime.now() - timedelta(days=400)
        timestamp = long_ago.timestamp()

        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "old_doc.pdf",
                "file_hash": "xyz789",
                "source_type": "email",
                "file_type": ".pdf",
                "file_mtime": timestamp,
            }
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        assert len(result) == 1
        doc = result[0]
        assert doc["age_days"] == 400
        assert doc["age_days"] > 365  # Should trigger warning in UI

    def test_age_calculation_no_timestamp(self, document_manager, mock_kb_manager):
        """Test handling of documents without file_mtime."""
        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "no_timestamp.pdf",
                "file_hash": "def456",
                "source_type": "file",
                "file_type": ".pdf",
                # No file_mtime field
            }
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        assert len(result) == 1
        doc = result[0]
        assert doc["age_days"] is None
        assert "date_added" not in doc or doc.get("date_added") is None

    def test_age_calculation_invalid_timestamp(self, document_manager, mock_kb_manager):
        """Test handling of invalid timestamps."""
        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "invalid.pdf",
                "file_hash": "ghi789",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": -999999999999,  # Invalid timestamp
            }
        ]

        # Call list_documents - should not crash
        result = document_manager.list_documents()

        # Should handle gracefully
        assert len(result) == 1
        doc = result[0]
        # Age should be None if timestamp is invalid
        assert doc["age_days"] is None

    def test_age_calculation_zero_days(self, document_manager, mock_kb_manager):
        """Test age calculation for a document added today."""
        # Create a document with timestamp from today
        now = datetime.now()
        timestamp = now.timestamp()

        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "today.pdf",
                "file_hash": "jkl012",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": timestamp,
            }
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        assert len(result) == 1
        doc = result[0]
        assert doc["age_days"] == 0

    def test_age_calculation_multiple_documents(
        self, document_manager, mock_kb_manager
    ):
        """Test age calculation for multiple documents with different ages."""
        now = datetime.now()

        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "new.pdf",
                "file_hash": "aaa111",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": (now - timedelta(days=2)).timestamp(),
            },
            {
                "filename": "medium.pdf",
                "file_hash": "bbb222",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": (now - timedelta(days=180)).timestamp(),
            },
            {
                "filename": "old.pdf",
                "file_hash": "ccc333",
                "source_type": "email",
                "file_type": ".pdf",
                "file_mtime": (now - timedelta(days=500)).timestamp(),
            },
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        assert len(result) == 3

        # Check each document has correct age
        ages = {doc["filename"]: doc["age_days"] for doc in result}
        assert ages["new.pdf"] == 2
        assert ages["medium.pdf"] == 180
        assert ages["old.pdf"] == 500

    def test_iso_date_format(self, document_manager, mock_kb_manager):
        """Test that date_added is in ISO format."""
        timestamp = datetime(2024, 6, 15, 10, 30, 0).timestamp()

        mock_kb_manager.get_unique_documents.return_value = [
            {
                "filename": "test.pdf",
                "file_hash": "ddd444",
                "source_type": "file",
                "file_type": ".pdf",
                "file_mtime": timestamp,
            }
        ]

        # Call list_documents
        result = document_manager.list_documents()

        # Assertions
        doc = result[0]
        assert "date_added" in doc

        # Should be parseable as ISO format
        parsed_date = datetime.fromisoformat(doc["date_added"])
        assert isinstance(parsed_date, datetime)
        assert parsed_date.year == 2024
        assert parsed_date.month == 6
        assert parsed_date.day == 15


class TestAgeThresholds:
    """Test age threshold calculations for UI warnings."""

    def test_warning_threshold_12_months(self):
        """Test that documents older than 365 days should trigger warning."""
        # This is more of a documentation test for the threshold
        warning_threshold_days = 365

        # Documents at various ages
        ages = [
            (10, False),  # 10 days - no warning
            (30, False),  # 1 month - no warning
            (180, False),  # 6 months - no warning
            (364, False),  # Just under 12 months - no warning
            (365, True),  # Exactly 12 months - warning
            (366, True),  # Over 12 months - warning
            (730, True),  # 2 years - warning
        ]

        for age_days, should_warn in ages:
            needs_warning = age_days >= warning_threshold_days
            assert (
                needs_warning == should_warn
            ), f"Age {age_days} days: expected warning={should_warn}"
