"""
Unit tests for platform multi-tenancy database models.

Tests Tenant, TenantUser, and TenantEncryptionKey models.
"""

from datetime import datetime

from src.platform.models import (
    JoinRequest,
    JoinRequestStatus,
    Tenant,
    TenantEncryptionKey,
    TenantStatus,
    TenantUser,
    TenantUserRole,
    generate_uuid,
)


class TestTenantStatus:
    """Tests for TenantStatus enum."""

    def test_status_values(self):
        """Test all status enum values exist."""
        assert TenantStatus.PROVISIONING.value == "provisioning"
        assert TenantStatus.ACTIVE.value == "active"
        assert TenantStatus.SUSPENDED.value == "suspended"

    def test_status_count(self):
        """Test there are exactly 3 statuses."""
        assert len(TenantStatus) == 3


class TestTenantUserRole:
    """Tests for TenantUserRole enum."""

    def test_role_values(self):
        """Test all role enum values exist."""
        assert TenantUserRole.ADMIN.value == "admin"
        assert TenantUserRole.TEACHER.value == "teacher"
        assert TenantUserRole.QUERIER.value == "querier"

    def test_role_count(self):
        """Test there are exactly 3 roles."""
        assert len(TenantUserRole) == 3


class TestGenerateUUID:
    """Tests for UUID generation."""

    def test_generate_uuid_format(self):
        """Test UUID is a valid format string."""
        uid = generate_uuid()
        assert isinstance(uid, str)
        assert len(uid) == 36
        assert uid.count("-") == 4

    def test_generate_uuid_uniqueness(self):
        """Test UUIDs are unique."""
        uuids = {generate_uuid() for _ in range(100)}
        assert len(uuids) == 100


class TestTenant:
    """Tests for Tenant model."""

    def test_create_tenant(self):
        """Test creating a Tenant instance with required fields."""
        tenant = Tenant(
            slug="acme",
            name="Acme Corporation",
            email_address="acme@berengar.io",
            db_name="berengario_tenant_acme",
            storage_path="tenants/acme",
        )

        assert tenant.slug == "acme"
        assert tenant.name == "Acme Corporation"
        assert tenant.email_address == "acme@berengar.io"
        assert tenant.db_name == "berengario_tenant_acme"
        assert tenant.storage_path == "tenants/acme"

    def test_tenant_defaults(self):
        """Test default/nullable values for Tenant.

        Note: SQLAlchemy Column defaults only apply when inserting via a session.
        When constructing in-memory, defaults are None. We test nullable fields.
        """
        tenant = Tenant(
            slug="test",
            name="Test Org",
            email_address="test@berengar.io",
            db_name="berengario_tenant_test",
            storage_path="tenants/test",
        )

        # Optional fields should be None when not provided
        assert tenant.description is None
        assert tenant.organization is None
        assert tenant.custom_prompt is None
        assert tenant.email_footer is None
        assert tenant.llm_model is None

    def test_tenant_with_optional_fields(self):
        """Test Tenant with all optional fields set."""
        tenant = Tenant(
            slug="imperial",
            name="Imperial College",
            description="University KB assistant",
            organization="Imperial College London",
            email_address="imperial@berengar.io",
            email_display_name="Imperial AI",
            custom_prompt="Use British English.",
            email_footer="Powered by Berengario",
            chunk_size=512,
            chunk_overlap=100,
            top_k_retrieval=10,
            similarity_threshold=0.8,
            llm_model="anthropic/claude-3.5-sonnet",
            db_name="berengario_tenant_imperial",
            storage_path="tenants/imperial",
        )

        assert tenant.description == "University KB assistant"
        assert tenant.organization == "Imperial College London"
        assert tenant.email_display_name == "Imperial AI"
        assert tenant.custom_prompt == "Use British English."
        assert tenant.chunk_size == 512
        assert tenant.llm_model == "anthropic/claude-3.5-sonnet"

    def test_tenant_repr(self):
        """Test Tenant string representation."""
        tenant = Tenant(
            id="test-uuid",
            slug="acme",
            name="Acme Corp",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="berengario_tenant_acme",
            storage_path="tenants/acme",
        )

        repr_str = repr(tenant)
        assert "acme" in repr_str
        assert "Acme Corp" in repr_str
        assert "active" in repr_str

    def test_tenant_to_dict(self):
        """Test Tenant to_dict conversion."""
        now = datetime.utcnow()
        tenant = Tenant(
            id="test-uuid",
            slug="acme",
            name="Acme Corp",
            description="Test description",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="berengario_tenant_acme",
            storage_path="tenants/acme",
            created_at=now,
            updated_at=now,
        )

        data = tenant.to_dict()

        assert data["id"] == "test-uuid"
        assert data["slug"] == "acme"
        assert data["name"] == "Acme Corp"
        assert data["description"] == "Test description"
        assert data["status"] == "active"
        assert data["email_address"] == "acme@berengar.io"
        assert data["db_name"] == "berengario_tenant_acme"
        assert isinstance(data["created_at"], str)

    def test_tenant_to_dict_no_timestamps(self):
        """Test to_dict handles None timestamps gracefully."""
        tenant = Tenant(
            slug="test",
            name="Test",
            status=TenantStatus.PROVISIONING,
            email_address="test@berengar.io",
            db_name="db",
            storage_path="path",
            created_at=None,
            updated_at=None,
        )

        data = tenant.to_dict()
        assert data["created_at"] is None
        assert data["updated_at"] is None


