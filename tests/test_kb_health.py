"""
Tests for KB Health metrics.

Tests KBManager.get_kb_health_metrics(), ConversationManager.get_retrieval_health_metrics(),
and the _compute_health_score helper.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.api.routes.analytics import _compute_health_score

# ---------------------------------------------------------------------------
# _compute_health_score tests
# ---------------------------------------------------------------------------


class TestComputeHealthScore:
    """Tests for the health score rubric."""

    def test_perfect_score(self):
        """Full score when KB is populated, fresh, fully cited, and relevant."""
        structural = {"total_documents": 10, "stale_count": 0}
        retrieval = {"citation_coverage_pct": 100, "low_relevance_rate": 0}
        result = _compute_health_score(structural, retrieval)
        assert result["total"] == 100
        assert result["factors"]["has_documents"]["score"] == 25
        assert result["factors"]["freshness"]["score"] == 25
        assert result["factors"]["citation_coverage"]["score"] == 25
        assert result["factors"]["relevance_quality"]["score"] == 25

    def test_empty_kb_score(self):
        """Zero score when KB is empty."""
        structural = {"total_documents": 0, "stale_count": 0}
        retrieval = {"citation_coverage_pct": 0, "low_relevance_rate": 0}
        result = _compute_health_score(structural, retrieval)
        assert result["total"] == 25  # relevance_quality gets 25 (0% low-rel)
        assert result["factors"]["has_documents"]["score"] == 0
        assert result["factors"]["freshness"]["score"] == 0

    def test_half_stale_docs(self):
        """Freshness score halved when half the docs are stale."""
        structural = {"total_documents": 10, "stale_count": 5}
        retrieval = {"citation_coverage_pct": 0, "low_relevance_rate": 0}
        result = _compute_health_score(structural, retrieval)
        assert result["factors"]["freshness"]["score"] == 12.5

    def test_partial_coverage(self):
        """Citation coverage score scales with percentage."""
        structural = {"total_documents": 10, "stale_count": 0}
        retrieval = {"citation_coverage_pct": 50, "low_relevance_rate": 0}
        result = _compute_health_score(structural, retrieval)
        assert result["factors"]["citation_coverage"]["score"] == 12.5

    def test_high_low_relevance(self):
        """Relevance quality drops when low-relevance rate is high."""
        structural = {"total_documents": 10, "stale_count": 0}
        retrieval = {"citation_coverage_pct": 100, "low_relevance_rate": 100}
        result = _compute_health_score(structural, retrieval)
        assert result["factors"]["relevance_quality"]["score"] == 0.0


# ---------------------------------------------------------------------------
# KBManager.get_kb_health_metrics tests
# ---------------------------------------------------------------------------


class TestKBHealthMetrics:
    """Tests for KBManager.get_kb_health_metrics()."""

    def _make_kb_manager(self):
        """Create a mocked KBManager without touching ChromaDB."""
        with patch(
            "src.document_processing.kb_manager.KnowledgeBaseManager.__init__",
            return_value=None,
        ):
            from src.document_processing.kb_manager import KnowledgeBaseManager

            kb = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
            kb.collection = MagicMock()
            return kb

    def test_empty_kb(self):
        """Empty collection returns zeroed metrics."""
        kb = self._make_kb_manager()
        kb.collection.get.return_value = {"metadatas": []}

        result = kb.get_kb_health_metrics()

        assert result["total_documents"] == 0
        assert result["total_chunks"] == 0
        assert result["avg_chunks_per_doc"] == 0
        assert result["documents"] == []
        assert result["file_type_breakdown"] == {}
        assert result["stale_count"] == 0

    def test_single_document_two_chunks(self):
        """Single document with two chunks produces correct counts."""
        kb = self._make_kb_manager()
        now = time.time()
        meta = {
            "file_hash": "abc123",
            "filename": "test.pdf",
            "file_type": "pdf",
            "source_type": "file",
            "enhanced": False,
            "file_mtime": now,
        }
        kb.collection.get.return_value = {"metadatas": [meta, meta]}

        result = kb.get_kb_health_metrics()

        assert result["total_documents"] == 1
        assert result["total_chunks"] == 2
        assert result["avg_chunks_per_doc"] == 2.0
        assert result["file_type_breakdown"] == {"pdf": 1}
        assert result["source_type_breakdown"] == {"file": 1}
        assert result["enhanced_count"] == 0
        assert result["stale_count"] == 0
        assert len(result["documents"]) == 1
        assert result["documents"][0]["chunks"] == 2

    def test_stale_document_detection(self):
        """Documents older than 90 days are counted as stale."""
        kb = self._make_kb_manager()
        old_ts = time.time() - (100 * 86400)  # 100 days ago
        meta = {
            "file_hash": "old_hash",
            "filename": "old_doc.txt",
            "file_type": "txt",
            "source_type": "file",
            "enhanced": False,
            "file_mtime": old_ts,
        }
        kb.collection.get.return_value = {"metadatas": [meta]}

        result = kb.get_kb_health_metrics()

        assert result["stale_count"] == 1
        assert result["avg_age_days"] > 90

    def test_multiple_document_types(self):
        """Multiple document types are correctly broken down."""
        kb = self._make_kb_manager()
        now = time.time()
        metas = [
            {
                "file_hash": "h1",
                "filename": "a.pdf",
                "file_type": "pdf",
                "source_type": "file",
                "enhanced": True,
                "file_mtime": now,
            },
            {
                "file_hash": "h2",
                "filename": "b.csv",
                "file_type": "csv",
                "source_type": "file",
                "enhanced": True,
                "file_mtime": now,
            },
            {
                "file_hash": "h3",
                "filename": "c.html",
                "file_type": "html",
                "source_type": "web",
                "enhanced": False,
                "last_crawled": now,
            },
        ]
        kb.collection.get.return_value = {"metadatas": metas}

        result = kb.get_kb_health_metrics()

        assert result["total_documents"] == 3
        assert result["file_type_breakdown"] == {"pdf": 1, "csv": 1, "html": 1}
        assert result["source_type_breakdown"] == {"file": 2, "web": 1}
        assert result["enhanced_count"] == 2
        assert result["enhanced_percentage"] == pytest.approx(66.7, abs=0.1)

    def test_chunk_distribution(self):
        """Chunk distribution stats are calculated correctly."""
        kb = self._make_kb_manager()
        now = time.time()
        # Doc h1 has 3 chunks, doc h2 has 1 chunk
        metas = [
            {
                "file_hash": "h1",
                "filename": "a.pdf",
                "file_type": "pdf",
                "source_type": "file",
                "file_mtime": now,
            },
            {
                "file_hash": "h1",
                "filename": "a.pdf",
                "file_type": "pdf",
                "source_type": "file",
                "file_mtime": now,
            },
            {
                "file_hash": "h1",
                "filename": "a.pdf",
                "file_type": "pdf",
                "source_type": "file",
                "file_mtime": now,
            },
            {
                "file_hash": "h2",
                "filename": "b.txt",
                "file_type": "txt",
                "source_type": "file",
                "file_mtime": now,
            },
        ]
        kb.collection.get.return_value = {"metadatas": metas}

        result = kb.get_kb_health_metrics()

        assert result["chunk_distribution"]["min"] == 1
        assert result["chunk_distribution"]["max"] == 3
        assert result["chunk_distribution"]["avg"] == 2.0
        assert result["chunk_distribution"]["median"] == 2.0


# ---------------------------------------------------------------------------
# ConversationManager.get_retrieval_health_metrics tests
# ---------------------------------------------------------------------------


class TestRetrievalHealthMetrics:
    """Tests for ConversationManager.get_retrieval_health_metrics()."""

    def _make_cm(self, reply_rows):
        """Create a ConversationManager with mocked DB returning given reply rows."""

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Build the chain: query().filter().filter()... .all()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = reply_rows

        with patch(
            "src.email.conversation_manager.ConversationManager.__init__",
            return_value=None,
        ):
            from src.email.conversation_manager import ConversationManager

            cm = ConversationManager.__new__(ConversationManager)
            cm.db_manager = mock_db
            return cm

    def _make_reply(self, sources):
        """Create a mock reply message with given sources_used."""
        msg = MagicMock()
        msg.message_type = MagicMock()
        msg.message_type.value = "reply"
        msg.sources_used = sources
        return msg

    def test_no_replies(self):
        """No replies produces zero metrics."""
        cm = self._make_cm([])
        result = cm.get_retrieval_health_metrics(
            kb_document_filenames=["a.pdf", "b.pdf"]
        )
        assert result["total_replies_analyzed"] == 0
        assert result["citation_coverage_pct"] == 0
        assert result["uncited_count"] == 2
        assert set(result["uncited_documents"]) == {"a.pdf", "b.pdf"}

    def test_full_coverage(self):
        """All KB docs cited produces 100% coverage."""
        replies = [
            self._make_reply(
                [
                    {"filename": "a.pdf", "score": 0.9},
                    {"filename": "b.pdf", "score": 0.8},
                ]
            ),
        ]
        cm = self._make_cm(replies)
        result = cm.get_retrieval_health_metrics(
            kb_document_filenames=["a.pdf", "b.pdf"]
        )
        assert result["citation_coverage_pct"] == 100.0
        assert result["uncited_count"] == 0
        assert result["low_relevance_count"] == 0

    def test_partial_coverage(self):
        """Only one of two docs cited produces 50% coverage."""
        replies = [
            self._make_reply([{"filename": "a.pdf", "score": 0.9}]),
        ]
        cm = self._make_cm(replies)
        result = cm.get_retrieval_health_metrics(
            kb_document_filenames=["a.pdf", "b.pdf"]
        )
        assert result["citation_coverage_pct"] == 50.0
        assert result["uncited_documents"] == ["b.pdf"]

    def test_low_relevance_detection(self):
        """Replies with all scores below threshold are counted as low relevance."""
        replies = [
            self._make_reply([{"filename": "a.pdf", "score": 0.1}]),
            self._make_reply([{"filename": "a.pdf", "score": 0.5}]),
        ]
        cm = self._make_cm(replies)
        result = cm.get_retrieval_health_metrics(
            kb_document_filenames=["a.pdf"],
            similarity_threshold=0.3,
        )
        assert result["low_relevance_count"] == 1
        assert result["low_relevance_rate"] == 50.0

    def test_empty_kb_filenames(self):
        """Empty KB filename list produces 0% coverage."""
        replies = [
            self._make_reply([{"filename": "a.pdf", "score": 0.9}]),
        ]
        cm = self._make_cm(replies)
        result = cm.get_retrieval_health_metrics(kb_document_filenames=[])
        assert result["citation_coverage_pct"] == 0
        assert result["total_kb_documents"] == 0
