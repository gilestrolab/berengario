"""
Tests for team management API routes.

Verifies CRUD operations on TenantUser records via the team router.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.team import create_team_router


def _make_mock_session(
    tenant_id="t-123",
    tenant_slug="acme",
    email="admin@example.com",
    is_admin=True,
):
    """Create a mock session object."""
    session = MagicMock()
    session.tenant_id = tenant_id
    session.tenant_slug = tenant_slug
    session.email = email
    session.is_admin = is_admin
    return session


def _create_test_app(platform_db_manager, admin_session=None):
    """Create a test FastAPI app with team router."""
    app = FastAPI()

    if admin_session is None:
        admin_session = _make_mock_session()

    async def require_admin():
        return admin_session

    team_router = create_team_router(
        platform_db_manager=platform_db_manager,
        require_admin=require_admin,
    )
    app.include_router(team_router)
    return app


class TestTeamRouter:
    """Tests for team management endpoints."""

    def test_list_members_returns_empty(self):
        """List returns empty when no members exist."""

        @contextmanager
        def fake_platform_session():
            session = MagicMock()
            session.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            yield session

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_platform_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/team")
        assert response.status_code == 200
        assert response.json() == []

    def test_add_member_invalid_role(self):
        """Adding a member with invalid role returns 400."""

        @contextmanager
        def fake_platform_session():
            yield MagicMock()

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_platform_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/admin/team",
            json={"email": "user@example.com", "role": "invalid_role"},
        )
        assert response.status_code == 400
        assert "Invalid role" in response.json()["detail"]

    def test_add_member_no_tenant_selected(self):
        """Adding member without active tenant returns 400."""
        platform_db = MagicMock()

        admin_session = _make_mock_session(tenant_id=None)
        app = _create_test_app(platform_db, admin_session=admin_session)
        client = TestClient(app)

        response = client.post(
            "/api/admin/team",
            json={"email": "user@example.com", "role": "querier"},
        )
        assert response.status_code == 400
        assert "No active tenant" in response.json()["detail"]

    def test_remove_self_blocked(self):
        """Admins cannot remove themselves."""

        @contextmanager
        def fake_platform_session():
            session = MagicMock()
            user = MagicMock()
            user.email = "admin@example.com"
            user.id = 1
            session.query.return_value.filter.return_value.first.return_value = user
            yield session

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_platform_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.delete("/api/admin/team/1")
        assert response.status_code == 400
        assert "cannot remove yourself" in response.json()["detail"]

    def test_delete_nonexistent_member(self):
        """Deleting nonexistent member returns 404."""

        @contextmanager
        def fake_platform_session():
            session = MagicMock()
            session.query.return_value.filter.return_value.first.return_value = None
            yield session

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_platform_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.delete("/api/admin/team/999")
        assert response.status_code == 404
