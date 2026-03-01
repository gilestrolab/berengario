"""
Unit tests for the platform admin application.

Tests auth routes, tenant CRUD, health endpoint, and auth guards
with mocked platform dependencies.
"""

import secrets
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.platform_admin.models import PlatformHealth, TenantSummary
from src.platform_admin.routes.auth import (
    AdminSessionManager,
    create_admin_auth_router,
)
from src.platform_admin.routes.health import create_health_router
from src.platform_admin.routes.tenants import create_tenants_router


class SimpleOTPManager:
    """
    Minimal OTP manager for tests.

    Avoids importing src.api.auth.otp_manager which triggers
    the settings import chain and ensure_directories().
    """

    def __init__(self):
        self._otps = {}

    def generate_otp(self, email: str) -> str:
        """Generate a 6-digit OTP."""
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        self._otps[email.lower()] = code
        return code

    def verify_otp(self, email: str, code: str) -> tuple:
        """Verify OTP code."""
        email = email.lower()
        stored = self._otps.get(email)
        if not stored:
            return False, "No OTP found"
        if stored == code:
            del self._otps[email]
            return True, "OK"
        return False, "Invalid OTP"

    def cleanup_expired(self):
        """No-op for tests."""
        pass


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def admin_emails():
    """Platform admin email list."""
    return ["admin@example.com", "ops@example.com"]


@pytest.fixture
def otp_manager():
    """Fresh OTP manager."""
    return SimpleOTPManager()


@pytest.fixture
def session_manager():
    """Fresh admin session manager."""
    return AdminSessionManager(timeout=3600)


@pytest.fixture
def mock_settings():
    """Mock settings object."""
    s = MagicMock()
    s.instance_name = "TestBerengario"
    s.organization = "TestOrg"
    s.disable_otp_for_dev = False
    s.master_encryption_key = "test-key"
    s.storage_backend = "local"
    s.web_session_timeout = 3600
    s.smtp_server = "smtp.test.com"
    s.smtp_port = 587
    s.smtp_user = "bot@test.com"
    s.smtp_password = "pass"
    s.smtp_use_tls = True
    s.email_target_address = "bot@test.com"
    return s


@pytest.fixture
def mock_email_sender():
    """Mock email sender."""
    sender = MagicMock()
    sender.send_reply = MagicMock(return_value=True)
    return sender


@pytest.fixture
def mock_db_manager():
    """Mock TenantDBManager."""
    mgr = MagicMock()
    mgr.test_platform_connection.return_value = True
    mgr.test_tenant_connection.return_value = True
    mgr.get_cache_stats.return_value = {
        "cached_tenants": 2,
        "max_cached": 50,
        "pool_size_per_tenant": 3,
        "entries": {},
    }
    return mgr


@pytest.fixture
def mock_provisioner():
    """Mock TenantProvisioner."""
    return MagicMock()


@pytest.fixture
def mock_key_manager():
    """Mock DatabaseKeyManager."""
    return MagicMock()


@pytest.fixture
def app(
    otp_manager,
    session_manager,
    admin_emails,
    mock_email_sender,
    mock_settings,
    mock_db_manager,
    mock_provisioner,
    mock_key_manager,
):
    """FastAPI test app with all admin routes."""
    app = FastAPI()

    auth_router = create_admin_auth_router(
        otp_manager=otp_manager,
        admin_session_manager=session_manager,
        admin_emails=admin_emails,
        email_sender=mock_email_sender,
        settings=mock_settings,
    )
    tenants_router = create_tenants_router(
        admin_session_manager=session_manager,
        db_manager=mock_db_manager,
        provisioner=mock_provisioner,
        key_manager=mock_key_manager,
    )
    health_router = create_health_router(
        admin_session_manager=session_manager,
        db_manager=mock_db_manager,
        settings=mock_settings,
    )

    app.include_router(auth_router)
    app.include_router(tenants_router)
    app.include_router(health_router)
    return app


@pytest.fixture
def client(app):
    """Test client."""
    return TestClient(app)


@pytest.fixture
def authed_client(client, otp_manager, session_manager):
    """Test client with authenticated admin session."""
    # Create session directly
    session_manager.create("test-session-id", "admin@example.com")
    # Set cookie
    client.cookies.set("admin_session_id", "test-session-id")
    return client


# ============================================================================
# Auth Tests
# ============================================================================


