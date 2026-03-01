"""
Tests for database query tools.

Tests conversation history and analytics querying with mocked database.
"""

from unittest.mock import MagicMock, patch

from src.rag.tools.database_tools import query_analytics, query_conversation_history


def _patch_conv_manager():
    """Patch _get_conv_manager to return a fresh MagicMock."""
    return patch(
        "src.rag.tools.database_tools._get_conv_manager",
        return_value=MagicMock(),
    )


class TestQueryConversationHistory:
    """Test conversation history querying."""

    def test_query_user_conversations(self):
        """Test querying conversations for specific user."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_user_queries.return_value = [
                {
                    "query": "Test query 1",
                    "timestamp": "2024-01-01T10:00:00",
                    "response": "Test response 1",
                },
                {
                    "query": "Test query 2",
                    "timestamp": "2024-01-01T11:00:00",
                    "response": "Test response 2",
                },
            ]

            result = query_conversation_history(
                sender="test@example.com", days=30, limit=10
            )

            assert result["success"] is True
            assert len(result["conversations"]) == 2
            assert result["summary"]["sender"] == "test@example.com"
            assert result["summary"]["num_conversations"] == 2
            assert result["total_count"] == 2
            mock_manager.get_user_queries.assert_called_once_with(
                "test@example.com", days=30, limit=10
            )

    def test_query_overall_stats(self):
        """Test querying overall statistics."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_usage_analytics.return_value = {
                "total_queries": 100,
                "unique_senders": 15,
                "avg_queries_per_user": 6.67,
            }

            result = query_conversation_history(sender=None, days=7)

            assert result["success"] is True
            assert result["summary"]["total_queries"] == 100
            assert result["summary"]["unique_senders"] == 15
            assert result["total_count"] == 0  # No individual conversations
            mock_manager.get_usage_analytics.assert_called_once_with(days=7)

    def test_query_with_limit(self):
        """Test that limit parameter works correctly."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_user_queries.return_value = [
                {"query": f"Query {i}"} for i in range(20)
            ]

            result = query_conversation_history(
                sender="test@example.com", days=30, limit=5
            )

            assert result["success"] is True
            assert len(result["conversations"]) == 5  # Limited to 5
            assert result["total_count"] == 20  # Original count

    def test_query_adjusts_invalid_days(self):
        """Test that invalid days parameter is adjusted."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_user_queries.return_value = []

            result = query_conversation_history(sender="test@example.com", days=0)

            assert result["success"] is True
            # Should adjust to default (30 days)
            mock_manager.get_user_queries.assert_called_once()
            call_args = mock_manager.get_user_queries.call_args
            assert call_args[1]["days"] == 30

    def test_query_adjusts_invalid_limit(self):
        """Test that invalid limit parameter is adjusted."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_user_queries.return_value = []

            result = query_conversation_history(sender="test@example.com", limit=0)

            assert result["success"] is True
            # Should adjust to default (10)
            call_args = mock_manager.get_user_queries.call_args
            assert call_args[1]["limit"] == 10

    def test_query_exception_handling(self):
        """Test that exceptions are handled gracefully."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_user_queries.side_effect = Exception("Database error")

            result = query_conversation_history(sender="test@example.com")

            assert result["success"] is False
            assert "failed" in result["error"].lower()
            assert result["total_count"] == 0
            assert result["conversations"] == []

    def test_uses_context_conversation_manager(self):
        """Test that context-provided conversation manager is used when available."""
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.get_user_queries.return_value = [{"query": "test"}]

        with patch(
            "src.rag.tools.database_tools.get_conversation_manager",
            return_value=mock_ctx_mgr,
        ):
            result = query_conversation_history(sender="test@example.com")

            assert result["success"] is True
            mock_ctx_mgr.get_user_queries.assert_called_once()

    def test_falls_back_to_default_when_no_context(self):
        """Test fallback to default ConversationManager when context returns None."""
        with (
            patch(
                "src.rag.tools.database_tools.get_conversation_manager",
                return_value=None,
            ),
            patch("src.email.conversation_manager.ConversationManager") as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.get_user_queries.return_value = []
            mock_cls.return_value = mock_instance

            result = query_conversation_history(sender="test@example.com")

            assert result["success"] is True
            mock_cls.assert_called_once()


class TestQueryAnalytics:
    """Test analytics querying."""

    def test_query_usage_analytics(self):
        """Test querying usage analytics."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_usage_analytics.return_value = {
                "total_queries": 50,
                "unique_senders": 10,
                "avg_queries_per_user": 5.0,
            }

            result = query_analytics(metric="usage", days=7)

            assert result["success"] is True
            assert result["metric"] == "usage"
            assert result["data"]["total_queries"] == 50
            assert result["days"] == 7
            mock_manager.get_usage_analytics.assert_called_once_with(days=7)

    def test_query_optimization_analytics(self):
        """Test querying optimization analytics."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_optimization_analytics.return_value = {
                "total_queries": 100,
                "optimized_count": 75,
                "optimization_rate": 0.75,
            }

            result = query_analytics(metric="optimization", days=30)

            assert result["success"] is True
            assert result["metric"] == "optimization"
            assert result["data"]["optimization_rate"] == 0.75
            mock_manager.get_optimization_analytics.assert_called_once_with(days=30)

    def test_query_sources_analytics(self):
        """Test querying source document analytics."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_source_analytics.return_value = {
                "total_replies": 80,
                "replies_with_sources": 75,
                "avg_sources_per_reply": 3.2,
            }

            result = query_analytics(metric="sources", days=14)

            assert result["success"] is True
            assert result["metric"] == "sources"
            assert result["data"]["avg_sources_per_reply"] == 3.2
            mock_manager.get_source_analytics.assert_called_once_with(days=14)

    def test_query_invalid_metric(self):
        """Test querying with invalid metric."""
        result = query_analytics(metric="invalid_metric", days=7)

        assert result["success"] is False
        assert "invalid metric" in result["error"].lower()
        assert result["metric"] == "invalid_metric"

    def test_query_adjusts_invalid_days(self):
        """Test that invalid days parameter is adjusted."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_usage_analytics.return_value = {}

            result = query_analytics(metric="usage", days=-5)

            assert result["success"] is True
            # Should adjust to default (7 days)
            mock_manager.get_usage_analytics.assert_called_once_with(days=7)

    def test_query_exception_handling(self):
        """Test that exceptions are handled gracefully."""
        with _patch_conv_manager() as mock_get:
            mock_manager = mock_get.return_value
            mock_manager.get_usage_analytics.side_effect = Exception("Database error")

            result = query_analytics(metric="usage", days=7)

            assert result["success"] is False
            assert "failed" in result["error"].lower()
            assert result["data"] == {}


class TestDatabaseToolsRegistration:
    """Test database tools registration."""

    def test_conversation_tool_registered(self):
        """Test that db_query_conversations tool is registered."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        assert registry.get("db_query_conversations") is not None

    def test_analytics_tool_registered(self):
        """Test that query_analytics tool is registered."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        assert registry.get("query_analytics") is not None

    def test_conversation_tool_parameters(self):
        """Test db_query_conversations tool parameters."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        tool = registry.get("db_query_conversations")

        assert tool is not None
        assert len(tool.parameters) == 3

        param_names = [p.name for p in tool.parameters]
        assert "sender" in param_names
        assert "days" in param_names
        assert "limit" in param_names

        # All parameters should be optional
        for param in tool.parameters:
            assert param.required is False

    def test_analytics_tool_parameters(self):
        """Test query_analytics tool parameters."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        tool = registry.get("query_analytics")

        assert tool is not None
        assert len(tool.parameters) == 2

        param_names = [p.name for p in tool.parameters]
        assert "metric" in param_names
        assert "days" in param_names

        # All parameters should be optional
        for param in tool.parameters:
            assert param.required is False
