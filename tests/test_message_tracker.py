"""
Unit tests for message tracker.

Tests the message tracking interface for email processing.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.email.db_manager import DatabaseManager
from src.email.db_models import ProcessedMessage
from src.email.message_tracker import MessageTracker


@pytest.fixture
def test_tracker():
    """Create a test message tracker with in-memory SQLite."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with (
        patch.object(DatabaseManager, "_create_engine", return_value=test_engine),
        patch("src.email.db_manager.settings"),
        patch("src.email.message_tracker.db_manager") as mock_db_manager,
    ):
        # Create fresh database manager for this test
        fresh_db_manager = DatabaseManager()
        fresh_db_manager.init_db()

        # Mock the db_manager used by MessageTracker
        mock_db_manager.get_session = fresh_db_manager.get_session
        mock_db_manager.init_db = fresh_db_manager.init_db

        # Create tracker without auto-init since we already initialized
        tracker = MessageTracker(auto_init_db=False)

        # Attach db_manager to tracker for test access
        tracker._test_db_manager = fresh_db_manager

        yield tracker

        # Cleanup
        fresh_db_manager.close()


class TestMessageTracker:
    """Tests for MessageTracker class."""

    def test_is_processed_new_message(self, test_tracker):
        """Test checking if new message is processed."""
        assert test_tracker.is_processed("<new@example.com>") is False

    def test_is_processed_existing_message(self, test_tracker):
        """Test checking if existing message is processed."""
        # Mark message as processed
        test_tracker.mark_processed(
            message_id="<test@example.com>",
            sender="sender@example.com",
            subject="Test",
        )

        # Check if processed
        assert test_tracker.is_processed("<test@example.com>") is True

    def test_mark_processed_success(self, test_tracker):
        """Test marking a message as successfully processed."""
        test_tracker.mark_processed(
            message_id="<test@example.com>",
            sender="sender@example.com",
            subject="Test Subject",
            attachment_count=2,
            chunks_created=5,
            status="success",
        )

        # Verify message is marked as processed
        assert test_tracker.is_processed("<test@example.com>") is True

    def test_mark_processed_error(self, test_tracker):
        """Test marking a message with error status."""
        test_tracker.mark_processed(
            message_id="<error@example.com>",
            sender="sender@example.com",
            subject="Failed",
            status="error",
            error_message="Connection timeout",
        )

        # Verify message is marked as processed (even with error status)
        assert test_tracker.is_processed("<error@example.com>") is True

    def test_mark_processed_updates_stats(self, test_tracker):
        """Test that marking processed updates daily statistics."""
        test_tracker.mark_processed(
            message_id="<test1@example.com>",
            sender="sender@example.com",
            attachment_count=2,
            chunks_created=5,
        )

        test_tracker.mark_processed(
            message_id="<test2@example.com>",
            sender="sender@example.com",
            attachment_count=1,
            chunks_created=3,
        )

        # Get today's stats
        stats = test_tracker.get_stats(days=1)

        assert stats["total_emails"] == 2
        assert stats["total_attachments"] == 3
        assert stats["total_chunks"] == 8
        assert stats["total_errors"] == 0

    def test_get_stats_empty(self, test_tracker):
        """Test getting stats when no messages processed."""
        stats = test_tracker.get_stats(days=30)

        assert stats["total_emails"] == 0
        assert stats["total_attachments"] == 0
        assert stats["total_chunks"] == 0
        assert stats["total_errors"] == 0
        assert stats["success_rate"] == 0

    def test_get_stats_with_data(self, test_tracker):
        """Test getting statistics with processed messages."""
        # Add successful messages
        for i in range(8):
            test_tracker.mark_processed(
                message_id=f"<test{i}@example.com>",
                sender="sender@example.com",
                attachment_count=1,
                chunks_created=3,
                status="success",
            )

        # Add failed messages
        for i in range(2):
            test_tracker.mark_processed(
                message_id=f"<error{i}@example.com>",
                sender="sender@example.com",
                status="error",
                error_message="Test error",
            )

        stats = test_tracker.get_stats(days=30)

        assert stats["total_emails"] == 10
        assert stats["total_attachments"] == 8
        assert stats["total_chunks"] == 24
        assert stats["total_errors"] == 2
        assert stats["success_rate"] == 80.0  # 8 success / 10 total
        assert stats["status_counts"]["success"] == 8
        assert stats["status_counts"]["error"] == 2

    def test_get_stats_top_senders(self, test_tracker):
        """Test getting top senders in statistics."""
        # Add messages from different senders
        test_tracker.mark_processed(
            message_id="<test1@example.com>",
            sender="alice@example.com",
        )
        test_tracker.mark_processed(
            message_id="<test2@example.com>",
            sender="alice@example.com",
        )
        test_tracker.mark_processed(
            message_id="<test3@example.com>",
            sender="bob@example.com",
        )

        stats = test_tracker.get_stats(days=30)

        assert len(stats["top_senders"]) == 2
        # Alice should be first (2 messages)
        assert stats["top_senders"][0]["sender"] == "alice@example.com"
        assert stats["top_senders"][0]["count"] == 2
        assert stats["top_senders"][1]["sender"] == "bob@example.com"
        assert stats["top_senders"][1]["count"] == 1

    def test_cleanup_old_records(self, test_tracker):
        """Test cleaning up old message records."""
        # Add recent message (should not be deleted)
        test_tracker.mark_processed(
            message_id="<recent@example.com>",
            sender="sender@example.com",
        )

        # Add old message manually (bypass tracker to set old date)
        old_message = ProcessedMessage(
            message_id="<old@example.com>",
            sender="sender@example.com",
            processed_at=datetime.utcnow() - timedelta(days=100),
        )

        with test_tracker._test_db_manager.get_session() as session:
            session.add(old_message)

        # Verify both exist
        assert test_tracker.is_processed("<recent@example.com>") is True
        assert test_tracker.is_processed("<old@example.com>") is True

        # Cleanup records older than 90 days
        deleted = test_tracker.cleanup_old_records(days=90)

        assert deleted == 1
        # Recent should still exist
        assert test_tracker.is_processed("<recent@example.com>") is True
        # Old should be deleted
        assert test_tracker.is_processed("<old@example.com>") is False