class TestTenantUser:
    """Tests for TenantUser model."""

    def test_create_tenant_user(self):
        """Test creating a TenantUser instance."""
        user = TenantUser(
            email="user@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.QUERIER,
        )

        assert user.email == "user@acme.com"
        assert user.tenant_id == "test-uuid"
        assert user.role == TenantUserRole.QUERIER

    def test_tenant_user_repr(self):
        """Test TenantUser string representation."""
        user = TenantUser(
            id=1,
            email="admin@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.ADMIN,
        )

        repr_str = repr(user)
        assert "admin@acme.com" in repr_str
        assert "admin" in repr_str

    def test_tenant_user_to_dict(self):
        """Test TenantUser to_dict conversion."""
        now = datetime.utcnow()
        user = TenantUser(
            id=1,
            email="user@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.TEACHER,
            created_at=now,
        )

        data = user.to_dict()

        assert data["id"] == 1
        assert data["email"] == "user@acme.com"
        assert data["tenant_id"] == "test-uuid"
        assert data["role"] == "teacher"
        assert isinstance(data["created_at"], str)

    def test_has_permission_admin_can_do_everything(self):
        """Test admin has all permissions."""
        user = TenantUser(
            email="admin@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.ADMIN,
        )

        assert user.has_permission(TenantUserRole.QUERIER) is True
        assert user.has_permission(TenantUserRole.TEACHER) is True
        assert user.has_permission(TenantUserRole.ADMIN) is True

    def test_has_permission_teacher(self):
        """Test teacher can query and teach but not admin."""
        user = TenantUser(
            email="teacher@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.TEACHER,
        )

        assert user.has_permission(TenantUserRole.QUERIER) is True
        assert user.has_permission(TenantUserRole.TEACHER) is True
        assert user.has_permission(TenantUserRole.ADMIN) is False

    def test_has_permission_querier(self):
        """Test querier can only query."""
        user = TenantUser(
            email="user@acme.com",
            tenant_id="test-uuid",
            role=TenantUserRole.QUERIER,
        )

        assert user.has_permission(TenantUserRole.QUERIER) is True
        assert user.has_permission(TenantUserRole.TEACHER) is False
        assert user.has_permission(TenantUserRole.ADMIN) is False


class TestTenantInviteCode:
    """Tests for Tenant invite code generation."""

    def test_generate_invite_code_length(self):
        """Test invite code is 8 characters by default."""
        code = Tenant.generate_invite_code()
        assert len(code) == 8

    def test_generate_invite_code_custom_length(self):
        """Test invite code with custom length."""
        code = Tenant.generate_invite_code(length=12)
        assert len(code) == 12

    def test_generate_invite_code_characters(self):
        """Test invite code only uses unambiguous characters."""
        ambiguous = set("O0I1L")
        for _ in range(50):
            code = Tenant.generate_invite_code()
            assert not ambiguous.intersection(
                code
            ), f"Code '{code}' contains ambiguous characters"

    def test_generate_invite_code_uniqueness(self):
        """Test invite codes are unique across many generations."""
        codes = {Tenant.generate_invite_code() for _ in range(100)}
        # With 8 chars from 29-char alphabet, collision is extremely unlikely
        assert len(codes) == 100

    def test_tenant_invite_code_field(self):
        """Test invite_code can be set on Tenant."""
        tenant = Tenant(
            slug="acme",
            name="Acme",
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
            invite_code="ABCD1234",
        )
        assert tenant.invite_code == "ABCD1234"

    def test_tenant_join_approval_required_field(self):
        """Test join_approval_required field on Tenant."""
        tenant = Tenant(
            slug="acme",
            name="Acme",
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
            join_approval_required=True,
        )
        assert tenant.join_approval_required is True

    def test_tenant_to_dict_includes_invite_fields(self):
        """Test to_dict includes invite_code and join_approval_required."""
        from datetime import datetime

        now = datetime.utcnow()
        tenant = Tenant(
            id="test-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
            invite_code="ABCD1234",
            join_approval_required=True,
            created_at=now,
            updated_at=now,
        )
        data = tenant.to_dict()
        assert data["invite_code"] == "ABCD1234"
        assert data["join_approval_required"] is True


