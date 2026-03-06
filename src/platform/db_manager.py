"""
Tenant-aware database connection manager.

Manages per-tenant database connections with lazy initialization and
LRU eviction. Also manages the shared platform database connection.
"""

import logging
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, make_transient, sessionmaker

from src.config import settings
from src.email.db_models import Base as TenantBase
from src.platform.models import PlatformBase, Tenant

logger = logging.getLogger(__name__)


class TenantDBManager:
    """
    Manages database connections for multi-tenant deployments.

    Maintains a shared platform DB connection and lazily-initialized
    per-tenant DB connections with LRU eviction to control resource usage.

    Attributes:
        platform_engine: SQLAlchemy engine for platform database
        _tenant_engines: LRU cache of tenant SQLAlchemy engines
        _max_cached: Maximum tenant connections to cache
        _lock: Thread lock for cache operations
    """

    def __init__(
        self,
        max_cached: Optional[int] = None,
        pool_size_per_tenant: Optional[int] = None,
    ):
        """
        Initialize tenant database manager.

        Args:
            max_cached: Max tenant DB engines to keep in LRU cache.
            pool_size_per_tenant: Connection pool size per tenant engine.
        """
        self._max_cached = max_cached or settings.tenant_db_max_cached
        self._pool_size = pool_size_per_tenant or settings.tenant_db_pool_size
        self._tenant_engines: OrderedDict[str, _TenantEngineEntry] = OrderedDict()
        self._lock = threading.Lock()

        # Initialize platform database connection
        self.platform_engine = self._create_platform_engine()
        self._PlatformSession = sessionmaker(
            autocommit=False, autoflush=False, bind=self.platform_engine
        )

        logger.info(
            f"TenantDBManager initialized: max_cached={self._max_cached}, "
            f"pool_size_per_tenant={self._pool_size}"
        )

    def _create_platform_engine(self) -> Engine:
        """
        Create SQLAlchemy engine for the platform database.

        Returns:
            Configured SQLAlchemy engine.
        """
        url = settings.get_platform_database_url()
        logger.debug(f"Creating platform DB engine: {url.split('@')[-1]}")

        return create_engine(
            url,
            pool_size=settings.db_pool_size,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,
            echo=settings.debug,
        )

    def _create_tenant_engine(self, db_name: str) -> Engine:
        """
        Create SQLAlchemy engine for a tenant database.

        Args:
            db_name: Tenant database name.

        Returns:
            Configured SQLAlchemy engine.
        """
        url = settings.get_tenant_database_url(db_name)
        logger.debug(f"Creating tenant DB engine for: {db_name}")

        return create_engine(
            url,
            pool_size=self._pool_size,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,
            echo=settings.debug,
        )

    def init_platform_db(self) -> None:
        """
        Create all platform database tables.

        Creates tables for Tenant, TenantUser, TenantEncryptionKey.
        Safe to call multiple times (idempotent).
        Also runs migrations for new columns on existing tables.
        """
        logger.info("Creating platform database tables...")
        PlatformBase.metadata.create_all(bind=self.platform_engine)
        self._migrate_billing_columns()
        logger.info("Platform database tables created successfully")

    def _migrate_billing_columns(self) -> None:
        """Add billing columns to tenants table if they don't exist.

        This handles upgrading existing databases that were created before
        billing fields were added to the Tenant model.
        """
        inspector = inspect(self.platform_engine)
        if "tenants" not in inspector.get_table_names():
            return

        existing_columns = {col["name"] for col in inspector.get_columns("tenants")}
        migrations = []

        if "plan" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN plan "
                "ENUM('FREE','LITE','TEAM','DEPARTMENT') "
                "NOT NULL DEFAULT 'DEPARTMENT'"
            )
        if "subscription_status" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN subscription_status "
                "ENUM('TRIALING','ACTIVE','PAST_DUE','CANCELLED') "
                "NOT NULL DEFAULT 'TRIALING'"
            )
        if "trial_ends_at" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN trial_ends_at DATETIME NULL"
            )
        if "paddle_customer_id" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN paddle_customer_id " "VARCHAR(255) NULL"
            )
            migrations.append(
                "CREATE INDEX idx_tenant_paddle_customer "
                "ON tenants (paddle_customer_id)"
            )
        if "paddle_subscription_id" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN paddle_subscription_id "
                "VARCHAR(255) NULL"
            )
            migrations.append(
                "CREATE INDEX idx_tenant_paddle_subscription "
                "ON tenants (paddle_subscription_id)"
            )
        if "paddle_subscription_scheduled_change" not in existing_columns:
            migrations.append(
                "ALTER TABLE tenants ADD COLUMN "
                "paddle_subscription_scheduled_change JSON NULL"
            )

        if migrations:
            logger.info("Running billing column migrations on tenants table...")
            with self.platform_engine.connect() as conn:
                for sql in migrations:
                    try:
                        conn.execute(text(sql))
                    except Exception as e:
                        # Ignore if column/index already exists (race condition)
                        if "Duplicate" not in str(e):
                            logger.warning("Migration warning: %s", e)
                conn.commit()
            logger.info("Billing column migrations complete")

        # Fix enum case: early migration used lowercase values but SQLAlchemy
        # expects uppercase enum names.  This ALTER is idempotent.
        if "plan" in existing_columns:
            fixup_sqls = [
                "ALTER TABLE tenants MODIFY COLUMN plan "
                "ENUM('FREE','LITE','TEAM','DEPARTMENT') "
                "NOT NULL DEFAULT 'DEPARTMENT'",
                "ALTER TABLE tenants MODIFY COLUMN subscription_status "
                "ENUM('TRIALING','ACTIVE','PAST_DUE','CANCELLED') "
                "NOT NULL DEFAULT 'TRIALING'",
            ]
            with self.platform_engine.connect() as conn:
                for sql in fixup_sqls:
                    try:
                        conn.execute(text(sql))
                    except Exception as e:
                        logger.debug("Enum fixup skipped: %s", e)
                conn.commit()

    def init_tenant_db(self, db_name: str) -> None:
        """
        Create all tables in a tenant database.

        Creates tables for tenant-specific models (ProcessedMessage,
        Conversation, ConversationMessage, etc.).

        Args:
            db_name: Tenant database name.
        """
        logger.info(f"Creating tenant database tables for: {db_name}")
        engine = self._get_or_create_tenant_engine(db_name)
        TenantBase.metadata.create_all(bind=engine)
        logger.info(f"Tenant database tables created for: {db_name}")

    def create_tenant_database(self, db_name: str) -> bool:
        """
        Create a new tenant database (MariaDB CREATE DATABASE).

        Args:
            db_name: Name for the new database.

        Returns:
            True if created successfully, False otherwise.
        """
        try:
            # Use platform engine to execute CREATE DATABASE
            with self.platform_engine.connect() as conn:
                # Must use raw connection for DDL outside transaction
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))
                conn.commit()
            logger.info(f"Created tenant database: {db_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create tenant database {db_name}: {e}")
            return False

    def drop_tenant_database(self, db_name: str) -> bool:
        """
        Drop a tenant database.

        WARNING: This permanently deletes all data in the database.

        Args:
            db_name: Name of the database to drop.

        Returns:
            True if dropped successfully, False otherwise.
        """
        try:
            # First evict from cache
            self._evict_tenant(db_name)

            # Drop the database
            with self.platform_engine.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
                conn.commit()
            logger.info(f"Dropped tenant database: {db_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop tenant database {db_name}: {e}")
            return False

    def _get_or_create_tenant_engine(self, db_name: str) -> Engine:
        """
        Get or create a tenant database engine with LRU tracking.

        Args:
            db_name: Tenant database name.

        Returns:
            SQLAlchemy engine for the tenant.
        """
        with self._lock:
            if db_name in self._tenant_engines:
                # Move to end (most recently used)
                entry = self._tenant_engines.pop(db_name)
                entry.last_used = time.time()
                self._tenant_engines[db_name] = entry
                return entry.engine

            # Create new engine
            engine = self._create_tenant_engine(db_name)
            entry = _TenantEngineEntry(engine=engine)
            self._tenant_engines[db_name] = entry

            # Evict LRU entries if over limit
            while len(self._tenant_engines) > self._max_cached:
                oldest_key, oldest_entry = self._tenant_engines.popitem(last=False)
                logger.info(f"Evicting tenant DB engine from cache: {oldest_key}")
                try:
                    oldest_entry.engine.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing evicted engine {oldest_key}: {e}")

            return engine

    def _evict_tenant(self, db_name: str) -> None:
        """
        Remove a tenant engine from the cache and dispose it.

        Args:
            db_name: Tenant database name.
        """
        with self._lock:
            if db_name in self._tenant_engines:
                entry = self._tenant_engines.pop(db_name)
                try:
                    entry.engine.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing engine for {db_name}: {e}")

    @contextmanager
    def get_platform_session(self) -> Generator[Session, None, None]:
        """
        Context manager for platform database sessions.

        Yields:
            SQLAlchemy session for platform DB operations.
        """
        session = self._PlatformSession()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Platform DB session rolled back: {e}")
            raise
        finally:
            session.close()

    @contextmanager
    def get_tenant_session(self, tenant: Tenant) -> Generator[Session, None, None]:
        """
        Context manager for tenant database sessions.

        Args:
            tenant: Tenant model instance (needs db_name).

        Yields:
            SQLAlchemy session for tenant DB operations.
        """
        engine = self._get_or_create_tenant_engine(tenant.db_name)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Tenant DB session rolled back ({tenant.slug}): {e}")
            raise
        finally:
            session.close()

    @contextmanager
    def get_tenant_session_by_name(
        self, db_name: str
    ) -> Generator[Session, None, None]:
        """
        Context manager for tenant database sessions by database name.

        Args:
            db_name: Tenant database name.

        Yields:
            SQLAlchemy session for tenant DB operations.
        """
        engine = self._get_or_create_tenant_engine(db_name)
        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Tenant DB session rolled back ({db_name}): {e}")
            raise
        finally:
            session.close()

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """
        Look up a tenant by slug from the platform database.

        Args:
            slug: Tenant slug (e.g., "acme").

        Returns:
            Tenant model or None if not found.
        """
        with self.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if tenant:
                session.expunge(tenant)
                # Reason: make_transient prevents DetachedInstanceError when
                # accessing attributes after the session closes
                make_transient(tenant)
            return tenant

    def get_tenant_by_email(self, email_address: str) -> Optional[Tenant]:
        """
        Look up a tenant by email address.

        Args:
            email_address: Tenant email (e.g., "acme@berengar.io").

        Returns:
            Tenant model or None if not found.
        """
        with self.get_platform_session() as session:
            tenant = (
                session.query(Tenant)
                .filter(Tenant.email_address == email_address)
                .first()
            )
            if tenant:
                session.expunge(tenant)
                make_transient(tenant)
            return tenant

    def get_active_tenants(self) -> list:
        """
        Get all active tenants.

        Returns:
            List of active Tenant models.
        """
        with self.get_platform_session() as session:
            from src.platform.models import TenantStatus

            tenants = (
                session.query(Tenant).filter(Tenant.status == TenantStatus.ACTIVE).all()
            )
            for t in tenants:
                session.expunge(t)
                make_transient(t)
            return tenants

    def test_platform_connection(self) -> bool:
        """
        Test platform database connection.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            with self.platform_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Platform database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Platform database connection test failed: {e}")
            return False

    def test_tenant_connection(self, db_name: str) -> bool:
        """
        Test tenant database connection.

        Args:
            db_name: Tenant database name.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            engine = self._get_or_create_tenant_engine(db_name)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"Tenant database connection test successful: {db_name}")
            return True
        except Exception as e:
            logger.error(f"Tenant database connection test failed ({db_name}): {e}")
            return False

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the tenant engine cache.

        Returns:
            Dictionary with cache statistics.
        """
        with self._lock:
            entries = {}
            for db_name, entry in self._tenant_engines.items():
                entries[db_name] = {
                    "last_used": entry.last_used,
                    "age_seconds": time.time() - entry.last_used,
                }

            return {
                "cached_tenants": len(self._tenant_engines),
                "max_cached": self._max_cached,
                "pool_size_per_tenant": self._pool_size,
                "entries": entries,
            }

    def close(self) -> None:
        """
        Close all database connections.

        Disposes platform engine and all cached tenant engines.
        """
        logger.info("Closing TenantDBManager...")

        # Close all tenant engines
        with self._lock:
            for db_name, entry in self._tenant_engines.items():
                try:
                    entry.engine.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing tenant engine {db_name}: {e}")
            self._tenant_engines.clear()

        # Close platform engine
        self.platform_engine.dispose()
        logger.info("TenantDBManager closed")


class _TenantEngineEntry:
    """Internal wrapper for cached tenant engines with usage tracking."""

    __slots__ = ("engine", "last_used")

    def __init__(self, engine: Engine):
        self.engine = engine
        self.last_used = time.time()
