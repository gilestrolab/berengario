"""
Unit tests for database models.

Tests the SQLAlchemy ORM models for email message tracking.
"""

import pytest
from datetime import datetime, date

from src.email.db_models import ProcessedMessage, ProcessingStats


class TestProcessedMessage:
    """Tests for ProcessedMessage model."""

    def test_create_processed_message(self):
        """Test creating a ProcessedMessage instance."""
        message = ProcessedMessage(
            message_id="<test@example.com>",
            sender="sender@example.com",
            subject="Test Subject",
            status="success",
            attachment_count=2,
            chunks_created=5,
        )

        assert message.message_id == "<test@example.com>"
        assert message.sender == "sender@example.com"
        assert message.subject == "Test Subject"
        assert message.status == "success"
        assert message.attachment_count == 2
        assert message.chunks_created == 5
        assert message.error_message is None

    def test_processed_message_defaults(self):
        """Test default values for ProcessedMessage."""
        message = ProcessedMessage(
            message_id="<test@example.com>",
            sender="sender@example.com",
        )

        assert message.status == "success"
        assert message.attachment_count == 0
        assert message.chunks_created == 0
        assert message.error_message is None

    def test_processed_message_with_error(self):
        """Test ProcessedMessage with error status."""
        message = ProcessedMessage(
            message_id="<test@example.com>",
            sender="sender@example.com",
            subject="Failed Email",
            status="error",
            error_message="Connection timeout",
        )

        assert message.status == "error"
        assert message.error_message == "Connection timeout"

    def test_processed_message_to_dict(self):
        """Test converting ProcessedMessage to dictionary."""
        now = datetime.utcnow()
        message = ProcessedMessage(
            message_id="<test@example.com>",
            sender="sender@example.com",
            subject="Test",
            processed_at=now,
            status="success",
            attachment_count=1,
            chunks_created=3,
        )

        data = message.to_dict()

        assert data["message_id"] == "<test@example.com>"
        assert data["sender"] == "sender@example.com"
        assert data["subject"] == "Test"
        assert data["status"] == "success"
        assert data["attachment_count"] == 1
        assert data["chunks_created"] == 3
        assert isinstance(data["processed_at"], str)

    def test_processed_message_repr(self):
        """Test string representation of ProcessedMessage."""
        message = ProcessedMessage(
            message_id="<test@example.com>",
            sender="sender@example.com",
            status="success",
        )

        repr_str = repr(message)

        assert "<test@example.com>" in repr_str
        assert "sender@example.com" in repr_str
        assert "success" in repr_str


class TestProcessingStats:
    """Tests for ProcessingStats model."""

    def test_create_processing_stats(self):
        """Test creating a ProcessingStats instance."""
        today = date.today()
        stats = ProcessingStats(
            date=today,
            emails_processed=10,
            attachments_processed=15,
            chunks_created=50,
            errors_count=2,
        )

        assert stats.date == today
        assert stats.emails_processed == 10
        assert stats.attachments_processed == 15
        assert stats.chunks_created == 50
        assert stats.errors_count == 2

    def test_processing_stats_defaults(self):
        """Test default values for ProcessingStats."""
        today = date.today()
        stats = ProcessingStats(date=today)

        assert stats.emails_processed == 0
        assert stats.attachments_processed == 0
        assert stats.chunks_created == 0
        assert stats.errors_count == 0

    def test_processing_stats_to_dict(self):
        """Test converting ProcessingStats to dictionary."""
        today = date.today()
        stats = ProcessingStats(
            date=today,
            emails_processed=5,
            attachments_processed=8,
            chunks_created=20,
            errors_count=1,
        )

        data = stats.to_dict()

        assert data["date"] == today.isoformat()
        assert data["emails_processed"] == 5
        assert data["attachments_processed"] == 8
        assert data["chunks_created"] == 20
        assert data["errors_count"] == 1
        assert "last_updated" in data

    def test_processing_stats_repr(self):
        """Test string representation of ProcessingStats."""
        today = date.today()
        stats = ProcessingStats(
            date=today,
            emails_processed=10,
            chunks_created=30,
            errors_count=2,
        )

        repr_str = repr(stats)

        assert str(today) in repr_str
        assert "emails=10" in repr_str
        assert "chunks=30" in repr_str
        assert "errors=2" in repr_str
