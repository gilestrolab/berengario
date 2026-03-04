"""
Database connection and session management.

This module provides database connection management using MariaDB/MySQL.
Uses SQLAlchemy for database abstraction.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.email.db_models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections and sessions.

    Uses MariaDB backend with automatic configuration based on settings.
    Provides session context managers for safe database operations.

    Attributes:
        engine: SQLAlchemy engine for database connections
        SessionLocal: Session factory for creating database sessions
    """

    def __init__(self):
        """Initialize database manager with engine and session factory."""
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        logger.info("DatabaseManager initialized with MariaDB backend")

    def _create_engine(self) -> Engine:
        """
        Create SQLAlchemy engine for MariaDB.

        Returns:
            Configured SQLAlchemy engine.
        """
        url = settings.get_database_url()
        logger.debug(
            f"Creating database engine: {url.split('@')[-1]}"
        )  # Don't log password

        return create_engine(
            url,
            pool_size=settings.db_pool_size,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,  # Verify connections are alive
            echo=settings.debug,
        )

    def init_db(self) -> None:
        """
        Create all database tables.

        Creates tables for all models defined in db_models.py if they don't
        already exist. Safe to call multiple times (idempotent).
        """
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")

    def drop_all(self) -> None:
        """
        Drop all database tables.

        WARNING: This will delete all data! Only use for testing or
        development cleanup.
        """
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(bind=self.engine)
        logger.info("All database tables dropped")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.

        Provides a database session with automatic commit/rollback handling.

        Yields:
            SQLAlchemy session for database operations.

        Raises:
            Exception: Re-raises any exception after rolling back the transaction.
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
            logger.debug("Database session committed successfully")
        except Exception as e:
            session.rollback()
            logger.error(f"Database session rolled back due to error: {e}")
            raise
        finally:
            session.close()
            logger.debug("Database session closed")

    def get_engine_info(self) -> dict:
        """
        Get information about the database engine.

        Returns:
            Dictionary with engine information (type, url, pool size, etc.).
        """
        info = {
            "db_type": "mariadb",
            "url": str(self.engine.url).split("@")[-1],  # Don't expose password
            "driver": self.engine.driver,
            "echo": self.engine.echo,
        }
        # Pool attributes vary by pool class (e.g. StaticPool lacks size())
        try:
            info["pool_size"] = self.engine.pool.size()
            info["pool_timeout"] = self.engine.pool.timeout
        except AttributeError:
            pass
        return info

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def close(self) -> None:
        """
        Close database engine and dispose of connection pool.
        """
        logger.info("Closing database engine...")
        self.engine.dispose()
        logger.info("Database engine closed")


# Global database manager instance
# Initialized on module import
db_manager = DatabaseManager()
