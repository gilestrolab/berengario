"""
Unit tests for TenantComponentFactory.

Tests component creation, LRU caching, eviction, and slug-based lookups.
Uses mocks to avoid actual ChromaDB/LLM initialization.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.platform.component_factory import (
    TenantComponentFactory,
    TenantComponents,
)
from src.platform.tenant_context import TenantContext


def _make_context(slug: str = "test", tmp_path: Path = Path("/tmp")) -> TenantContext:
    """Create a TenantContext for testing."""
    from src.config import settings

    return TenantContext(
        tenant_slug=slug,
        tenant_id=f"uuid-{slug}",
        tenant_db_name=f"tenant_{slug}",
        chroma_db_path=tmp_path / slug / "chroma_db",
        documents_path=tmp_path / slug / "documents",
        kb_documents_path=tmp_path / slug / "kb" / "documents",
        kb_emails_path=tmp_path / slug / "kb" / "emails",
        temp_dir=tmp_path / slug / "temp",
        chunk_size=1024,
        chunk_overlap=200,
        top_k_retrieval=5,
        similarity_threshold=0.7,
        llm_model="test-model",
        instance_name=f"{slug}-bot",
        instance_description=f"Bot for {slug}",
        organization=f"{slug} org",
        custom_prompt=None,
        email_footer=None,
        query_optimization_enabled=False,
        query_optimization_model=None,
        doc_enhancement_enabled=False,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_api_base,
        openai_embedding_model=settings.openai_embedding_model,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_api_base=settings.openrouter_api_base,
    )


class TestTenantComponentFactory:
    """Tests for TenantComponentFactory."""

    @pytest.fixture
    def factory(self):
        """Create a TenantComponentFactory with small cache."""
        return TenantComponentFactory(max_cached=3)

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_get_components_creates_and_caches(self, mock_build, factory, tmp_path):
        """Test that get_components creates components and caches them."""
        ctx = _make_context("acme", tmp_path)
        mock_components = MagicMock(spec=TenantComponents)
        mock_build.return_value = mock_components

        result = factory.get_components(ctx)

        assert result == mock_components
        mock_build.assert_called_once_with(ctx)

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_get_components_returns_cached(self, mock_build, factory, tmp_path):
        """Test that second call returns cached components without rebuilding."""
        ctx = _make_context("acme", tmp_path)
        mock_components = MagicMock(spec=TenantComponents)
        mock_build.return_value = mock_components

        result1 = factory.get_components(ctx)
        result2 = factory.get_components(ctx)

        assert result1 == result2
        # Only built once, second call is cache hit
        mock_build.assert_called_once()

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_lru_eviction(self, mock_build, tmp_path):
        """Test that oldest entry is evicted when cache exceeds max_cached."""
        factory = TenantComponentFactory(max_cached=2)
        mock_build.return_value = MagicMock(spec=TenantComponents)

        ctx1 = _make_context("tenant1", tmp_path)
        ctx2 = _make_context("tenant2", tmp_path)
        ctx3 = _make_context("tenant3", tmp_path)

        factory.get_components(ctx1)
        factory.get_components(ctx2)
        factory.get_components(ctx3)

        stats = factory.get_cache_stats()
        assert stats["cached_tenants"] == 2
        # tenant1 should have been evicted (oldest)
        assert "tenant1" not in stats["entries"]
        assert "tenant2" in stats["entries"]
        assert "tenant3" in stats["entries"]

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_evict_removes_from_cache(self, mock_build, factory, tmp_path):
        """Test that evict() removes tenant from cache."""
        ctx = _make_context("acme", tmp_path)
        mock_build.return_value = MagicMock(spec=TenantComponents)

        factory.get_components(ctx)
        assert factory.get_cache_stats()["cached_tenants"] == 1

        factory.evict("acme")
        assert factory.get_cache_stats()["cached_tenants"] == 0

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_evict_nonexistent_is_noop(self, mock_build, factory):
        """Test that evicting a non-cached slug is safe."""
        factory.evict("nonexistent")
        assert factory.get_cache_stats()["cached_tenants"] == 0

    @patch("src.platform.component_factory.TenantComponentFactory._build_components")
    def test_cache_stats(self, mock_build, factory, tmp_path):
        """Test get_cache_stats returns correct info."""
        mock_build.return_value = MagicMock(spec=TenantComponents)
        ctx = _make_context("acme", tmp_path)
        factory.get_components(ctx)

        stats = factory.get_cache_stats()
        assert stats["cached_tenants"] == 1
        assert stats["max_cached"] == 3
        assert "acme" in stats["entries"]
        assert "last_used" in stats["entries"]["acme"]
        assert "age_seconds" in stats["entries"]["acme"]

    def test_get_components_for_slug_without_db_manager(self, factory):
        """Test that slug lookup fails without db_manager."""
        with pytest.raises(ValueError, match="db_manager required"):
            factory.get_components_for_slug("acme")

    def test_get_components_for_slug_without_storage(self):
        """Test that slug lookup fails without storage_backend."""
        db_manager = MagicMock()
        factory = TenantComponentFactory(db_manager=db_manager)

        with pytest.raises(ValueError, match="storage_backend required"):
            factory.get_components_for_slug("acme")

    def test_get_components_for_slug_tenant_not_found(self):
        """Test that slug lookup fails when tenant doesn't exist."""
        db_manager = MagicMock()
        db_manager.get_tenant_by_slug.return_value = None
        storage = MagicMock()
        factory = TenantComponentFactory(db_manager=db_manager, storage_backend=storage)

        with pytest.raises(ValueError, match="Tenant not found"):
            factory.get_components_for_slug("nonexistent")

    def test_get_components_for_slug_inactive_tenant(self):
        """Test that slug lookup fails for non-active tenants."""
        from src.platform.models import TenantStatus

        tenant = MagicMock()
        tenant.slug = "suspended"
        tenant.status = TenantStatus.SUSPENDED

        db_manager = MagicMock()
        db_manager.get_tenant_by_slug.return_value = tenant
        storage = MagicMock()
        factory = TenantComponentFactory(db_manager=db_manager, storage_backend=storage)

        with pytest.raises(ValueError, match="not active"):
            factory.get_components_for_slug("suspended")


