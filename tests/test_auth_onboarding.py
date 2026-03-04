"""
Tests for auth flow changes in multi-tenant onboarding.

Verifies that unknown emails in MT mode get onboarding state
instead of rejection, and known emails follow the normal flow.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.session_manager import Session, SessionManager
from src.api.routes.auth import create_auth_router


def _make_settings(multi_tenant=True, disable_otp=True):
    """Create mock settings."""
    s = MagicMock()
    s.multi_tenant = multi_tenant
    s.disable_otp_for_dev = disable_otp
    s.instance_name = "TestBot"
    s.organization = "TestOrg"
    return s


def _make_platform_db(tenant_users=None):
    """Create mock platform DB manager with configurable TenantUser lookup."""
    platform_db = MagicMock()

    # Mock get_platform_session for _lookup_tenant_users
    @contextmanager
    def fake_session():
        session = MagicMock()
        # Return the provided records (or empty)
        records = []
        if tenant_users:
            for tu in tenant_users:
                r = MagicMock()
                r.tenant_id = tu["tenant_id"]
                r.tenant.slug = tu["tenant_slug"]
                r.tenant.name = tu["tenant_name"]
                r.role = MagicMock()
                r.role.value = tu["role"]
                r.role.__str__ = lambda s: s.value
                records.append(r)
        session.query.return_value.join.return_value.filter.return_value.all.return_value = (
            records
        )
        yield session

    platform_db.get_platform_session = fake_session
    return platform_db


def _create_test_app(settings_override=None, platform_db=None):
    """Create a test FastAPI app with auth router configured for MT testing."""
    app = FastAPI()

    settings = settings_override or _make_settings()
    session_manager = SessionManager()
    otp_manager = MagicMock()
    otp_manager.generate_otp.return_value = "123456"
    otp_manager.verify_otp.return_value = (True, "OK")
    email_sender = MagicMock()

    def get_session_id(request):
        return request.cookies.get("session_id")

    def set_session_cookie(response, session_id):
        response.set_cookie("session_id", session_id)

    router = create_auth_router(
        session_manager=session_manager,
        otp_manager=otp_manager,
        email_sender=email_sender,
        get_session_id=get_session_id,
        set_session_cookie=set_session_cookie,
        settings=settings,
        platform_db_manager=platform_db,
    )
    app.include_router(router)
    return app, session_manager


class TestMTRequestOTP:
    """Tests for OTP request in MT mode."""

    def test_request_otp_allows_any_email_in_mt_mode(self):
        """In MT mode, any email can request OTP (no rejection)."""
        platform_db = _make_platform_db(tenant_users=[])
        app, _ = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/auth/request-otp",
            json={"email": "unknown@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_request_otp_rejects_in_st_mode(self):
        """In ST mode, non-whitelisted emails are rejected."""
        settings = _make_settings(multi_tenant=False)
        app, _ = _create_test_app(settings_override=settings)
        client = TestClient(app)

        response = client.post(
            "/api/auth/request-otp",
            json={"email": "unknown@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Access denied" in data["message"]


class TestMTVerifyOTP:
    """Tests for OTP verification in MT mode."""

    def test_verify_unknown_email_gets_onboarding_state(self):
        """Unknown email in MT mode gets onboarding_verified=True."""
        platform_db = _make_platform_db(tenant_users=[])
        app, session_mgr = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/auth/verify-otp",
            json={"email": "newuser@example.com", "otp_code": "123456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["requires_onboarding"] is True
        assert data["email"] == "newuser@example.com"

        # Verify session state
        session_id = response.cookies.get("session_id")
        assert session_id is not None
        session = session_mgr.get_session(session_id)
        assert session is not None
        assert session.onboarding_verified is True
        assert session.onboarding_email == "newuser@example.com"

    def test_verify_known_email_normal_flow(self):
        """Known email in MT mode follows normal tenant flow."""
        tenant_users = [
            {
                "tenant_id": "t-123",
                "tenant_slug": "acme",
                "tenant_name": "Acme Corp",
                "role": "admin",
            }
        ]
        platform_db = _make_platform_db(tenant_users=tenant_users)
        app, session_mgr = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/auth/verify-otp",
            json={"email": "admin@acme.com", "otp_code": "123456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data.get("requires_onboarding", False) is False

        # Should have auto-selected the single tenant
        session_id = response.cookies.get("session_id")
        session = session_mgr.get_session(session_id)
        assert session.tenant_slug == "acme"
        assert session.onboarding_verified is False

    def test_verify_multi_tenant_user(self):
        """User with multiple tenants gets requires_tenant_selection."""
        tenant_users = [
            {
                "tenant_id": "t-123",
                "tenant_slug": "acme",
                "tenant_name": "Acme Corp",
                "role": "admin",
            },
            {
                "tenant_id": "t-456",
                "tenant_slug": "widgets",
                "tenant_name": "Widgets Inc",
                "role": "querier",
            },
        ]
        platform_db = _make_platform_db(tenant_users=tenant_users)
        app, session_mgr = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/auth/verify-otp",
            json={"email": "user@multi.com", "otp_code": "123456"},
        )
        data = response.json()
        assert data["success"] is True
        assert data.get("requires_onboarding", False) is False

        # Session should have available_tenants
        session_id = response.cookies.get("session_id")
        session = session_mgr.get_session(session_id)
        assert len(session.available_tenants) == 2


class TestMTAuthStatus:
    """Tests for auth status endpoint with onboarding state."""

    def test_status_reflects_onboarding(self):
        """Auth status returns onboarding_verified when in onboarding state."""
        platform_db = _make_platform_db(tenant_users=[])
        app, _ = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        # First verify OTP to get onboarding session
        verify_resp = client.post(
            "/api/auth/verify-otp",
            json={"email": "new@example.com", "otp_code": "123456"},
        )
        assert verify_resp.json()["requires_onboarding"] is True

        # Now check status
        status_resp = client.get("/api/auth/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["authenticated"] is True
        assert data["onboarding_verified"] is True
        assert data["email"] == "new@example.com"

    def test_status_not_onboarding_for_known_user(self):
        """Auth status shows onboarding_verified=False for known users."""
        tenant_users = [
            {
                "tenant_id": "t-1",
                "tenant_slug": "test",
                "tenant_name": "Test",
                "role": "querier",
            }
        ]
        platform_db = _make_platform_db(tenant_users=tenant_users)
        app, _ = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        client.post(
            "/api/auth/verify-otp",
            json={"email": "known@test.com", "otp_code": "123456"},
        )

        status_resp = client.get("/api/auth/status")
        data = status_resp.json()
        assert data["authenticated"] is True
        assert data["onboarding_verified"] is False

    def test_status_unauthenticated(self):
        """Auth status returns unauthenticated for no session."""
        platform_db = _make_platform_db()
        app, _ = _create_test_app(platform_db=platform_db)
        client = TestClient(app)

        status_resp = client.get("/api/auth/status")
        data = status_resp.json()
        assert data["authenticated"] is False
        assert data["onboarding_verified"] is False


class TestSessionOnboardingFields:
    """Tests for Session dataclass onboarding fields."""

    def test_session_default_onboarding_fields(self):
        """New session has onboarding fields set to defaults."""
        session = Session(session_id="test-123")
        assert session.onboarding_email is None
        assert session.onboarding_verified is False

    def test_session_onboarding_fields_settable(self):
        """Onboarding fields can be set on session."""
        session = Session(session_id="test-123")
        session.onboarding_email = "user@example.com"
        session.onboarding_verified = True
        assert session.onboarding_email == "user@example.com"
        assert session.onboarding_verified is True
