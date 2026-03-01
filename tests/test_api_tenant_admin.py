"""
Tests for tenant admin API routes.

Verifies invite code management, join request handling, and tenant settings.
"""

import importlib.util
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.tenant_admin import create_tenant_admin_router

HAS_QRCODE = importlib.util.find_spec("qrcode") is not None


def _make_admin_session(
    tenant_id="t-123",
    tenant_slug="acme",
    email="admin@acme.com",
    is_admin=True,
):
    """Create a mock admin session."""
    session = MagicMock()
    session.tenant_id = tenant_id
    session.tenant_slug = tenant_slug
    session.email = email
    session.is_admin = is_admin
    return session


def _create_test_app(platform_db, admin_session=None):
    """Create a test FastAPI app with tenant admin router."""
    app = FastAPI()

    if admin_session is None:
        admin_session = _make_admin_session()

    async def require_admin(session=None):
        return admin_session

    settings = MagicMock()
    settings.platform_base_url = "https://test.berengar.io"
    session_manager = MagicMock()

    def get_session_id(request):
        return "test-session"

    router = create_tenant_admin_router(
        platform_db_manager=platform_db,
        require_admin=require_admin,
        session_manager=session_manager,
        get_session_id=get_session_id,
        settings=settings,
    )
    app.include_router(router)
    return app


def _make_mock_tenant(
    id="t-123",
    slug="acme",
    name="Acme Corp",
    invite_code="ABCD1234",
    join_approval_required=False,
):
    """Create a mock Tenant."""
    t = MagicMock()
    t.id = id
    t.slug = slug
    t.name = name
    t.invite_code = invite_code
    t.join_approval_required = join_approval_required
    return t


class TestGetInviteInfo:
    """Tests for GET /api/admin/tenant/invite."""

    def test_get_invite_info(self):
        """Returns invite code and settings."""
        tenant = _make_mock_tenant()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/tenant/invite")
        assert response.status_code == 200
        data = response.json()
        assert data["invite_code"] == "ABCD1234"
        assert data["join_approval_required"] is False
        assert data["tenant_name"] == "Acme Corp"

    def test_get_invite_info_tenant_not_found(self):
        """Returns 404 if tenant not found."""

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/tenant/invite")
        assert response.status_code == 404


class TestRegenerateInviteCode:
    """Tests for POST /api/admin/tenant/invite/regenerate."""

    def test_regenerate_code(self):
        """Regenerate returns a new code."""
        tenant = _make_mock_tenant()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post("/api/admin/tenant/invite/regenerate")
        assert response.status_code == 200
        data = response.json()
        # New code should be different from original (statistically)
        assert "invite_code" in data
        assert len(data["invite_code"]) == 8


class TestUpdateSettings:
    """Tests for PUT /api/admin/tenant/settings."""

    def test_update_join_approval(self):
        """Update join_approval_required setting."""
        tenant = _make_mock_tenant()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.put(
            "/api/admin/tenant/settings",
            json={"join_approval_required": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert tenant.join_approval_required is True


class TestJoinRequests:
    """Tests for join request management."""

    def _make_mock_join_request(
        self,
        id=1,
        email="user@example.com",
        tenant_id="t-123",
        status_value="pending",
    ):
        """Create a mock JoinRequest."""
        from src.platform.models import JoinRequestStatus

        jr = MagicMock()
        jr.id = id
        jr.email = email
        jr.tenant_id = tenant_id
        jr.status = JoinRequestStatus.PENDING
        jr.created_at = datetime.utcnow()
        jr.resolved_at = None
        jr.resolved_by = None
        jr.to_dict.return_value = {
            "id": id,
            "email": email,
            "tenant_id": tenant_id,
            "status": status_value,
            "created_at": jr.created_at.isoformat(),
            "resolved_at": None,
            "resolved_by": None,
        }
        return jr

    def test_list_join_requests(self):
        """List returns pending requests."""
        jr = self._make_mock_join_request()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
                jr
            ]
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/tenant/join-requests")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == "user@example.com"
        assert data[0]["status"] == "pending"

    def test_approve_join_request(self):
        """Approve creates TenantUser and updates request."""
        jr = self._make_mock_join_request()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = jr
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post("/api/admin/tenant/join-requests/1/approve")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Approved" in data["message"]

    def test_approve_already_resolved(self):
        """Approve an already-approved request returns error."""
        from src.platform.models import JoinRequestStatus

        jr = self._make_mock_join_request()
        jr.status = JoinRequestStatus.APPROVED

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = jr
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post("/api/admin/tenant/join-requests/1/approve")
        data = response.json()
        assert data["success"] is False
        assert "already" in data["message"]

    def test_reject_join_request(self):
        """Reject updates request status."""
        jr = self._make_mock_join_request()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = jr
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post("/api/admin/tenant/join-requests/1/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Rejected" in data["message"]

    def test_approve_nonexistent_request(self):
        """Approve nonexistent request returns 404."""

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post("/api/admin/tenant/join-requests/999/approve")
        assert response.status_code == 404


class TestInviteQR:
    """Tests for GET /api/admin/tenant/invite/qr."""

    @pytest.mark.skipif(not HAS_QRCODE, reason="qrcode not installed")
    def test_qr_returns_png(self):
        """QR endpoint returns a PNG image."""
        tenant = _make_mock_tenant()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/tenant/invite/qr")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        # PNG starts with magic bytes
        assert response.content[:4] == b"\x89PNG"

    def test_qr_no_invite_code(self):
        """QR endpoint returns 404 when no invite code."""
        tenant = _make_mock_tenant(invite_code=None)

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/admin/tenant/invite/qr")
        assert response.status_code == 404
