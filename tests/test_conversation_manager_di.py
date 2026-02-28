"""
Tests for ConversationManager dependency injection.

Verifies that ConversationManager accepts an optional db_manager parameter
and falls back to the global default when None.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch


class TestConversationManagerDI:
    """Tests for ConversationManager db_manager injection."""

    def test_default_uses_global_db_manager(self):
        """When no db_manager is passed, uses the global instance."""
        with patch("src.email.conversation_manager.logger"):
            # Import fresh to test the default path
            from src.email.conversation_manager import ConversationManager

            cm = ConversationManager()
            # Should have the global db_manager
            assert cm.db_manager is not None

    def test_injected_db_manager_is_used(self):
        """When a custom db_manager is passed, it is used."""
        mock_db = MagicMock()

        with patch("src.email.conversation_manager.logger"):
            from src.email.conversation_manager import ConversationManager

            cm = ConversationManager(db_manager=mock_db)
            assert cm.db_manager is mock_db

    def test_injected_db_manager_get_session_called(self):
        """Operations use the injected db_manager's get_session."""
        mock_session = MagicMock()

        @contextmanager
        def fake_get_session():
            yield mock_session

        mock_db = MagicMock()
        mock_db.get_session = fake_get_session

        with patch("src.email.conversation_manager.logger"):
            from src.email.conversation_manager import ConversationManager

            cm = ConversationManager(db_manager=mock_db)

            # Call a method that uses get_session
            # get_conversation_history queries via db_manager.get_session()
            result = cm.get_conversation_history("nonexistent-thread")
            assert result == []  # No conversation found, returns empty list

    def test_global_singleton_unchanged(self):
        """The module-level conversation_manager singleton still works."""
        from src.email.conversation_manager import conversation_manager

        assert conversation_manager is not None
        assert conversation_manager.db_manager is not None
