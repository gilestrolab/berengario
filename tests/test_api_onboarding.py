"""
Tests for onboarding API routes.

Verifies create-tenant, validate-code, join-tenant, and slug-check endpoints.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.session_manager import Session, SessionManager
from src.api.routes.onboarding import create_onboarding_router


def _make_onboarding_session(
    session_id="sess-123",
    email="newuser@example.com",
):
    """Create a session in onboarding state."""
    session = Session(session_id=session_id)
    session.authenticated = True
    session.email = email
    session.onboarding_email = email
    session.onboarding_verified = True
    return session


def _make_unauthenticated_session(session_id="sess-456"):
    """Create an unauthenticated session."""
    return Session(session_id=session_id)


def _make_mock_tenant(
    id="t-123",
    slug="acme",
    name="Acme Corp",
    status_value="active",
    invite_code="ABCD1234",
    join_approval_required=False,
):
    """Create a mock Tenant object."""
    tenant = MagicMock()
    tenant.id = id
    tenant.slug = slug
    tenant.name = name
    tenant.invite_code = invite_code
    tenant.join_approval_required = join_approval_required
    tenant.status = MagicMock()
    tenant.status.value = status_value
    return tenant


def _create_test_app(platform_db, session_manager=None, onboarding_session=None):
    """Create a test FastAPI app with onboarding router."""
    app = FastAPI()

    sm = session_manager or SessionManager()
    if onboarding_session:
        sm.sessions[onboarding_session.session_id] = onboarding_session

    settings = MagicMock()
    settings.multi_tenant = True

    def get_session_id(request):
        return request.cookies.get("session_id")

    def set_session_cookie(response, session_id):
        response.set_cookie("session_id", session_id)

    router = create_onboarding_router(
        platform_db_manager=platform_db,
        session_manager=sm,
        get_session_id=get_session_id,
        set_session_cookie=set_session_cookie,
        settings=settings,
    )
    app.include_router(router)
    return app, sm


class TestCreateTenant:
    """Tests for POST /api/onboarding/create-tenant."""

    def test_create_tenant_success(self):
        """Create tenant with onboarding session succeeds."""
        session = _make_onboarding_session()
        platform_db = MagicMock()

        mock_tenant = MagicMock()
        mock_tenant.id = "new-tenant-id"
        mock_tenant.slug = "my-team"
        mock_tenant.name = "My Team"

        with (
            patch("src.platform.storage.create_storage_backend"),
            patch("src.platform.provisioning.TenantProvisioner") as mock_prov_cls,
        ):
            mock_prov_instance = MagicMock()
            mock_prov_instance.create_tenant.return_value = mock_tenant
            mock_prov_cls.return_value = mock_prov_instance
            mock_prov_cls.validate_slug.return_value = True

            app, sm = _create_test_app(platform_db, onboarding_session=session)
            client = TestClient(app, cookies={"session_id": session.session_id})

            response = client.post(
                "/api/onboarding/create-tenant",
                json={"name": "My Team", "slug": "my-team"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tenant_slug"] == "my-team"
        assert data["tenant_name"] == "My Team"

        # Session should have tenant selected and onboarding cleared
        assert session.onboarding_verified is False
        assert session.tenant_slug == "my-team"

    def test_create_tenant_without_onboarding_session(self):
        """Create tenant without onboarding session returns 403."""
        platform_db = MagicMock()
        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/onboarding/create-tenant",
            json={"name": "My Team"},
        )
        assert response.status_code == 403

    def test_create_tenant_auto_generates_slug(self):
        """Create tenant auto-generates slug from name when not provided."""
        session = _make_onboarding_session()
        platform_db = MagicMock()

        mock_tenant = MagicMock()
        mock_tenant.id = "tid"
        mock_tenant.slug = "acme-corp"
        mock_tenant.name = "Acme Corp"

        with (
            patch("src.platform.storage.create_storage_backend"),
            patch("src.platform.provisioning.TenantProvisioner") as mock_prov_cls,
            patch("src.platform.provisioning.generate_slug", return_value="acme-corp"),
        ):
            mock_prov = MagicMock()
            mock_prov.create_tenant.return_value = mock_tenant
            mock_prov_cls.return_value = mock_prov
            mock_prov_cls.validate_slug.return_value = True

            app, _ = _create_test_app(platform_db, onboarding_session=session)
            client = TestClient(app, cookies={"session_id": session.session_id})

            response = client.post(
                "/api/onboarding/create-tenant",
                json={"name": "Acme Corp"},
            )

        data = response.json()
        assert data["success"] is True
        assert data["tenant_slug"] == "acme-corp"

    def test_create_tenant_duplicate_slug(self):
        """Create tenant with duplicate slug returns error."""
        session = _make_onboarding_session()
        platform_db = MagicMock()

        with (
            patch("src.platform.storage.create_storage_backend"),
            patch("src.platform.provisioning.TenantProvisioner") as mock_prov_cls,
        ):
            mock_prov = MagicMock()
            mock_prov.create_tenant.side_effect = ValueError(
                "Tenant with slug 'taken' already exists"
            )
            mock_prov_cls.return_value = mock_prov
            mock_prov_cls.validate_slug.return_value = True

            app, _ = _create_test_app(platform_db, onboarding_session=session)
            client = TestClient(app, cookies={"session_id": session.session_id})

            response = client.post(
                "/api/onboarding/create-tenant",
                json={"name": "Taken", "slug": "taken"},
            )

        data = response.json()
        assert data["success"] is False
        assert "already exists" in data["message"]

    def test_create_tenant_invalid_slug(self):
        """Create tenant with invalid slug returns error."""
        session = _make_onboarding_session()
        platform_db = MagicMock()

        with patch("src.platform.provisioning.TenantProvisioner") as mock_prov_cls:
            mock_prov_cls.validate_slug.return_value = False

            app, _ = _create_test_app(platform_db, onboarding_session=session)
            client = TestClient(app, cookies={"session_id": session.session_id})

            response = client.post(
                "/api/onboarding/create-tenant",
                json={"name": "Bad", "slug": "A!"},
            )

        data = response.json()
        assert data["success"] is False
        assert "Invalid slug" in data["message"]


class TestValidateCode:
    """Tests for POST /api/onboarding/validate-code."""

    def test_validate_valid_code(self):
        """Valid invite code returns tenant name."""
        tenant = _make_mock_tenant()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/onboarding/validate-code",
            json={"code": "ABCD1234"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["tenant_name"] == "Acme Corp"
        assert data["requires_approval"] is False

    def test_validate_invalid_code(self):
        """Invalid invite code returns valid=False."""

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/onboarding/validate-code",
            json={"code": "INVALID"},
        )
        data = response.json()
        assert data["valid"] is False

    def test_validate_code_approval_required(self):
        """Code for approval-required tenant shows requires_approval."""
        tenant = _make_mock_tenant(join_approval_required=True)

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = tenant
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/onboarding/validate-code",
            json={"code": "ABCD1234"},
        )
        data = response.json()
        assert data["valid"] is True
        assert data["requires_approval"] is True


class TestJoinTenant:
    """Tests for POST /api/onboarding/join-tenant."""

    def test_join_open_tenant(self):
        """Join an open tenant (no approval required) succeeds."""
        session = _make_onboarding_session()
        tenant = _make_mock_tenant(join_approval_required=False)

        @contextmanager
        def fake_session():
            s = MagicMock()
            # First query: find tenant by invite_code
            # Second query: check existing membership
            query_results = []

            def query_side_effect(model):
                result = MagicMock()
                if len(query_results) == 0:
                    # Tenant lookup
                    result.filter.return_value.first.return_value = tenant
                else:
                    # Existing user check
                    result.filter.return_value.first.return_value = None
                query_results.append(model)
                return result

            s.query.side_effect = query_side_effect
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db, onboarding_session=session)
        client = TestClient(app, cookies={"session_id": session.session_id})

        response = client.post(
            "/api/onboarding/join-tenant",
            json={"code": "ABCD1234"},
        )
        data = response.json()
        assert data["success"] is True
        assert data["joined"] is True
        assert session.onboarding_verified is False
        assert session.tenant_slug == "acme"

    def test_join_approval_required(self):
        """Join an approval-required tenant creates a pending request."""
        session = _make_onboarding_session()
        tenant = _make_mock_tenant(join_approval_required=True)

        @contextmanager
        def fake_session():
            s = MagicMock()
            query_results = []

            def query_side_effect(model):
                result = MagicMock()
                if len(query_results) == 0:
                    result.filter.return_value.first.return_value = tenant
                elif len(query_results) == 1:
                    # No existing user
                    result.filter.return_value.first.return_value = None
                else:
                    # No existing pending request
                    result.filter.return_value.first.return_value = None
                query_results.append(model)
                return result

            s.query.side_effect = query_side_effect
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db, onboarding_session=session)
        client = TestClient(app, cookies={"session_id": session.session_id})

        response = client.post(
            "/api/onboarding/join-tenant",
            json={"code": "ABCD1234"},
        )
        data = response.json()
        assert data["success"] is True
        assert data["pending_approval"] is True

    def test_join_already_member(self):
        """Join when already a member returns error."""
        session = _make_onboarding_session()
        tenant = _make_mock_tenant()
        existing_user = MagicMock()

        @contextmanager
        def fake_session():
            s = MagicMock()
            query_results = []

            def query_side_effect(model):
                result = MagicMock()
                if len(query_results) == 0:
                    result.filter.return_value.first.return_value = tenant
                else:
                    result.filter.return_value.first.return_value = existing_user
                query_results.append(model)
                return result

            s.query.side_effect = query_side_effect
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db, onboarding_session=session)
        client = TestClient(app, cookies={"session_id": session.session_id})

        response = client.post(
            "/api/onboarding/join-tenant",
            json={"code": "ABCD1234"},
        )
        data = response.json()
        assert data["success"] is False
        assert "already a member" in data["message"]

    def test_join_invalid_code(self):
        """Join with invalid code returns error."""
        session = _make_onboarding_session()

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db, onboarding_session=session)
        client = TestClient(app, cookies={"session_id": session.session_id})

        response = client.post(
            "/api/onboarding/join-tenant",
            json={"code": "INVALID"},
        )
        data = response.json()
        assert data["success"] is False
        assert "Invalid" in data["message"]

    def test_join_without_onboarding_session(self):
        """Join without onboarding session returns 403."""
        platform_db = MagicMock()
        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.post(
            "/api/onboarding/join-tenant",
            json={"code": "ABCD1234"},
        )
        assert response.status_code == 403


class TestSlugCheck:
    """Tests for GET /api/onboarding/slug-check."""

    def test_slug_available(self):
        """Available slug returns available=True."""

        @contextmanager
        def fake_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/onboarding/slug-check?slug=new-team")
        data = response.json()
        assert data["available"] is True

    def test_slug_taken_with_suggestion(self):
        """Taken slug returns available=False with suggestion."""

        @contextmanager
        def fake_session():
            s = MagicMock()
            call_count = [0]

            def first_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    return MagicMock()  # slug taken
                return None  # suggestion available

            filter_mock = MagicMock()
            filter_mock.first.side_effect = first_side_effect
            s.query.return_value.filter.return_value = filter_mock
            yield s

        platform_db = MagicMock()
        platform_db.get_platform_session = fake_session

        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/onboarding/slug-check?slug=acme")
        data = response.json()
        assert data["available"] is False
        assert data["suggestion"] == "acme-2"

    def test_slug_check_invalid(self):
        """Invalid slug returns available=False."""
        platform_db = MagicMock()
        app, _ = _create_test_app(platform_db)
        client = TestClient(app)

        response = client.get("/api/onboarding/slug-check?slug=A!")
        data = response.json()
        assert data["available"] is False
