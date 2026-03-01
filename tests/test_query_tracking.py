"""
Unit tests for query tracking functionality.

Tests that query optimization and source document tracking are properly
stored in the conversation database.
"""

from unittest.mock import patch

import pytest

from src.email.conversation_manager import ConversationManager
from src.email.db_manager import DatabaseManager
from src.email.db_models import ChannelType, MessageType


@pytest.fixture
def conversation_manager():
    """Create conversation manager with test database."""
    # Setup test database
    with patch("src.email.db_manager.settings") as mock_settings:
        mock_settings.db_type = "sqlite"
        mock_settings.sqlite_db_path = ":memory:"
        mock_settings.debug = False
        mock_settings.get_database_url.return_value = "sqlite:///:memory:"

        test_db_manager = DatabaseManager()
        test_db_manager.init_db()

        # Pass the test db_manager directly via DI
        manager = ConversationManager(db_manager=test_db_manager)
        yield manager

        test_db_manager.close()


class TestQueryOptimizationTracking:
    """Test suite for query optimization tracking."""

    def test_add_message_with_optimization_data(self, conversation_manager):
        """Test storing a message with query optimization data."""
        thread_id = "test_thread_001"

        # Add query message with optimization data
        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="vacation days",
            sender="user@example.com",
            channel=ChannelType.EMAIL,
            original_query="vacation days",
            optimized_query="What is the company vacation policy?",
        )

        assert message_id is not None

        # Verify optimization data was stored
        details = conversation_manager.get_message_optimization_details(message_id)

        assert details is not None
        assert details["original_query"] == "vacation days"
        assert details["optimized_query"] == "What is the company vacation policy?"
        assert details["optimization_applied"] is True

    def test_add_message_without_optimization(self, conversation_manager):
        """Test storing a message without optimization."""
        thread_id = "test_thread_002"

        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="test query",
            sender="user@example.com",
            channel=ChannelType.WEBCHAT,
        )

        assert message_id is not None

        # Verify no optimization data
        details = conversation_manager.get_message_optimization_details(message_id)

        assert details is not None
        assert details["original_query"] is None
        assert details["optimized_query"] is None
        assert details["optimization_applied"] is False

    def test_optimization_applied_flag_same_query(self, conversation_manager):
        """Test that optimization_applied is False when queries are identical."""
        thread_id = "test_thread_003"

        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="What is the vacation policy?",
            sender="user@example.com",
            original_query="What is the vacation policy?",
            optimized_query="What is the vacation policy?",  # Same as original
        )

        details = conversation_manager.get_message_optimization_details(message_id)

        assert details["optimization_applied"] is False

    def test_optimization_applied_flag_different_query(self, conversation_manager):
        """Test that optimization_applied is True when queries differ."""
        thread_id = "test_thread_004"

        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="vacation",
            sender="user@example.com",
            original_query="vacation",
            optimized_query="What is the vacation policy?",
        )

        details = conversation_manager.get_message_optimization_details(message_id)

        assert details["optimization_applied"] is True

    def test_get_optimization_details_nonexistent_message(self, conversation_manager):
        """Test retrieving optimization details for nonexistent message."""
        details = conversation_manager.get_message_optimization_details(99999)

        assert details is None


