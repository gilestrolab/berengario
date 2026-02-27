"""
Unit tests for platform multi-tenancy database models.

Tests Tenant, TenantUser, and TenantEncryptionKey models.
"""

from datetime import datetime

from src.platform.models import (
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