class TestJoinRequestStatus:
    """Tests for JoinRequestStatus enum."""

    def test_status_values(self):
        """Test all join request status values exist."""
        assert JoinRequestStatus.PENDING.value == "pending"
        assert JoinRequestStatus.APPROVED.value == "approved"
        assert JoinRequestStatus.REJECTED.value == "rejected"

    def test_status_count(self):
        """Test there are exactly 3 statuses."""
        assert len(JoinRequestStatus) == 3


class TestJoinRequest:
    """Tests for JoinRequest model."""

    def test_create_join_request(self):
        """Test creating a JoinRequest instance."""
        req = JoinRequest(
            email="user@example.com",
            tenant_id="test-uuid",
        )
        assert req.email == "user@example.com"
        assert req.tenant_id == "test-uuid"

    def test_join_request_defaults(self):
        """Test JoinRequest default values (in-memory)."""
        req = JoinRequest(
            email="user@example.com",
            tenant_id="test-uuid",
        )
        # resolved_at and resolved_by should be None
        assert req.resolved_at is None
        assert req.resolved_by is None

    def test_join_request_repr(self):
        """Test JoinRequest string representation."""
        req = JoinRequest(
            id=1,
            email="user@example.com",
            tenant_id="test-uuid",
            status=JoinRequestStatus.PENDING,
        )
        repr_str = repr(req)
        assert "user@example.com" in repr_str
        assert "pending" in repr_str

    def test_join_request_to_dict(self):
        """Test JoinRequest to_dict conversion."""
        from datetime import datetime

        now = datetime.utcnow()
        req = JoinRequest(
            id=1,
            email="user@example.com",
            tenant_id="test-uuid",
            status=JoinRequestStatus.APPROVED,
            created_at=now,
            resolved_at=now,
            resolved_by="admin@example.com",
        )
        data = req.to_dict()
        assert data["id"] == 1
        assert data["email"] == "user@example.com"
        assert data["status"] == "approved"
        assert data["resolved_by"] == "admin@example.com"
        assert isinstance(data["created_at"], str)
        assert isinstance(data["resolved_at"], str)

    def test_join_request_to_dict_no_resolution(self):
        """Test to_dict with unresolved request."""
        from datetime import datetime

        now = datetime.utcnow()
        req = JoinRequest(
            id=2,
            email="user@example.com",
            tenant_id="test-uuid",
            status=JoinRequestStatus.PENDING,
            created_at=now,
        )
        data = req.to_dict()
        assert data["status"] == "pending"
        assert data["resolved_at"] is None
        assert data["resolved_by"] is None


class TestTenantEncryptionKey:
    """Tests for TenantEncryptionKey model."""

    def test_create_encryption_key(self):
        """Test creating a TenantEncryptionKey instance."""
        key = TenantEncryptionKey(
            tenant_id="test-uuid",
            encrypted_key=b"encrypted-data",
            key_version=1,
        )

        assert key.tenant_id == "test-uuid"
        assert key.encrypted_key == b"encrypted-data"
        assert key.key_version == 1
        assert key.rotated_at is None

    def test_encryption_key_repr(self):
        """Test TenantEncryptionKey string representation."""
        key = TenantEncryptionKey(
            tenant_id="test-uuid",
            encrypted_key=b"data",
            key_version=3,
        )

        repr_str = repr(key)
        assert "test-uuid" in repr_str
        assert "3" in repr_str