class TestBuildComponents:
    """Tests for _build_components (actual component creation)."""

    def test_build_creates_all_components(self, tmp_path):
        """Test that _build_components creates all four component types."""
        with (
            patch("src.document_processing.kb_manager.KnowledgeBaseManager") as mock_kb,
            patch(
                "src.document_processing.document_processor.DocumentProcessor"
            ) as mock_dp,
            patch("src.rag.rag_engine.RAGEngine") as mock_rag,
            patch("src.rag.query_handler.QueryHandler") as mock_qh,
        ):
            factory = TenantComponentFactory()
            ctx = _make_context("acme", tmp_path)

            result = factory._build_components(ctx)

            # Verify KnowledgeBaseManager created with tenant paths
            mock_kb.assert_called_once_with(
                db_path=ctx.chroma_db_path,
                collection_name="acme_kb",
                embedding_model=ctx.openai_embedding_model,
                embedding_api_key=ctx.openai_api_key,
                embedding_api_base=ctx.openai_api_base,
            )

            # Verify DocumentProcessor created with tenant chunking config
            mock_dp.assert_called_once_with(
                chunk_size=1024,
                chunk_overlap=200,
            )

            # Verify RAGEngine created with tenant context
            mock_rag.assert_called_once()
            rag_kwargs = mock_rag.call_args
            assert rag_kwargs.kwargs["tenant_context"] == ctx
            assert rag_kwargs.kwargs["llm_model"] == "test-model"

            # Verify QueryHandler created with tenant context
            mock_qh.assert_called_once()
            qh_kwargs = mock_qh.call_args
            assert qh_kwargs.kwargs["tenant_context"] == ctx

            # Verify result is TenantComponents
            assert isinstance(result, TenantComponents)
            assert result.context == ctx
