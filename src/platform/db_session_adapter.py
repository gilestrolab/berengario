"""
Database session adapter for multi-tenant ConversationManager integration.

Adapts TenantDBManager's get_tenant_session_by_name() to match the
get_session() interface that ConversationManager expects, enabling
per-tenant conversation storage without changing ConversationManager's code.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TenantDBSessionAdapter:
    """
    Adapts TenantDBManager to the DatabaseManager.get_session() interface.

    ConversationManager calls self.db_manager.get_session() to get a
    database session. This adapter wraps TenantDBManager so that
    get_session() delegates to get_tenant_session_by_name(db_name),
    routing queries to the correct tenant database.

    Attributes:
        _mgr: TenantDBManager instance.
        _db_name: Tenant database name to connect to.
    """

    def __init__(
        self,
        tenant_db_manager: "TenantDBManager",  # noqa: F821
        db_name: str,
    ):
        """
        Initialize adapter.

        Args:
            tenant_db_manager: TenantDBManager instance.
            db_name: Tenant database name (e.g., "tenant_acme").
        """
        self._mgr = tenant_db_manager
        self._db_name = db_name
        logger.debug(f"TenantDBSessionAdapter created for db: {db_name}")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Provide a database session for the configured tenant.

        Delegates to TenantDBManager.get_tenant_session_by_name().

        Yields:
            SQLAlchemy session for tenant DB operations.
        """
        with self._mgr.get_tenant_session_by_name(self._db_name) as session:
            yield session
