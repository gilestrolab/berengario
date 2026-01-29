"""
Tests for web search tools.

Tests DuckDuckGo-based web search functionality with mocked responses.
"""

from unittest.mock import MagicMock, patch

from src.rag.tools.web_search_tools import web_search


class TestWebSearch:
    """Test web search functionality."""

    @patch("duckduckgo_search.DDGS")
    def test_web_search_success(self, mock_ddgs_class):
        """Test successful web search."""
        # Mock DDGS search results
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {
                "title": "Test Result 1",
                "link": "https://example.com/1",
                "body": "This is test result 1",
            },
            {
                "title": "Test Result 2",
                "link": "https://example.com/2",
                "body": "This is test result 2",
            },
        ]
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("test query", num_results=2)

        assert result["success"] is True
        assert result["query"] == "test query"
        assert result["num_results"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Test Result 1"
        assert result["results"][0]["url"] == "https://example.com/1"
        assert result["results"][0]["snippet"] == "This is test result 1"

    @patch("duckduckgo_search.DDGS")
    def test_web_search_no_results(self, mock_ddgs_class):
        """Test web search with no results."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = []
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("nonexistent query")

        assert result["success"] is True
        assert result["num_results"] == 0
        assert result["results"] == []

    def test_web_search_empty_query(self):
        """Test web search with empty query."""
        result = web_search("")

        assert result["success"] is False
        assert "empty" in result["error"].lower()
        assert result["num_results"] == 0

    def test_web_search_whitespace_query(self):
        """Test web search with whitespace-only query."""
        result = web_search("   ")

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    @patch("duckduckgo_search.DDGS")
    def test_web_search_adjusts_num_results(self, mock_ddgs_class):
        """Test that num_results is adjusted to valid range."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = []
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        # Test negative num_results
        result = web_search("test", num_results=-1)
        assert result["success"] is True  # Adjusted to valid range

        # Test zero num_results
        result = web_search("test", num_results=0)
        assert result["success"] is True  # Adjusted to valid range

    @patch("duckduckgo_search.DDGS")
    def test_web_search_exception_handling(self, mock_ddgs_class):
        """Test web search handles exceptions gracefully."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.side_effect = Exception("Network error")
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("test query")

        assert result["success"] is False
        assert "failed" in result["error"].lower()
        assert result["num_results"] == 0
        assert result["results"] == []

    @patch("duckduckgo_search.DDGS")
    def test_web_search_missing_fields(self, mock_ddgs_class):
        """Test web search handles missing fields in results."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {
                "title": "Result with missing fields",
                # Missing 'link' and 'body'
            },
            {
                # Missing all fields
            },
        ]
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("test query")

        assert result["success"] is True
        assert result["num_results"] == 2
        assert result["results"][0]["title"] == "Result with missing fields"
        assert result["results"][0]["url"] == ""
        assert result["results"][0]["snippet"] == ""
        assert result["results"][1]["title"] == "No title"

    @patch("duckduckgo_search.DDGS")
    def test_web_search_default_num_results(self, mock_ddgs_class):
        """Test web search uses default num_results."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = []
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("test query")

        # Should call with max_results=5 (default)
        mock_ddgs.text.assert_called_with("test query", max_results=5)
        assert result["success"] is True

    @patch("duckduckgo_search.DDGS")
    def test_web_search_special_characters(self, mock_ddgs_class):
        """Test web search with special characters in query."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {
                "title": "Special chars result",
                "link": "https://example.com",
                "body": "Result for special chars",
            }
        ]
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = web_search("test @#$% query!?", num_results=1)

        assert result["success"] is True
        assert result["query"] == "test @#$% query!?"
        mock_ddgs.text.assert_called_with("test @#$% query!?", max_results=1)


class TestWebSearchTool:
    """Test web search tool registration."""

    def test_web_search_tool_registered(self):
        """Test that web_search tool is registered."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        assert registry.get("web_search") is not None

    def test_web_search_tool_parameters(self):
        """Test web_search tool parameters."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        tool = registry.get("web_search")

        assert tool is not None
        assert tool.name == "web_search"
        assert len(tool.parameters) == 2

        # Check parameters
        param_names = [p.name for p in tool.parameters]
        assert "query" in param_names
        assert "num_results" in param_names

        # Check required status
        query_param = next(p for p in tool.parameters if p.name == "query")
        assert query_param.required is True

        num_results_param = next(p for p in tool.parameters if p.name == "num_results")
        assert num_results_param.required is False
