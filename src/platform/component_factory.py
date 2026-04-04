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
        conversation_manager: ConversationManager for this tenant's DB.
    """

    context: TenantContext
    kb_manager: "KnowledgeBaseManager"  # noqa: F821
    doc_processor: "DocumentProcessor"  # noqa: F821
    rag_engine: "RAGEngine"  # noqa: F821
    query_handler: "QueryHandler"  # noqa: F821
    conversation_manager: "ConversationManager"  # noqa: F821


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
        max_cached: int = 5,
        idle_ttl_seconds: int = 1800,
        query_engine_idle_seconds: int = 600,
        start_background_evictor: bool = False,
        evictor_interval_seconds: int = 300,
    ):
        """
        Initialize the component factory.

        Args:
            storage_backend: Storage backend for path resolution.
            db_manager: TenantDBManager for tenant lookups.
            max_cached: Maximum tenant component stacks to cache.
            idle_ttl_seconds: Evict whole tenant stacks idle this long.
            query_engine_idle_seconds: Evict RAGEngine._query_engine idle
                this long (releases BM25 retriever + LlamaIndex wrappers).
            start_background_evictor: Launch a daemon thread that runs
                periodic eviction. Enable in long-running services.
            evictor_interval_seconds: Sleep between background evictor runs.
        """
        self._storage_backend = storage_backend
        self._db_manager = db_manager
        self._max_cached = max_cached
        self._idle_ttl = idle_ttl_seconds
        self._query_engine_idle = query_engine_idle_seconds
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

        logger.info(
            f"TenantComponentFactory initialized: max_cached={max_cached}, "
            f"idle_ttl={idle_ttl_seconds}s, "
            f"query_engine_idle={query_engine_idle_seconds}s"
        )

        if start_background_evictor:
            self._evictor_stop = threading.Event()
            self._evictor_thread = threading.Thread(
                target=self._evictor_loop,
                args=(evictor_interval_seconds,),
                daemon=True,
                name="component-evictor",
            )
            self._evictor_thread.start()
            logger.info(
                f"Background evictor started (interval={evictor_interval_seconds}s)"
            )

    def get_components(self, ctx: TenantContext) -> TenantComponents:
        """
        Get or create component stack for a tenant context.

        Args:
            ctx: TenantContext with all tenant-specific configuration.

        Returns:
            TenantComponents with fully initialized component stack.
        """
        self.evict_idle()
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

        self.evict_idle()
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

    def evict_idle(self, max_idle_seconds: Optional[int] = None) -> int:
        """
        Remove entries idle longer than threshold.

        Args:
            max_idle_seconds: Override idle threshold (default: self._idle_ttl).

        Returns:
            Number of entries evicted.
        """
        threshold = max_idle_seconds if max_idle_seconds is not None else self._idle_ttl
        now = time.time()
        evicted = 0
        with self._lock:
            stale_keys = [
                k
                for k, entry in self._cache.items()
                if now - entry.last_used > threshold
            ]
            for key in stale_keys:
                self._cache.pop(key)
                evicted += 1
        if evicted:
            logger.info(f"Evicted {evicted} idle tenant(s) from component cache")
        return evicted

    def evict_idle_query_engines(self, max_idle_seconds: Optional[int] = None) -> int:
        """Drop RAGEngine._query_engine from cached components that are idle.

        Tenant stacks stay cached (cheap to keep), but the fat query engine
        (BM25 retriever + LlamaIndex wrappers) is released. Next query
        rebuilds it lazily.

        Returns:
            Number of query engines evicted.
        """
        threshold = (
            max_idle_seconds
            if max_idle_seconds is not None
            else self._query_engine_idle
        )
        evicted = 0
        with self._lock:
            entries = list(self._cache.values())
        for entry in entries:
            rag_engine = entry.components.rag_engine
            if rag_engine.evict_query_engine_if_idle(threshold):
                evicted += 1
        return evicted

    def _evictor_loop(self, interval_seconds: int) -> None:
        """Background loop that periodically evicts idle state."""
        while not self._evictor_stop.wait(interval_seconds):
            try:
                self.evict_idle()
                self.evict_idle_query_engines()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Evictor loop error: {exc}", exc_info=True)

    def stop_background_evictor(self) -> None:
        """Signal the background evictor thread to stop. For shutdown/tests."""
        if hasattr(self, "_evictor_stop"):
            self._evictor_stop.set()

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
        from src.email.conversation_manager import ConversationManager
        from src.platform.db_session_adapter import TenantDBSessionAdapter
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

        # 4. ConversationManager with tenant-specific DB (built before QueryHandler
        #    so it can be injected into tool context for database_tools)
        if ctx.tenant_db_name and self._db_manager:
            adapter = TenantDBSessionAdapter(self._db_manager, ctx.tenant_db_name)
            conv_manager = ConversationManager(db_manager=adapter)
        else:
            conv_manager = ConversationManager()

        # 5. QueryHandler with tenant context + conversation manager
        query_handler = QueryHandler(
            rag_engine=rag_engine,
            tenant_context=ctx,
            conversation_manager=conv_manager,
        )

        return TenantComponents(
            context=ctx,
            kb_manager=kb_manager,
            doc_processor=doc_processor,
            rag_engine=rag_engine,
            query_handler=query_handler,
            conversation_manager=conv_manager,
        )
