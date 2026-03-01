"""
Tests for RAG search tools.

Tests explicit knowledge base search functionality with mocked KB manager.
"""

from unittest.mock import MagicMock, patch

from src.rag.tools.context import clear_tool_context, get_kb_manager, set_tool_context
from src.rag.tools.rag_tools import rag_search


class TestRAGSearch:
    """Test RAG search functionality."""

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_success(self, mock_kb_class):
        """Test successful KB search."""
        # Mock query engine and response
        mock_node1 = MagicMock()
        mock_node1.text = "This is document 1"
        mock_node1.score = 0.95
        mock_node1.metadata = {"filename": "doc1.pdf", "page": 1}

        mock_node2 = MagicMock()
        mock_node2.text = "This is document 2"
        mock_node2.score = 0.87
        mock_node2.metadata = {"filename": "doc2.pdf"}

        mock_response = MagicMock()
        mock_response.source_nodes = [mock_node1, mock_node2]

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        result = rag_search("test query", top_k=5)

        assert result["success"] is True
        assert result["query"] == "test query"
        assert result["num_results"] == 2
        assert len(result["documents"]) == 2

        # Check first document
        assert result["documents"][0]["text"] == "This is document 1"
        assert result["documents"][0]["score"] == 0.95
        assert result["documents"][0]["filename"] == "doc1.pdf"
        assert result["documents"][0]["page"] == 1

        # Check second document
        assert result["documents"][1]["text"] == "This is document 2"
        assert result["documents"][1]["score"] == 0.87
        assert result["documents"][1]["filename"] == "doc2.pdf"

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_no_results(self, mock_kb_class):
        """Test KB search with no results."""
        mock_response = MagicMock()
        mock_response.source_nodes = []

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        result = rag_search("nonexistent query")

        assert result["success"] is True
        assert result["num_results"] == 0
        assert result["documents"] == []

    def test_rag_search_empty_query(self):
        """Test KB search with empty query."""
        result = rag_search("")

        assert result["success"] is False
        assert "empty" in result["error"].lower()
        assert result["num_results"] == 0

    def test_rag_search_whitespace_query(self):
        """Test KB search with whitespace-only query."""
        result = rag_search("   ")

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_adjusts_top_k(self, mock_kb_class):
        """Test that top_k is adjusted to valid range."""
        mock_response = MagicMock()
        mock_response.source_nodes = []

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        # Test negative top_k
        result = rag_search("test", top_k=-1)
        assert result["success"] is True
        # Should be adjusted to 5
        mock_kb.get_query_engine.assert_called_with(top_k=5)

        # Test zero top_k
        result = rag_search("test", top_k=0)
        assert result["success"] is True

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_exception_handling(self, mock_kb_class):
        """Test KB search handles exceptions gracefully."""
        mock_kb = MagicMock()
        mock_kb.get_query_engine.side_effect = Exception("KB error")
        mock_kb_class.return_value = mock_kb

        result = rag_search("test query")

        assert result["success"] is False
        assert "failed" in result["error"].lower()
        assert result["num_results"] == 0
        assert result["documents"] == []

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_missing_metadata(self, mock_kb_class):
        """Test KB search handles missing metadata fields."""
        mock_node = MagicMock()
        mock_node.text = "Document with missing metadata"
        mock_node.score = 0.8
        mock_node.metadata = {}  # Empty metadata

        mock_response = MagicMock()
        mock_response.source_nodes = [mock_node]

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        result = rag_search("test query")

        assert result["success"] is True
        assert result["num_results"] == 1
        assert result["documents"][0]["filename"] == "unknown"
        assert result["documents"][0]["page"] is None
        assert result["documents"][0]["chunk_id"] is None

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_no_source_nodes(self, mock_kb_class):
        """Test KB search when response has no source_nodes attribute."""
        mock_response = MagicMock()
        # Remove source_nodes attribute
        del mock_response.source_nodes

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        result = rag_search("test query")

        assert result["success"] is True
        assert result["num_results"] == 0
        assert result["documents"] == []

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_default_top_k(self, mock_kb_class):
        """Test KB search uses default top_k."""
        mock_response = MagicMock()
        mock_response.source_nodes = []

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        result = rag_search("test query")

        # Should call with top_k=5 (default)
        mock_kb.get_query_engine.assert_called_with(top_k=5)
        assert result["success"] is True


class TestRAGSearchTool:
    """Test RAG search tool registration."""

    def test_rag_search_tool_registered(self):
        """Test that rag_search tool is registered."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        assert registry.get("rag_search") is not None

    def test_rag_search_tool_parameters(self):
        """Test rag_search tool parameters."""
        from src.rag.tools.base import get_registry

        registry = get_registry()
        tool = registry.get("rag_search")

        assert tool is not None
        assert tool.name == "rag_search"
        assert len(tool.parameters) == 2

        # Check parameters
        param_names = [p.name for p in tool.parameters]
        assert "query" in param_names
        assert "top_k" in param_names

        # Check required status
        query_param = next(p for p in tool.parameters if p.name == "query")
        assert query_param.required is True

        top_k_param = next(p for p in tool.parameters if p.name == "top_k")
        assert top_k_param.required is False


class TestRAGSearchContext:
    """Test RAG search uses context kb_manager when available."""

    def test_rag_search_uses_context_kb_manager(self):
        """When kb_manager is set in context, rag_search should use it."""
        # Set up mock KB manager in context
        mock_node = MagicMock()
        mock_node.text = "Context KB result"
        mock_node.score = 0.9
        mock_node.metadata = {"filename": "tenant_doc.pdf"}

        mock_response = MagicMock()
        mock_response.source_nodes = [mock_node]

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine

        try:
            set_tool_context(
                user_email="test@example.com",
                is_admin=False,
                kb_manager=mock_kb,
            )

            result = rag_search("test query", top_k=3)

            assert result["success"] is True
            assert result["num_results"] == 1
            assert result["documents"][0]["text"] == "Context KB result"
            # Verify the context KB was used, not a new default one
            mock_kb.get_query_engine.assert_called_once_with(top_k=3)
        finally:
            clear_tool_context()

    @patch("src.document_processing.kb_manager.KnowledgeBaseManager")
    def test_rag_search_defaults_without_context(self, mock_kb_class):
        """When no kb_manager in context, rag_search should create a default one."""
        mock_response = MagicMock()
        mock_response.source_nodes = []

        mock_query_engine = MagicMock()
        mock_query_engine.query.return_value = mock_response

        mock_kb = MagicMock()
        mock_kb.get_query_engine.return_value = mock_query_engine
        mock_kb_class.return_value = mock_kb

        try:
            # Set context without kb_manager
            set_tool_context(
                user_email="test@example.com",
                is_admin=False,
            )

            result = rag_search("test query")

            assert result["success"] is True
            # Should have created a new KnowledgeBaseManager
            mock_kb_class.assert_called_once()
        finally:
            clear_tool_context()

    def test_kb_manager_context_var_lifecycle(self):
        """Test kb_manager context variable set/get/clear lifecycle."""
        # Initially None
        assert get_kb_manager() is None

        mock_kb = MagicMock()
        set_tool_context(
            user_email="test@example.com", is_admin=False, kb_manager=mock_kb
        )
        assert get_kb_manager() is mock_kb

        clear_tool_context()
        assert get_kb_manager() is None
