"""
Tenant component factory for multi-tenant deployments.

Creates and caches per-tenant stacks of data-layer components
(KnowledgeBaseManager, DocumentProcessor, RAGEngine, QueryHandler).
Uses LRU eviction to control memory usage, same pattern as TenantDBManager.
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from src.platform.tenant_context import TenantContext

logger = logging.getLogger(__name__)


@dataclass
class TenantComponents:
    """
    Bundle of per-tenant data-layer components.

    Attributes:
        context: The TenantContext used to build these components.
        kb_manager: KnowledgeBaseManager for this tenant's ChromaDB.
        doc_processor: DocumentProcessor for chunking documents.
        rag_engine: RAGEngine for query processing.
        query_handler: QueryHandler wrapping the RAG engine.
    """

    context: TenantContext
    kb_manager: "KnowledgeBaseManager"  # noqa: F821
    doc_processor: "DocumentProcessor"  # noqa: F821
    rag_engine: "RAGEngine"  # noqa: F821
    query_handler: "QueryHandler"  # noqa: F821


class _CacheEntry:
    """Internal wrapper for cached tenant components with usage tracking."""

    __slots__ = ("components", "last_used")

    def __init__(self, components: TenantComponents):
        self.components = components
        self.last_used = time.time()


class TenantComponentFactory:
    """
    LRU-cached factory for per-tenant component stacks.

    Thread-safe. Each tenant gets its own KnowledgeBaseManager,
    DocumentProcessor, RAGEngine, and QueryHandler configured
    via TenantContext.

    Attributes:
        _cache: LRU cache of tenant component stacks.
        _max_cached: Maximum entries to keep in cache.
        _lock: Thread lock for cache operations.
        _storage_backend: Storage backend for resolving tenant paths.
        _db_manager: TenantDBManager for looking up tenants by slug.
    """

    def __init__(
        self,
        storage_backend: Optional["StorageBackend"] = None,  # noqa: F821
        db_manager: Optional["TenantDBManager"] = None,  # noqa: F821
        max_cached: int = 20,
    ):
        """
        Initialize the component factory.

        Args:
            storage_backend: Storage backend for path resolution.
            db_manager: TenantDBManager for tenant lookups.
            max_cached: Maximum tenant component stacks to cache.
        """
        self._storage_backend = storage_backend
        self._db_manager = db_manager
        self._max_cached = max_cached
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

        logger.info(f"TenantComponentFactory initialized: max_cached={max_cached}")

    def get_components(self, ctx: TenantContext) -> TenantComponents:
        """
        Get or create component stack for a tenant context.

        Args:
            ctx: TenantContext with all tenant-specific configuration.

        Returns:
            TenantComponents with fully initialized component stack.
        """
        slug = ctx.tenant_slug

        with self._lock:
            if slug in self._cache:
                entry = self._cache.pop(slug)
                entry.last_used = time.time()
                self._cache[slug] = entry
                logger.debug(f"Cache hit for tenant components: {slug}")
                return entry.components

        # Build components outside lock (construction may be slow)
        components = self._build_components(ctx)

        with self._lock:
            # Double-check: another thread may have created it
            if slug in self._cache:
                entry = self._cache.pop(slug)
                entry.last_used = time.time()
                self._cache[slug] = entry
                return entry.components

            self._cache[slug] = _CacheEntry(components)

            # Evict LRU entries if over limit
            while len(self._cache) > self._max_cached:
                oldest_key, _ = self._cache.popitem(last=False)
                logger.info(f"Evicting tenant components from cache: {oldest_key}")

        logger.info(f"Created and cached components for tenant: {slug}")
        return components

    def get_components_for_slug(self, slug: str) -> TenantComponents:
        """
        Resolve slug to Tenant, build TenantContext, and get components.

        Convenience method that chains slug → Tenant → TenantContext → components.

        Args:
            slug: Tenant slug (e.g., "acme").

        Returns:
            TenantComponents for the tenant.

        Raises:
            ValueError: If tenant not found or not active.
        """
        if not self._db_manager:
            raise ValueError("db_manager required for slug-based lookup")
        if not self._storage_backend:
            raise ValueError("storage_backend required for slug-based lookup")

        # Check cache first to avoid DB lookup
        with self._lock:
            if slug in self._cache:
                entry = self._cache.pop(slug)
                entry.last_used = time.time()
                self._cache[slug] = entry
                return entry.components

        # Look up tenant from platform DB
        tenant = self._db_manager.get_tenant_by_slug(slug)
        if not tenant:
            raise ValueError(f"Tenant not found: {slug}")

        from src.platform.models import TenantStatus

        if tenant.status != TenantStatus.ACTIVE:
            raise ValueError(
                f"Tenant '{slug}' is not active (status: {tenant.status.value})"
            )

        ctx = TenantContext.from_tenant(tenant, self._storage_backend)
        return self.get_components(ctx)

    def evict(self, slug: str) -> None:
        """
        Remove a tenant's components from the cache.

        Use after tenant config changes to force re-creation on next access.

        Args:
            slug: Tenant slug to evict.
        """
        with self._lock:
            if slug in self._cache:
                self._cache.pop(slug)
                logger.info(f"Evicted tenant components: {slug}")

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the component cache.

        Returns:
            Dictionary with cache statistics.
        """
        with self._lock:
            entries = {}
            for slug, entry in self._cache.items():
                entries[slug] = {
                    "last_used": entry.last_used,
                    "age_seconds": time.time() - entry.last_used,
                }
            return {
                "cached_tenants": len(self._cache),
                "max_cached": self._max_cached,
                "entries": entries,
            }

    def _build_components(self, ctx: TenantContext) -> TenantComponents:
        """
        Build a full component stack for a tenant.

        Args:
            ctx: TenantContext with all configuration.

        Returns:
            TenantComponents with initialized components.
        """
        # Lazy imports to avoid circular dependencies
        from src.document_processing.document_processor import DocumentProcessor
        from src.document_processing.kb_manager import KnowledgeBaseManager
        from src.rag.query_handler import QueryHandler
        from src.rag.rag_engine import RAGEngine

        logger.info(f"Building component stack for tenant: {ctx.tenant_slug}")

        # 1. KnowledgeBaseManager with tenant-specific ChromaDB
        kb_manager = KnowledgeBaseManager(
            db_path=ctx.chroma_db_path,
            collection_name=f"{ctx.tenant_slug}_kb",
            embedding_model=ctx.openai_embedding_model,
            embedding_api_key=ctx.openai_api_key,
            embedding_api_base=ctx.openai_api_base,
        )

        # 2. DocumentProcessor with tenant-specific chunking
        doc_processor = DocumentProcessor(
            chunk_size=ctx.chunk_size,
            chunk_overlap=ctx.chunk_overlap,
        )

        # 3. RAGEngine with tenant context
        rag_engine = RAGEngine(
            kb_manager=kb_manager,
            llm_model=ctx.llm_model,
            tenant_context=ctx,
        )

        # 4. QueryHandler with tenant context
        query_handler = QueryHandler(
            rag_engine=rag_engine,
            tenant_context=ctx,
        )

        return TenantComponents(
            context=ctx,
            kb_manager=kb_manager,
            doc_processor=doc_processor,
            rag_engine=rag_engine,
            query_handler=query_handler,
        )

    def get_default_components(self) -> TenantComponents:
        """
        Get components for single-tenant mode (from global settings).

        Convenience method that creates a TenantContext from settings
        and returns the cached component stack.

        Returns:
            TenantComponents for the default single-tenant configuration.
        """
        ctx = TenantContext.from_settings()
        return self.get_components(ctx)
