"""
Tenant context for dependency injection into data-layer components.

Bundles all tenant-specific configuration (paths, RAG settings, LLM model,
prompts, feature flags) into a single frozen dataclass. Components receive
a TenantContext instead of reading from global settings directly, enabling
per-tenant isolation without changing component signatures.

Two factory classmethods:
- TenantContext.from_settings() — single-tenant mode
- TenantContext.from_tenant() — multi-tenant mode
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantContext:
    """
    Immutable bundle of tenant-specific configuration.

    Components accept an optional TenantContext. When None, they fall back
    to global settings (backward-compatible single-tenant behavior).

    Attributes:
        tenant_slug: URL-safe tenant identifier (e.g., "acme").
        tenant_id: UUID string (None in single-tenant mode).
        chroma_db_path: Path to ChromaDB storage for this tenant.
        documents_path: Path to source documents folder.
        kb_documents_path: Path to KB documents (attachments/uploads).
        kb_emails_path: Path to saved email copies.
        temp_dir: Temporary directory for email attachments.
        chunk_size: Document chunking size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        top_k_retrieval: Number of chunks to retrieve.
        similarity_threshold: Minimum similarity score.
        llm_model: LLM model name for this tenant.
        instance_name: Name of the assistant instance.
        instance_description: Description used in system prompts.
        organization: Organization name.
        custom_prompt: Custom RAG system prompt text (not file path).
        email_footer: Custom email footer text.
        query_optimization_enabled: Whether query optimization is on.
        query_optimization_model: Model for query optimization.
        doc_enhancement_enabled: Whether doc enhancement is on.
        openai_api_key: API key for embeddings.
        openai_api_base: API base URL for embeddings.
        openai_embedding_model: Embedding model name.
        openrouter_api_key: API key for LLM queries.
        openrouter_api_base: API base URL for LLM queries.
    """

    # Identity
    tenant_slug: str
    tenant_id: Optional[str]

    # Paths
    chroma_db_path: Path
    documents_path: Path
    kb_documents_path: Path
    kb_emails_path: Path
    temp_dir: Path

    # RAG config
    chunk_size: int
    chunk_overlap: int
    top_k_retrieval: int
    similarity_threshold: float

    # LLM config
    llm_model: str

    # Instance identity
    instance_name: str
    instance_description: str
    organization: str

    # Prompt and footer (text, not file paths)
    custom_prompt: Optional[str]
    email_footer: Optional[str]

    # Feature flags
    query_optimization_enabled: bool
    query_optimization_model: Optional[str]
    doc_enhancement_enabled: bool

    # Shared API keys (from global settings, not per-tenant)
    openai_api_key: str
    openai_api_base: str
    openai_embedding_model: str
    openrouter_api_key: str
    openrouter_api_base: str

    @classmethod
    def from_settings(cls) -> "TenantContext":
        """
        Create TenantContext from global settings (single-tenant mode).

        Reads all values from the global settings object, matching
        current single-tenant behavior exactly.

        Returns:
            TenantContext configured for single-tenant operation.
        """
        # Load custom prompt from file if configured
        custom_prompt = None
        if settings.rag_custom_prompt_file and settings.rag_custom_prompt_file.exists():
            try:
                custom_prompt = settings.rag_custom_prompt_file.read_text(
                    encoding="utf-8"
                ).strip()
            except Exception as e:
                logger.warning(f"Failed to load custom prompt file: {e}")

        # Load email footer from file if configured
        email_footer = None
        if (
            settings.email_custom_footer_file
            and settings.email_custom_footer_file.exists()
        ):
            try:
                email_footer = settings.email_custom_footer_file.read_text(
                    encoding="utf-8"
                ).strip()
            except Exception as e:
                logger.warning(f"Failed to load custom footer file: {e}")

        return cls(
            tenant_slug="default",
            tenant_id=None,
            chroma_db_path=settings.chroma_db_path,
            documents_path=settings.documents_path,
            kb_documents_path=settings.kb_documents_path,
            kb_emails_path=settings.kb_emails_path,
            temp_dir=settings.email_temp_dir,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            top_k_retrieval=settings.top_k_retrieval,
            similarity_threshold=settings.similarity_threshold,
            llm_model=settings.openrouter_model,
            instance_name=settings.instance_name,
            instance_description=settings.instance_description,
            organization=settings.organization,
            custom_prompt=custom_prompt,
            email_footer=email_footer,
            query_optimization_enabled=settings.query_optimization_enabled,
            query_optimization_model=settings.query_optimization_model,
            doc_enhancement_enabled=settings.doc_enhancement_enabled,
            openai_api_key=settings.openai_api_key,
            openai_api_base=settings.openai_api_base,
            openai_embedding_model=settings.openai_embedding_model,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_api_base=settings.openrouter_api_base,
        )

    @classmethod
    def from_tenant(
        cls,
        tenant: "Tenant",  # noqa: F821 - forward reference to avoid circular import
        storage_backend: "StorageBackend",  # noqa: F821
    ) -> "TenantContext":
        """
        Create TenantContext from a Tenant model (multi-tenant mode).

        Reads tenant-specific config from the Tenant model and resolves
        filesystem paths via the StorageBackend.

        Args:
            tenant: Tenant model instance from platform database.
            storage_backend: Storage backend for resolving paths.

        Returns:
            TenantContext configured for the specific tenant.
        """
        from src.platform.storage import LocalStorageBackend

        slug = tenant.slug

        # Resolve paths based on storage backend type
        if isinstance(storage_backend, LocalStorageBackend):
            tenant_root = storage_backend.get_tenant_path(slug)
            chroma_db_path = tenant_root / "chroma_db"
            documents_path = tenant_root / "documents"
            kb_documents_path = tenant_root / "kb" / "documents"
            kb_emails_path = tenant_root / "kb" / "emails"
            temp_dir = tenant_root / "temp"
        else:
            # S3 backend: ChromaDB still needs local path, use a local cache dir
            local_cache = Path(f"data/cache/{slug}")
            chroma_db_path = local_cache / "chroma_db"
            chroma_db_path.mkdir(parents=True, exist_ok=True)
            documents_path = local_cache / "documents"
            kb_documents_path = local_cache / "kb" / "documents"
            kb_emails_path = local_cache / "kb" / "emails"
            temp_dir = local_cache / "temp"

        # Tenant model fields with fallback to global defaults
        # Reason: Column defaults only apply via DB session, not in-memory
        chunk_size = tenant.chunk_size if tenant.chunk_size is not None else 1024
        chunk_overlap = (
            tenant.chunk_overlap if tenant.chunk_overlap is not None else 200
        )
        top_k = tenant.top_k_retrieval if tenant.top_k_retrieval is not None else 5
        similarity = (
            tenant.similarity_threshold
            if tenant.similarity_threshold is not None
            else 0.7
        )

        return cls(
            tenant_slug=slug,
            tenant_id=tenant.id,
            chroma_db_path=chroma_db_path,
            documents_path=documents_path,
            kb_documents_path=kb_documents_path,
            kb_emails_path=kb_emails_path,
            temp_dir=temp_dir,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k_retrieval=top_k,
            similarity_threshold=similarity,
            llm_model=tenant.llm_model or settings.openrouter_model,
            instance_name=tenant.name,
            instance_description=tenant.description or "",
            organization=tenant.organization or "",
            custom_prompt=tenant.custom_prompt,
            email_footer=tenant.email_footer,
            query_optimization_enabled=settings.query_optimization_enabled,
            query_optimization_model=settings.query_optimization_model,
            doc_enhancement_enabled=settings.doc_enhancement_enabled,
            openai_api_key=settings.openai_api_key,
            openai_api_base=settings.openai_api_base,
            openai_embedding_model=settings.openai_embedding_model,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_api_base=settings.openrouter_api_base,
        )