class TestSourceDocumentTracking:
    """Test suite for source document tracking."""

    def test_add_reply_with_sources(self, conversation_manager):
        """Test storing a reply message with source documents."""
        thread_id = "test_thread_005"

        # First add a query
        conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="test query",
            sender="user@example.com",
        )

        # Add reply with sources
        sources = [
            {
                "filename": "policy.pdf",
                "score": 0.95,
                "text_preview": "Vacation policy details...",
            },
            {
                "filename": "handbook.docx",
                "score": 0.87,
                "text_preview": "Employee handbook excerpt...",
            },
        ]

        metadata = {
            "model": "test-model",
            "num_sources": 2,
            "num_attachments": 0,
            "query_length": 10,
        }

        reply_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content="Here is the vacation policy...",
            sender="assistant",
            sources_used=sources,
            retrieval_metadata=metadata,
        )

        assert reply_id is not None

        # Verify source data was stored
        details = conversation_manager.get_message_source_details(reply_id)

        assert details is not None
        assert details["sources_used"] is not None
        assert len(details["sources_used"]) == 2
        assert details["sources_used"][0]["filename"] == "policy.pdf"
        assert details["sources_used"][0]["score"] == 0.95
        assert details["retrieval_metadata"] is not None
        assert details["retrieval_metadata"]["num_sources"] == 2

    def test_add_reply_without_sources(self, conversation_manager):
        """Test storing a reply without source documents."""
        thread_id = "test_thread_006"

        reply_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content="I don't have enough information to answer.",
            sender="assistant",
        )

        details = conversation_manager.get_message_source_details(reply_id)

        assert details is not None
        assert details["sources_used"] is None
        assert details["retrieval_metadata"] is None

    def test_get_source_details_nonexistent_message(self, conversation_manager):
        """Test retrieving source details for nonexistent message."""
        details = conversation_manager.get_message_source_details(99999)

        assert details is None

    def test_sources_with_complex_metadata(self, conversation_manager):
        """Test storing sources with complex metadata structures."""
        thread_id = "test_thread_007"

        sources = [
            {
                "filename": "email_from_john.txt",
                "score": 0.92,
                "text_preview": "Email content...",
                "source_type": "email",
                "sender": "john@example.com",
                "subject": "RE: Vacation Request",
                "date": "2025-01-15",
            }
        ]

        metadata = {
            "model": "claude-3.5-sonnet",
            "num_sources": 1,
            "avg_relevance_score": 0.92,
            "retrieval_method": "semantic_search",
            "context_window_used": 8000,
        }

        reply_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content="Based on the email from John...",
            sender="assistant",
            sources_used=sources,
            retrieval_metadata=metadata,
        )

        details = conversation_manager.get_message_source_details(reply_id)

        assert details["sources_used"][0]["source_type"] == "email"
        assert details["sources_used"][0]["sender"] == "john@example.com"
        assert details["retrieval_metadata"]["retrieval_method"] == "semantic_search"


class TestConversationMessageModel:
    """Test the ConversationMessage model directly."""

    def test_message_to_dict_includes_new_fields(self, conversation_manager):
        """Test that to_dict() includes all new tracking fields."""
        thread_id = "test_thread_008"

        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="test",
            sender="user@example.com",
            original_query="test",
            optimized_query="What is the test?",
        )

        # Get message and convert to dict
        with conversation_manager.db_manager.get_session() as session:
            from src.email.db_models import ConversationMessage

            message = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.id == message_id)
                .first()
            )

            message_dict = message.to_dict()

        # Verify all new fields are included
        assert "original_query" in message_dict
        assert "optimized_query" in message_dict
        assert "optimization_applied" in message_dict
        assert "sources_used" in message_dict
        assert "retrieval_metadata" in message_dict

        assert message_dict["original_query"] == "test"
        assert message_dict["optimized_query"] == "What is the test?"
        assert message_dict["optimization_applied"] is True


class TestBackwardCompatibility:
    """Test that new fields don't break existing functionality."""

    def test_old_messages_without_new_fields(self, conversation_manager):
        """Test that old messages without tracking data still work."""
        thread_id = "test_thread_009"

        # Add message the old way (without new params)
        message_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="old style query",
            sender="user@example.com",
        )

        # Should not raise errors
        opt_details = conversation_manager.get_message_optimization_details(message_id)
        assert opt_details is not None
        assert opt_details["original_query"] is None

        # Add reply the old way
        reply_id = conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content="old style reply",
            sender="assistant",
        )

        src_details = conversation_manager.get_message_source_details(reply_id)
        assert src_details is not None
        assert src_details["sources_used"] is None

    def test_conversation_history_still_works(self, conversation_manager):
        """Test that get_conversation_history works with new fields."""
        thread_id = "test_thread_010"

        # Add messages with and without tracking data
        conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.QUERY,
            content="query 1",
            sender="user@example.com",
            original_query="query 1",
            optimized_query="What is query 1?",
        )

        conversation_manager.add_message(
            thread_id=thread_id,
            message_type=MessageType.REPLY,
            content="answer 1",
            sender="assistant",
            sources_used=[{"filename": "doc.pdf"}],
        )

        # Get conversation history
        history = conversation_manager.get_conversation_history(thread_id)

        assert len(history) == 2
        assert history[0]["content"] == "query 1"
        assert history[1]["content"] == "answer 1"
