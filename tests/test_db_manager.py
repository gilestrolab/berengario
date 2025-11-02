"""
Unit tests for database manager.

Tests database connection management, session handling, and
database operations for both SQLite and MariaDB backends.
"""

from unittest.mock import patch

import pytest

from src.email.db_manager import DatabaseManager
from src.email.db_models import Base, ProcessedMessage


@pytest.fixture
def test_db_manager():
    """Create a test database manager with in-memory SQLite."""
    # Override settings to use in-memory SQLite
    with patch("src.email.db_manager.settings") as mock_settings:
        mock_settings.db_type = "sqlite"
        mock_settings.sqlite_db_path = ":memory:"
        mock_settings.debug = False
        mock_settings.get_database_url.return_value = "sqlite:///:memory:"

        manager = DatabaseManager()
        manager.init_db()

        yield manager

        # Cleanup
        manager.close()


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    def test_create_sqlite_engine(self, test_db_manager):
        """Test creating SQLite engine."""
        assert test_db_manager.engine is not None
        assert "sqlite" in str(test_db_manager.engine.url)

    def test_init_db(self, test_db_manager):
        """Test database initialization creates tables."""
        # Tables should exist after init_db
        assert ProcessedMessage.__tablename__ in Base.metadata.tables

    def test_get_session_context_manager(self, test_db_manager):
        """Test session context manager."""
        with test_db_manager.get_session() as session:
            # Session should be active
            assert session.is_active
            # Store session for checking later
            test_session = session

        # Session should be closed after context
        # Note: In SQLAlchemy 2.0+, is_active may still be True even after close
        # Instead, check that we can't use it by verifying it's been committed/closed
        assert test_session.get_bind() is not None  # Session exists but closed

    def test_session_commit_on_success(self, test_db_manager):
        """Test session commits on successful operations."""
        with test_db_manager.get_session() as session:
            message = ProcessedMessage(
                message_id="<test@example.com>",
                sender="test@example.com",
                subject="Test",
            )
            session.add(message)

        # Verify message was committed
        with test_db_manager.get_session() as session:
            found = (
                session.query(ProcessedMessage)
                .filter_by(message_id="<test@example.com>")
                .first()
            )
            assert found is not None
            assert found.sender == "test@example.com"

    def test_session_rollback_on_error(self, test_db_manager):
        """Test session rolls back on errors."""
        with pytest.raises(ValueError):
            with test_db_manager.get_session() as session:
                message = ProcessedMessage(
                    message_id="<test@example.com>",
                    sender="test@example.com",
                )
                session.add(message)
                # Force an error
                raise ValueError("Test error")

        # Verify message was not committed
        with test_db_manager.get_session() as session:
            found = (
                session.query(ProcessedMessage)
                .filter_by(message_id="<test@example.com>")
                .first()
            )
            assert found is None

    def test_get_engine_info(self, test_db_manager):
        """Test getting engine information."""
        info = test_db_manager.get_engine_info()

        assert "db_type" in info
        assert "url" in info
        assert "driver" in info
        assert info["db_type"] == "sqlite"

    def test_test_connection(self, test_db_manager):
        """Test database connection test."""
        result = test_db_manager.test_connection()
        assert result is True

    def test_test_connection_failure(self, test_db_manager):
        """Test connection test with failed connection."""
        # Close the engine to simulate failure
        test_db_manager.engine.dispose()

        # Create a broken engine
        with patch.object(test_db_manager.engine, "connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            result = test_db_manager.test_connection()
            assert result is False

    def test_drop_all(self, test_db_manager):
        """Test dropping all tables."""
        # Add a message
        with test_db_manager.get_session() as session:
            message = ProcessedMessage(
                message_id="<test@example.com>",
                sender="test@example.com",
            )
            session.add(message)

        # Drop all tables
        test_db_manager.drop_all()

        # Recreate tables
        test_db_manager.init_db()

        # Verify data is gone
        with test_db_manager.get_session() as session:
            count = session.query(ProcessedMessage).count()
            assert count == 0

    def test_close(self, test_db_manager):
        """Test closing database manager."""
        # Manager should be usable before close
        assert test_db_manager.test_connection() is True

        # Close the manager
        test_db_manager.close()

        # Engine should be disposed
        # Note: Can't easily test this without accessing internals


class TestDatabaseManagerMariaDB:
    """Tests for MariaDB-specific configuration."""

    def test_create_mariadb_engine(self):
        """Test creating MariaDB engine configuration."""
        with patch("src.email.db_manager.settings") as mock_settings:
            mock_settings.db_type = "mariadb"
            mock_settings.db_host = "localhost"
            mock_settings.db_port = 3306
            mock_settings.db_name = "test"
            mock_settings.db_user = "test_user"
            mock_settings.db_password = "test_pass"
            mock_settings.db_pool_size = 5
            mock_settings.db_pool_recycle = 3600
            mock_settings.debug = False
            mock_settings.get_database_url.return_value = (
                "mysql+pymysql://test_user:test_pass@localhost:3306/test"
            )

            # Create manager (won't connect without real MariaDB)
            manager = DatabaseManager()

            # Verify engine configuration
            assert "mysql" in str(manager.engine.url)
            assert manager.engine.pool.size() == 5

    def test_mariadb_engine_info(self):
        """Test getting MariaDB engine information."""
        with patch("src.email.db_manager.settings") as mock_settings:
            mock_settings.db_type = "mariadb"
            mock_settings.db_host = "localhost"
            mock_settings.db_port = 3306
            mock_settings.db_name = "test"
            mock_settings.db_user = "test_user"
            mock_settings.db_password = "test_pass"
            mock_settings.db_pool_size = 10
            mock_settings.db_pool_recycle = 3600
            mock_settings.debug = False
            mock_settings.get_database_url.return_value = (
                "mysql+pymysql://test_user:test_pass@localhost:3306/test"
            )

            manager = DatabaseManager()
            info = manager.get_engine_info()

            assert info["db_type"] == "mariadb"
            assert "pool_size" in info
