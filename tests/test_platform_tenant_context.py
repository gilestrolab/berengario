"""
Unit tests for TenantContext dataclass.

Tests both factory classmethods: from_settings() and from_tenant().
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.platform.models import Tenant, TenantStatus
from src.platform.tenant_context import TenantContext


class TestTenantContextFromSettings:
    """Tests for TenantContext.from_settings() single-tenant factory."""

    def test_basic_fields_from_settings(self):
        """Test that from_settings reads core fields from global settings."""
        ctx = TenantContext.from_settings()

        assert ctx.tenant_slug == "default"
        assert ctx.tenant_id is None
        assert isinstance(ctx.chroma_db_path, Path)
        assert isinstance(ctx.chunk_size, int)
        assert isinstance(ctx.chunk_overlap, int)
        assert isinstance(ctx.top_k_retrieval, int)
        assert isinstance(ctx.similarity_threshold, float)
        assert isinstance(ctx.llm_model, str)
        assert isinstance(ctx.instance_name, str)
        assert isinstance(ctx.openai_api_key, str)
        assert isinstance(ctx.openrouter_api_key, str)

    def test_frozen_immutability(self):
        """Test that TenantContext is immutable (frozen dataclass)."""
        ctx = TenantContext.from_settings()

        with pytest.raises(AttributeError):
            ctx.tenant_slug = "modified"

        with pytest.raises(AttributeError):
            ctx.chunk_size = 999

    def test_custom_prompt_none_when_no_file(self):
        """Test custom_prompt is None when no prompt file configured."""
        with patch("src.platform.tenant_context.settings") as mock_settings:
            mock_settings.rag_custom_prompt_file = None
            mock_settings.email_custom_footer_file = None
            mock_settings.chroma_db_path = Path("/tmp/chroma")
            mock_settings.documents_path = Path("/tmp/docs")
            mock_settings.kb_documents_path = Path("/tmp/kb/docs")
            mock_settings.kb_emails_path = Path("/tmp/kb/emails")
            mock_settings.email_temp_dir = Path("/tmp/temp")
            mock_settings.chunk_size = 1024
            mock_settings.chunk_overlap = 200
            mock_settings.top_k_retrieval = 5
            mock_settings.similarity_threshold = 0.7
            mock_settings.openrouter_model = "test-model"
            mock_settings.instance_name = "TestBot"
            mock_settings.instance_description = "Test"
            mock_settings.organization = "TestOrg"
            mock_settings.query_optimization_enabled = True
            mock_settings.query_optimization_model = None
            mock_settings.doc_enhancement_enabled = True
            mock_settings.openai_api_key = "key"
            mock_settings.openai_api_base = "https://api.test.com"
            mock_settings.openai_embedding_model = "text-embedding-3-small"
            mock_settings.openrouter_api_key = "key2"
            mock_settings.openrouter_api_base = "https://router.test.com"

            ctx = TenantContext.from_settings()
            assert ctx.custom_prompt is None
            assert ctx.email_footer is None

    def test_custom_prompt_loaded_from_file(self, tmp_path):
        """Test custom_prompt is loaded from file when configured."""
        prompt_file = tmp_path / "custom_prompt.txt"
        prompt_file.write_text("Use British English spelling")

        with patch("src.platform.tenant_context.settings") as mock_settings:
            mock_settings.rag_custom_prompt_file = prompt_file
            mock_settings.email_custom_footer_file = None
            mock_settings.chroma_db_path = Path("/tmp/chroma")
            mock_settings.documents_path = Path("/tmp/docs")
            mock_settings.kb_documents_path = Path("/tmp/kb/docs")
            mock_settings.kb_emails_path = Path("/tmp/kb/emails")
            mock_settings.email_temp_dir = Path("/tmp/temp")
            mock_settings.chunk_size = 1024
            mock_settings.chunk_overlap = 200
            mock_settings.top_k_retrieval = 5
            mock_settings.similarity_threshold = 0.7
            mock_settings.openrouter_model = "test-model"
            mock_settings.instance_name = "TestBot"
            mock_settings.instance_description = "Test"
            mock_settings.organization = "TestOrg"
            mock_settings.query_optimization_enabled = True
            mock_settings.query_optimization_model = None
            mock_settings.doc_enhancement_enabled = True
            mock_settings.openai_api_key = "key"
            mock_settings.openai_api_base = "https://api.test.com"
            mock_settings.openai_embedding_model = "text-embedding-3-small"
            mock_settings.openrouter_api_key = "key2"
            mock_settings.openrouter_api_base = "https://router.test.com"

            ctx = TenantContext.from_settings()
            assert ctx.custom_prompt == "Use British English spelling"

    def test_settings_values_match(self):
        """Test that from_settings produces context matching global settings."""
        from src.config import settings

        ctx = TenantContext.from_settings()

        assert ctx.chroma_db_path == settings.chroma_db_path
        assert ctx.documents_path == settings.documents_path
        assert ctx.chunk_size == settings.chunk_size
        assert ctx.chunk_overlap == settings.chunk_overlap
        assert ctx.top_k_retrieval == settings.top_k_retrieval
        assert ctx.similarity_threshold == settings.similarity_threshold
        assert ctx.llm_model == settings.openrouter_model
        assert ctx.instance_name == settings.instance_name
        assert ctx.openai_api_key == settings.openai_api_key


class TestTenantContextFromTenant:
    """Tests for TenantContext.from_tenant() multi-tenant factory."""

    @pytest.fixture
    def mock_tenant(self):
        """Create a mock Tenant model."""
        tenant = MagicMock(spec=Tenant)
        tenant.id = "test-uuid-1234"
        tenant.slug = "acme"
        tenant.name = "Acme Corp Bot"
        tenant.description = "AI assistant for Acme Corp"
        tenant.organization = "Acme Corporation"
        tenant.status = TenantStatus.ACTIVE
        tenant.email_address = "acme@berengar.io"
        tenant.custom_prompt = "Always be helpful"
        tenant.email_footer = "Powered by Acme"
        tenant.chunk_size = 2048
        tenant.chunk_overlap = 400
        tenant.top_k_retrieval = 10
        tenant.similarity_threshold = 0.8
        tenant.llm_model = "anthropic/claude-3.5-sonnet"
        tenant.db_name = "berengario_tenant_acme"
        tenant.storage_path = "acme"
        return tenant

    @pytest.fixture
    def mock_storage(self, tmp_path):
        """Create a mock LocalStorageBackend."""
        from src.platform.storage import LocalStorageBackend

        storage = LocalStorageBackend(base_path=str(tmp_path))
        return storage

    def test_from_tenant_basic(self, mock_tenant, mock_storage):
        """Test from_tenant creates context with tenant-specific values."""
        ctx = TenantContext.from_tenant(mock_tenant, mock_storage)

        assert ctx.tenant_slug == "acme"
        assert ctx.tenant_id == "test-uuid-1234"
        assert ctx.instance_name == "Acme Corp Bot"
        assert ctx.instance_description == "AI assistant for Acme Corp"
        assert ctx.organization == "Acme Corporation"
        assert ctx.custom_prompt == "Always be helpful"
        assert ctx.email_footer == "Powered by Acme"
        assert ctx.chunk_size == 2048
        assert ctx.chunk_overlap == 400
        assert ctx.top_k_retrieval == 10
        assert ctx.similarity_threshold == 0.8
        assert ctx.llm_model == "anthropic/claude-3.5-sonnet"

    def test_from_tenant_paths(self, mock_tenant, mock_storage, tmp_path):
        """Test from_tenant resolves paths via storage backend."""
        ctx = TenantContext.from_tenant(mock_tenant, mock_storage)

        assert ctx.chroma_db_path == tmp_path / "acme" / "chroma_db"
        assert ctx.documents_path == tmp_path / "acme" / "documents"
        assert ctx.kb_documents_path == tmp_path / "acme" / "kb" / "documents"
        assert ctx.kb_emails_path == tmp_path / "acme" / "kb" / "emails"
        assert ctx.temp_dir == tmp_path / "acme" / "temp"

    def test_from_tenant_shares_api_keys(self, mock_tenant, mock_storage):
        """Test that API keys come from global settings, not tenant."""
        from src.config import settings

        ctx = TenantContext.from_tenant(mock_tenant, mock_storage)

        assert ctx.openai_api_key == settings.openai_api_key
        assert ctx.openrouter_api_key == settings.openrouter_api_key
        assert ctx.openai_api_base == settings.openai_api_base

    def test_from_tenant_null_fields_fallback(self, mock_storage):
        """Test that None fields in Tenant model fall back to defaults."""
        tenant = MagicMock(spec=Tenant)
        tenant.id = "uuid-2"
        tenant.slug = "minimal"
        tenant.name = "Minimal Tenant"
        tenant.description = None
        tenant.organization = None
        tenant.custom_prompt = None
        tenant.email_footer = None
        tenant.chunk_size = None
        tenant.chunk_overlap = None
        tenant.top_k_retrieval = None
        tenant.similarity_threshold = None
        tenant.llm_model = None

        ctx = TenantContext.from_tenant(tenant, mock_storage)

        assert ctx.instance_description == ""
        assert ctx.organization == ""
        assert ctx.custom_prompt is None
        assert ctx.chunk_size == 1024
        assert ctx.chunk_overlap == 200
        assert ctx.top_k_retrieval == 5
        assert ctx.similarity_threshold == 0.7
        # llm_model falls back to settings.openrouter_model
        assert ctx.llm_model is not None

    def test_from_tenant_s3_backend(self, mock_tenant):
        """Test from_tenant with non-local storage uses cache directory."""
        mock_s3 = MagicMock()
        # Make isinstance check for LocalStorageBackend return False
        mock_s3.__class__ = type("MockS3", (), {})

        ctx = TenantContext.from_tenant(mock_tenant, mock_s3)

        assert "cache" in str(ctx.chroma_db_path)
        assert "acme" in str(ctx.chroma_db_path)


class TestTenantContextEquality:
    """Tests for TenantContext equality and hashing."""

    def test_same_settings_produces_equal_contexts(self):
        """Test that two from_settings() calls produce equal contexts."""
        ctx1 = TenantContext.from_settings()
        ctx2 = TenantContext.from_settings()
        assert ctx1 == ctx2

    def test_different_slugs_not_equal(self):
        """Test that contexts with different slugs are not equal."""
        ctx1 = TenantContext.from_settings()
        # Create a different context by modifying via constructor
        fields = {
            f.name: getattr(ctx1, f.name) for f in ctx1.__dataclass_fields__.values()
        }
        fields["tenant_slug"] = "other"
        ctx2 = TenantContext(**fields)
        assert ctx1 != ctx2
