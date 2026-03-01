"""
Tests for TenantDBSessionAdapter.

Verifies that the adapter correctly delegates get_session() calls
to TenantDBManager.get_tenant_session_by_name().
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from src.platform.db_session_adapter import TenantDBSessionAdapter


class TestTenantDBSessionAdapter:
    """Tests for TenantDBSessionAdapter."""

    def test_init_stores_manager_and_db_name(self):
        """Adapter stores the manager and db_name."""
        mgr = MagicMock()
        adapter = TenantDBSessionAdapter(mgr, "tenant_acme")
        assert adapter._mgr is mgr
        assert adapter._db_name == "tenant_acme"

    def test_get_session_delegates_to_manager(self):
        """get_session() delegates to get_tenant_session_by_name()."""
        mock_session = MagicMock()

        @contextmanager
        def fake_get_session(db_name):
            assert db_name == "tenant_acme"
            yield mock_session

        mgr = MagicMock()
        mgr.get_tenant_session_by_name = fake_get_session

        adapter = TenantDBSessionAdapter(mgr, "tenant_acme")

        with adapter.get_session() as session:
            assert session is mock_session

    def test_get_session_propagates_exceptions(self):
        """Exceptions from the underlying session propagate correctly."""

        @contextmanager
        def failing_get_session(db_name):
            raise RuntimeError("DB connection failed")
            yield  # required for contextmanager

        mgr = MagicMock()
        mgr.get_tenant_session_by_name = failing_get_session

        adapter = TenantDBSessionAdapter(mgr, "tenant_fail")

        with pytest.raises(RuntimeError, match="DB connection failed"):
            with adapter.get_session():
                pass

    def test_different_db_names_produce_different_adapters(self):
        """Each adapter uses its own db_name."""
        mgr = MagicMock()
        adapter1 = TenantDBSessionAdapter(mgr, "tenant_a")
        adapter2 = TenantDBSessionAdapter(mgr, "tenant_b")

        assert adapter1._db_name != adapter2._db_name
        assert adapter1._mgr is adapter2._mgr
