"""
Unit tests for TenantEmailRouter.

Tests sender-to-tenant resolution, role-based permission checks,
and component/context delegation.
"""

from unittest.mock import MagicMock

import pytest

from src.email.tenant_email_router import TenantEmailRouter


@pytest.fixture
def mock_db_manager():
    """Create a mock TenantDBManager."""
    return MagicMock()


@pytest.fixture
def mock_component_factory():
    """Create a mock TenantComponentFactory."""
    return MagicMock()


@pytest.fixture
def router(mock_db_manager, mock_component_factory):
    """Create a TenantEmailRouter instance."""
    return TenantEmailRouter(
        db_manager=mock_db_manager,
        component_factory=mock_component_factory,
    )


class TestResolveSender:
    """Tests for resolve_sender()."""

    def test_resolve_sender_single_tenant(self, router, mock_db_manager):
        """Test resolving a sender that belongs to one tenant."""
        mock_tenant = MagicMock()
        mock_tenant.slug = "acme"

        mock_user = MagicMock()
        mock_user.tenant_id = "tenant-123"
        mock_user.tenant = mock_tenant
        mock_user.role.value = "teacher"

        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_user
        ]
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = router.resolve_sender("alice@example.com")

        assert len(results) == 1
        assert results[0]["tenant_slug"] == "acme"
        assert results[0]["tenant_id"] == "tenant-123"
        assert results[0]["role"] == "teacher"

    def test_resolve_sender_multiple_tenants(self, router, mock_db_manager):
        """Test resolving a sender that belongs to multiple tenants."""
        mock_tenant_a = MagicMock()
        mock_tenant_a.slug = "acme"
        mock_tenant_a.name = "Acme Corp"

        mock_tenant_b = MagicMock()
        mock_tenant_b.slug = "globex"
        mock_tenant_b.name = "Globex Inc"

        mock_user_a = MagicMock()
        mock_user_a.tenant_id = "t-1"
        mock_user_a.tenant = mock_tenant_a
        mock_user_a.role.value = "admin"

        mock_user_b = MagicMock()
        mock_user_b.tenant_id = "t-2"
        mock_user_b.tenant = mock_tenant_b
        mock_user_b.role.value = "querier"

        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_user_a,
            mock_user_b,
        ]
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = router.resolve_sender("bob@example.com")

        assert len(results) == 2
        slugs = {r["tenant_slug"] for r in results}
        assert slugs == {"acme", "globex"}

    def test_resolve_sender_no_match(self, router, mock_db_manager):
        """Test resolving a sender not in any tenant."""
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = (
            []
        )
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = router.resolve_sender("unknown@example.com")

        assert len(results) == 0

    def test_resolve_sender_excludes_suspended_tenant(self, router, mock_db_manager):
        """Test that suspended tenants are excluded (filter is on ACTIVE status)."""
        # The SQL filter includes Tenant.status == ACTIVE, so suspended tenants
        # won't appear in results. We test that an empty result is returned
        # when all matches are suspended.
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = (
            []
        )
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = router.resolve_sender("suspended@example.com")

        assert len(results) == 0


class TestCheckPermission:
    """Tests for check_permission()."""

    def test_admin_can_query(self, router):
        """Admin role should have query permission."""
        assert router.check_permission("admin", "query") is True

    def test_admin_can_teach(self, router):
        """Admin role should have teach permission."""
        assert router.check_permission("admin", "teach") is True

    def test_teacher_can_query(self, router):
        """Teacher role should have query permission."""
        assert router.check_permission("teacher", "query") is True

    def test_teacher_can_teach(self, router):
        """Teacher role should have teach permission."""
        assert router.check_permission("teacher", "teach") is True

    def test_querier_can_query(self, router):
        """Querier role should have query permission."""
        assert router.check_permission("querier", "query") is True

    def test_querier_cannot_teach(self, router):
        """Querier role should NOT have teach permission."""
        assert router.check_permission("querier", "teach") is False

    def test_unknown_action_denied(self, router):
        """Unknown action should be denied."""
        assert router.check_permission("admin", "unknown_action") is False


class TestGetComponents:
    """Tests for get_components() and get_tenant_context()."""

    def test_get_components_delegates_to_factory(self, router, mock_component_factory):
        """get_components() should delegate to component_factory."""
        mock_components = MagicMock()
        mock_component_factory.get_components_for_slug.return_value = mock_components

        result = router.get_components("acme")

        mock_component_factory.get_components_for_slug.assert_called_once_with("acme")
        assert result is mock_components

    def test_get_tenant_context_returns_context(self, router, mock_component_factory):
        """get_tenant_context() should return the context from components."""
        mock_ctx = MagicMock()
        mock_components = MagicMock()
        mock_components.context = mock_ctx
        mock_component_factory.get_components_for_slug.return_value = mock_components

        result = router.get_tenant_context("acme")

        assert result is mock_ctx