class TestAdminAuth:
    """Tests for admin auth routes."""

    def test_request_otp_denied_for_non_admin(self, client):
        """Non-admin emails should be denied."""
        resp = client.post(
            "/api/auth/request-otp",
            json={"email": "stranger@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not authorized" in data["message"].lower()

    def test_request_otp_allowed_for_admin(self, client):
        """Admin emails should receive OTP."""
        resp = client.post(
            "/api/auth/request-otp",
            json={"email": "admin@example.com"},
        )
        data = resp.json()
        assert data["success"] is True
        assert data["email"] == "admin@example.com"

    def test_request_otp_case_insensitive(self, client):
        """Email check should be case-insensitive."""
        resp = client.post(
            "/api/auth/request-otp",
            json={"email": "ADMIN@example.com"},
        )
        data = resp.json()
        assert data["success"] is True

    def test_verify_otp_success(self, client, otp_manager):
        """Successful OTP verification creates session."""
        otp_code = otp_manager.generate_otp("admin@example.com")
        resp = client.post(
            "/api/auth/verify-otp",
            json={"email": "admin@example.com", "otp_code": otp_code},
        )
        data = resp.json()
        assert data["success"] is True
        assert "admin_session_id" in resp.cookies

    def test_verify_otp_wrong_code(self, client, otp_manager):
        """Wrong OTP should fail."""
        otp_manager.generate_otp("admin@example.com")
        resp = client.post(
            "/api/auth/verify-otp",
            json={"email": "admin@example.com", "otp_code": "000000"},
        )
        data = resp.json()
        assert data["success"] is False

    def test_verify_otp_denied_for_non_admin(self, client):
        """Non-admin email should be denied even with valid OTP."""
        resp = client.post(
            "/api/auth/verify-otp",
            json={"email": "stranger@example.com", "otp_code": "123456"},
        )
        data = resp.json()
        assert data["success"] is False

    def test_dev_mode_bypasses_otp(self, mock_settings, client):
        """Dev mode should bypass OTP verification."""
        mock_settings.disable_otp_for_dev = True
        resp = client.post(
            "/api/auth/request-otp",
            json={"email": "admin@example.com"},
        )
        data = resp.json()
        assert data["success"] is True
        assert "dev mode" in data["message"].lower()

    def test_auth_status_unauthenticated(self, client):
        """Status should show unauthenticated without session."""
        resp = client.get("/api/auth/status")
        data = resp.json()
        assert data["authenticated"] is False

    def test_auth_status_authenticated(self, authed_client):
        """Status should show authenticated with valid session."""
        resp = authed_client.get("/api/auth/status")
        data = resp.json()
        assert data["authenticated"] is True
        assert data["email"] == "admin@example.com"

    def test_logout_clears_session(self, authed_client, session_manager):
        """Logout should delete session and clear cookie."""
        resp = authed_client.post("/api/auth/logout")
        data = resp.json()
        assert data["success"] is True
        assert session_manager.get("test-session-id") is None


class TestAdminSessionManager:
    """Tests for AdminSessionManager."""

    def test_create_and_get(self):
        """Should create and retrieve sessions."""
        mgr = AdminSessionManager(timeout=3600)
        session = mgr.create("s1", "test@example.com")
        assert session.authenticated is True
        assert session.email == "test@example.com"

        retrieved = mgr.get("s1")
        assert retrieved is not None
        assert retrieved.email == "test@example.com"

    def test_get_nonexistent_returns_none(self):
        """Should return None for unknown session IDs."""
        mgr = AdminSessionManager()
        assert mgr.get("unknown") is None

    def test_delete_session(self):
        """Should delete session."""
        mgr = AdminSessionManager()
        mgr.create("s1", "test@example.com")
        mgr.delete("s1")
        assert mgr.get("s1") is None

    def test_expired_session_returns_none(self):
        """Expired sessions should be evicted on access."""
        mgr = AdminSessionManager(timeout=0)  # Instant expiry
        mgr.create("s1", "test@example.com")
        # Force expiry by backdating
        import time

        time.sleep(0.01)
        assert mgr.get("s1") is None


# ============================================================================
# Auth Guard Tests
# ============================================================================


class TestAuthGuard:
    """Tests for auth guard on protected endpoints."""

    def test_list_tenants_requires_auth(self, client):
        """Tenant list should return 401 without auth."""
        resp = client.get("/api/tenants/")
        assert resp.status_code == 401

    def test_get_tenant_requires_auth(self, client):
        """Tenant detail should return 401 without auth."""
        resp = client.get("/api/tenants/test-slug")
        assert resp.status_code == 401

    def test_create_tenant_requires_auth(self, client):
        """Tenant creation should return 401 without auth."""
        resp = client.post(
            "/api/tenants/",
            json={
                "slug": "test",
                "name": "Test",
                "admin_email": "a@b.com",
            },
        )
        assert resp.status_code == 401

    def test_suspend_requires_auth(self, client):
        """Suspend should return 401 without auth."""
        resp = client.post("/api/tenants/test/suspend")
        assert resp.status_code == 401

    def test_resume_requires_auth(self, client):
        """Resume should return 401 without auth."""
        resp = client.post("/api/tenants/test/resume")
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        """Delete should return 401 without auth."""
        resp = client.delete("/api/tenants/test?confirm=test")
        assert resp.status_code == 401

    def test_rotate_key_requires_auth(self, client):
        """Key rotation should return 401 without auth."""
        resp = client.post("/api/tenants/test/rotate-key")
        assert resp.status_code == 401

    def test_list_users_requires_auth(self, client):
        """User listing should return 401 without auth."""
        resp = client.get("/api/tenants/test/users")
        assert resp.status_code == 401

    def test_add_user_requires_auth(self, client):
        """Add user should return 401 without auth."""
        resp = client.post(
            "/api/tenants/test/users",
            json={"email": "u@b.com", "role": "querier"},
        )
        assert resp.status_code == 401

    def test_remove_user_requires_auth(self, client):
        """Remove user should return 401 without auth."""
        resp = client.delete("/api/tenants/test/users/u@b.com")
        assert resp.status_code == 401


# ============================================================================
# Tenant CRUD Tests
# ============================================================================


class TestTenantCRUD:
    """Tests for tenant management routes."""

    def test_list_tenants(self, authed_client, mock_db_manager):
        """Should list tenants with user counts."""
        # Mock the platform session query
        from src.platform.models import Tenant, TenantStatus

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_tenant.slug = "acme"
        mock_tenant.name = "Acme Corp"
        mock_tenant.status = TenantStatus.ACTIVE
        mock_tenant.organization = "Acme Inc"
        mock_tenant.email_address = "acme@berengar.io"
        mock_tenant.created_at = datetime(2024, 1, 1)

        mock_session = MagicMock()
        mock_session.query.return_value.outerjoin.return_value.group_by.return_value.order_by.return_value.all.return_value = [
            (mock_tenant, 3)
        ]
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        resp = authed_client.get("/api/tenants/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "acme"
        assert data[0]["user_count"] == 3

    def test_create_tenant(self, authed_client, mock_provisioner):
        """Should create a tenant via provisioner."""
        from src.platform.models import Tenant, TenantStatus

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-new"
        mock_tenant.slug = "newco"
        mock_tenant.name = "New Company"
        mock_tenant.status = TenantStatus.ACTIVE
        mock_tenant.organization = None
        mock_tenant.email_address = "newco@berengar.io"
        mock_tenant.created_at = datetime(2024, 6, 1)
        mock_provisioner.create_tenant.return_value = mock_tenant

        resp = authed_client.post(
            "/api/tenants/",
            json={
                "slug": "newco",
                "name": "New Company",
                "admin_email": "admin@newco.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "newco"
        mock_provisioner.create_tenant.assert_called_once()

    def test_create_tenant_invalid_slug(self, authed_client, mock_provisioner):
        """Should return 400 for invalid slug."""
        mock_provisioner.create_tenant.side_effect = ValueError("Invalid slug")

        resp = authed_client.post(
            "/api/tenants/",
            json={
                "slug": "bad",
                "name": "Bad",
                "admin_email": "a@b.com",
            },
        )
        assert resp.status_code == 400

    def test_suspend_tenant(self, authed_client, mock_provisioner):
        """Should suspend a tenant."""
        mock_provisioner.suspend_tenant.return_value = True

        resp = authed_client.post("/api/tenants/acme/suspend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_provisioner.suspend_tenant.assert_called_with("acme")

    def test_suspend_nonexistent_tenant(self, authed_client, mock_provisioner):
        """Should return 404 for missing tenant."""
        mock_provisioner.suspend_tenant.side_effect = ValueError("Not found")

        resp = authed_client.post("/api/tenants/ghost/suspend")
        assert resp.status_code == 404

    def test_resume_tenant(self, authed_client, mock_provisioner):
        """Should resume a suspended tenant."""
        mock_provisioner.resume_tenant.return_value = True

        resp = authed_client.post("/api/tenants/acme/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_provisioner.resume_tenant.assert_called_with("acme")

    def test_delete_tenant_with_confirmation(self, authed_client, mock_provisioner):
        """Should delete tenant when confirm matches slug."""
        mock_provisioner.delete_tenant.return_value = True

        resp = authed_client.delete("/api/tenants/acme?confirm=acme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_provisioner.delete_tenant.assert_called_with("acme")

    def test_delete_tenant_without_confirmation(self, authed_client):
        """Should return 400 without confirm parameter."""
        resp = authed_client.delete("/api/tenants/acme")
        assert resp.status_code == 400

    def test_delete_tenant_wrong_confirmation(self, authed_client):
        """Should return 400 with wrong confirm value."""
        resp = authed_client.delete("/api/tenants/acme?confirm=wrong")
        assert resp.status_code == 400

    def test_rotate_key(self, authed_client, mock_db_manager, mock_key_manager):
        """Should rotate encryption key for a tenant."""
        from src.platform.models import Tenant

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_tenant.slug = "acme"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_tenant
        )
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        resp = authed_client.post("/api/tenants/acme/rotate-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_key_manager.rotate_tenant_key_with_session.assert_called_once()


# ============================================================================
# User Management Tests
# ============================================================================


class TestUserManagement:
    """Tests for tenant user management routes."""

    def test_list_users(self, authed_client, mock_provisioner):
        """Should list users in a tenant."""
        mock_provisioner.get_tenant_users.return_value = [
            {
                "id": 1,
                "email": "user1@acme.com",
                "role": "admin",
                "tenant_id": "uuid-1",
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "id": 2,
                "email": "user2@acme.com",
                "role": "querier",
                "tenant_id": "uuid-1",
                "created_at": "2024-01-02T00:00:00",
            },
        ]

        resp = authed_client.get("/api/tenants/acme/users")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["email"] == "user1@acme.com"

    def test_list_users_not_found(self, authed_client, mock_provisioner):
        """Should return 404 for nonexistent tenant."""
        mock_provisioner.get_tenant_users.side_effect = ValueError("Not found")

        resp = authed_client.get("/api/tenants/ghost/users")
        assert resp.status_code == 404

    def test_add_user(self, authed_client, mock_provisioner):
        """Should add a user to a tenant."""
        from src.platform.models import TenantUserRole

        mock_user = MagicMock()
        mock_user.id = 3
        mock_user.email = "new@acme.com"
        mock_user.role = TenantUserRole.QUERIER
        mock_user.tenant_id = "uuid-1"
        mock_user.created_at = datetime(2024, 6, 1)
        mock_provisioner.add_user.return_value = mock_user

        resp = authed_client.post(
            "/api/tenants/acme/users",
            json={"email": "new@acme.com", "role": "querier"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "new@acme.com"

    def test_add_duplicate_user(self, authed_client, mock_provisioner):
        """Should return 400 for duplicate user."""
        mock_provisioner.add_user.side_effect = ValueError("already exists")

        resp = authed_client.post(
            "/api/tenants/acme/users",
            json={"email": "dup@acme.com", "role": "querier"},
        )
        assert resp.status_code == 400

    def test_remove_user(self, authed_client, mock_provisioner):
        """Should remove a user from a tenant."""
        mock_provisioner.remove_user.return_value = True

        resp = authed_client.delete("/api/tenants/acme/users/user@acme.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_remove_nonexistent_user(self, authed_client, mock_provisioner):
        """Should return 404 for nonexistent user."""
        mock_provisioner.remove_user.return_value = False

        resp = authed_client.delete("/api/tenants/acme/users/ghost@acme.com")
        assert resp.status_code == 404


# ============================================================================
# Health Tests
# ============================================================================


class TestHealth:
    """Tests for platform health endpoint."""

    def test_health_endpoint(self, client, mock_db_manager):
        """Health endpoint should be accessible without auth (for Docker healthcheck)."""
        # Mock the platform session for tenant counts
        mock_session = MagicMock()
        mock_session.query.return_value.group_by.return_value.all.return_value = []
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        resp = client.get("/api/platform/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["platform_db"] is True
        assert "cache_stats" in data
        assert "tenant_counts" in data
        assert "encryption_enabled" in data
        assert "storage_backend" in data

    def test_health_unhealthy_db(self, client, mock_db_manager):
        """Health should report unhealthy when DB is down."""
        mock_db_manager.test_platform_connection.return_value = False
        # Mock the platform session to handle the tenant counts query
        mock_session = MagicMock()
        mock_session.query.return_value.group_by.return_value.all.return_value = []
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        resp = client.get("/api/platform/health")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["platform_db"] is False


# ============================================================================
# Pydantic Model Tests
# ============================================================================


class TestPydanticModels:
    """Tests for platform admin Pydantic models."""

    def test_tenant_summary_model(self):
        """TenantSummary should serialize correctly."""
        summary = TenantSummary(
            id="uuid-1",
            slug="acme",
            name="Acme Corp",
            status="active",
            organization="Acme Inc",
            email_address="acme@berengar.io",
            user_count=5,
            created_at="2024-01-01T00:00:00",
        )
        data = summary.model_dump()
        assert data["slug"] == "acme"
        assert data["user_count"] == 5

    def test_platform_health_model(self):
        """PlatformHealth should include timestamp."""
        health = PlatformHealth(
            status="healthy",
            platform_db=True,
            cache_stats={"cached_tenants": 0},
            tenant_counts={"active": 1},
            encryption_enabled=True,
            storage_backend="local",
        )
        data = health.model_dump()
        assert "timestamp" in data
        assert data["status"] == "healthy"
