"""
Unit tests for RAG retrieval upgrades: reranking, hybrid search, and contextual enrichment.

Tests the three new retrieval capabilities added to the RAG pipeline.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.enhancement_processor import EnhancementProcessor


# ---------------------------------------------------------------------------
# Contextual Enrichment Tests
# ---------------------------------------------------------------------------
class TestContextualHeaders:
    """Test contextual header generation and integration."""

    def test_header_for_file_document(self):
        """Test header generation for a regular file."""
        header = EnhancementProcessor.generate_contextual_header(
            filename="policy.pdf",
            file_type=".pdf",
            source_type="manual",
        )
        assert "Document: policy.pdf" in header
        assert "Type: pdf" in header

    def test_header_for_email_document(self):
        """Test header includes email subject and sender."""
        header = EnhancementProcessor.generate_contextual_header(
            filename="attachment.docx",
            file_type=".docx",
            source_type="email",
            extra_metadata={"subject": "Q3 Report", "sender": "alice@example.com"},
        )
        assert "Document: attachment.docx" in header
        assert "Email subject: Q3 Report" in header
        assert "From: alice@example.com" in header
        assert "Type: docx" in header

    def test_header_for_web_document(self):
        """Test header for web-crawled content."""
        header = EnhancementProcessor.generate_contextual_header(
            filename="Web: https://example.com/faq",
            file_type=".html",
            source_type="web",
            extra_metadata={"source_url": "https://example.com/faq"},
        )
        assert "Document: Web: https://example.com/faq" in header
        assert "Source: https://example.com/faq" in header
        assert "Type: html" in header

    def test_header_for_web_without_url(self):
        """Test web header falls back to 'Web page' when no URL in metadata."""
        header = EnhancementProcessor.generate_contextual_header(
            filename="web_page",
            file_type=".html",
            source_type="web",
        )
        assert "Source: Web page" in header

    def test_header_for_email_without_metadata(self):
        """Test email header works with no extra metadata."""
        header = EnhancementProcessor.generate_contextual_header(
            filename="note.txt",
            file_type=".txt",
            source_type="email",
        )
        assert "Document: note.txt" in header
        assert "Type: txt" in header
        # Should not contain email-specific fields
        assert "Email subject" not in header
        assert "From:" not in header


class TestContextualEnrichmentIntegration:
    """Test that contextual headers are prepended to document chunks."""

    @pytest.fixture
    def processor(self):
        """Create a DocumentProcessor instance for testing."""
        return DocumentProcessor(chunk_size=512, chunk_overlap=50)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_headers_prepended_to_file_chunks(self, processor, temp_dir):
        """Test that contextual headers are prepended to processed chunks."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("This is test content for contextual enrichment. " * 10)

        with patch(
            "src.document_processing.document_processor._get_enhancement_processor"
        ) as mock_get:
            mock_get.return_value = None  # Disable LLM enhancement

            with patch(
                "src.document_processing.document_processor.settings"
            ) as mock_settings:
                mock_settings.chunk_size = 512
                mock_settings.chunk_overlap = 50
                mock_settings.contextual_enrichment_enabled = True
                mock_settings.doc_enhancement_enabled = False

                nodes = processor.process_document(test_file, source_type="manual")

        assert len(nodes) > 0
        # Each chunk should start with the contextual header
        for node in nodes:
            assert node.text.startswith("Document: test.txt")
            assert "Type: txt" in node.text

    def test_headers_disabled_via_config(self, processor, temp_dir):
        """Test that headers are not added when feature is disabled."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Test content without headers.")

        with patch(
            "src.document_processing.document_processor._get_enhancement_processor"
        ) as mock_get:
            mock_get.return_value = None

            with patch(
                "src.document_processing.document_processor.settings"
            ) as mock_settings:
                mock_settings.chunk_size = 512
                mock_settings.chunk_overlap = 50
                mock_settings.contextual_enrichment_enabled = False
                mock_settings.doc_enhancement_enabled = False

                nodes = processor.process_document(test_file, source_type="manual")

        assert len(nodes) > 0
        # Chunks should NOT start with contextual header
        for node in nodes:
            assert not node.text.startswith("Document:")

    def test_email_headers_include_subject_sender(self, processor, temp_dir):
        """Test that email metadata is included in contextual headers."""
        test_file = temp_dir / "attachment.txt"
        test_file.write_text("Content from email attachment. " * 10)

        extra_metadata = {
            "subject": "Important Update",
            "sender": "boss@company.com",
        }

        with patch(
            "src.document_processing.document_processor._get_enhancement_processor"
        ) as mock_get:
            mock_get.return_value = None

            with patch(
                "src.document_processing.document_processor.settings"
            ) as mock_settings:
                mock_settings.chunk_size = 512
                mock_settings.chunk_overlap = 50
                mock_settings.contextual_enrichment_enabled = True
                mock_settings.doc_enhancement_enabled = False

                nodes = processor.process_document(
                    test_file,
                    source_type="email",
                    extra_metadata=extra_metadata,
                )

        assert len(nodes) > 0
        first_chunk = nodes[0].text
        assert "Email subject: Important Update" in first_chunk
        assert "From: boss@company.com" in first_chunk


# ---------------------------------------------------------------------------
# Hybrid Search Tests
# ---------------------------------------------------------------------------
class TestHybridSearch:
    """Test BM25 + vector hybrid search functionality."""

    def _make_kb_mock(self):
        """Create a KnowledgeBaseManager mock with cache attributes."""
        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.collection = MagicMock()
        kb._bm25_retriever_cache = None
        kb._bm25_retriever_cache_time = 0.0
        kb._bm25_cache_top_k = None
        kb._BM25_CACHE_TTL = 300
        return kb

    def test_build_bm25_retriever_with_documents(self):
        """Test BM25 retriever construction from ChromaDB data."""
        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = self._make_kb_mock()
        kb.collection.get.return_value = {
            "ids": ["id1", "id2"],
            "documents": ["First document text", "Second document text"],
            "metadatas": [{"filename": "a.txt"}, {"filename": "b.txt"}],
        }

        # Call the real method on the mock
        result = KnowledgeBaseManager._build_bm25_retriever(kb, top_k=5)

        assert result is not None
        kb.collection.get.assert_called_once_with(include=["documents", "metadatas"])

    def test_build_bm25_retriever_empty_collection(self):
        """Test BM25 retriever returns None for empty collection."""
        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = self._make_kb_mock()
        kb.collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }

        result = KnowledgeBaseManager._build_bm25_retriever(kb, top_k=5)
        assert result is None

    @patch("src.document_processing.kb_manager.settings")
    def test_hybrid_search_disabled(self, mock_settings):
        """Test that hybrid search can be disabled via config."""
        mock_settings.hybrid_search_enabled = False
        mock_settings.reranking_enabled = False
        mock_settings.cohere_api_key = ""
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_retriever

        # Call the real method
        KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

        # BM25 retriever should not have been built
        kb._build_bm25_retriever.assert_not_called()

    @patch("src.document_processing.kb_manager.settings")
    def test_hybrid_search_enabled_builds_fusion_retriever(self, mock_settings):
        """Test that enabling hybrid search creates a QueryFusionRetriever."""
        mock_settings.hybrid_search_enabled = True
        mock_settings.reranking_enabled = False
        mock_settings.cohere_api_key = ""
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_vector_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_vector_retriever

        mock_bm25 = MagicMock()
        kb._build_bm25_retriever.return_value = mock_bm25

        # Call real method — lazy imports inside method, so patch the source modules
        with patch(
            "src.document_processing.kb_manager.RetrieverQueryEngine"
        ) as mock_rqe:
            mock_rqe.from_args.return_value = MagicMock()
            KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

        # BM25 retriever should have been built
        kb._build_bm25_retriever.assert_called_once()


# ---------------------------------------------------------------------------
# Reranking Tests
# ---------------------------------------------------------------------------
class TestReranking:
    """Test Cohere reranking postprocessor integration."""

    @patch("src.document_processing.kb_manager.settings")
    def test_reranking_enabled_with_api_key(self, mock_settings):
        """Test that CohereRerank is added when enabled with API key."""
        mock_settings.reranking_enabled = True
        mock_settings.cohere_api_key = "test-key"
        mock_settings.reranking_model = "rerank-v3.5"
        mock_settings.reranking_top_n = None
        mock_settings.hybrid_search_enabled = False
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_retriever

        with patch(
            "src.document_processing.kb_manager.RetrieverQueryEngine"
        ) as mock_rqe:
            mock_rqe.from_args.return_value = MagicMock()

            KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

            # Verify postprocessors were passed
            call_kwargs = mock_rqe.from_args.call_args
            postprocessors = call_kwargs.kwargs.get(
                "node_postprocessors"
            ) or call_kwargs[1].get("node_postprocessors")
            assert postprocessors is not None
            assert len(postprocessors) == 1

    @patch("src.document_processing.kb_manager.settings")
    def test_reranking_skipped_without_api_key(self, mock_settings):
        """Test graceful skip when API key is not set."""
        mock_settings.reranking_enabled = True
        mock_settings.cohere_api_key = ""
        mock_settings.hybrid_search_enabled = False
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_retriever

        with patch(
            "src.document_processing.kb_manager.RetrieverQueryEngine"
        ) as mock_rqe:
            mock_rqe.from_args.return_value = MagicMock()

            KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

            # Verify no postprocessors
            call_kwargs = mock_rqe.from_args.call_args
            postprocessors = call_kwargs.kwargs.get("node_postprocessors")
            assert postprocessors is None

    @patch("src.document_processing.kb_manager.settings")
    def test_reranking_disabled_via_config(self, mock_settings):
        """Test that reranking is completely skipped when disabled."""
        mock_settings.reranking_enabled = False
        mock_settings.cohere_api_key = "test-key"  # Key set but feature disabled
        mock_settings.hybrid_search_enabled = False
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_retriever

        with patch(
            "src.document_processing.kb_manager.RetrieverQueryEngine"
        ) as mock_rqe:
            mock_rqe.from_args.return_value = MagicMock()

            KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

            # Verify no postprocessors (disabled overrides key)
            call_kwargs = mock_rqe.from_args.call_args
            postprocessors = call_kwargs.kwargs.get("node_postprocessors")
            assert postprocessors is None

    @patch("src.document_processing.kb_manager.settings")
    def test_overfetch_multiplier_with_reranking(self, mock_settings):
        """Test that retrieval_k is 3x top_k when reranking is active."""
        mock_settings.reranking_enabled = True
        mock_settings.cohere_api_key = "test-key"
        mock_settings.reranking_model = "rerank-v3.5"
        mock_settings.reranking_top_n = None
        mock_settings.hybrid_search_enabled = False
        mock_settings.top_k_retrieval = 5

        from src.document_processing.kb_manager import KnowledgeBaseManager

        kb = MagicMock(spec=KnowledgeBaseManager)
        kb.index = MagicMock()
        kb.embed_model = MagicMock()

        mock_retriever = MagicMock()
        kb.index.as_retriever.return_value = mock_retriever

        with patch(
            "src.document_processing.kb_manager.RetrieverQueryEngine"
        ) as mock_rqe:
            mock_rqe.from_args.return_value = MagicMock()

            KnowledgeBaseManager.get_query_engine(kb, top_k=5, llm=MagicMock())

            # Vector retriever should be called with 3x top_k
            kb.index.as_retriever.assert_called_once_with(
                similarity_top_k=15, embed_model=kb.embed_model
            )
