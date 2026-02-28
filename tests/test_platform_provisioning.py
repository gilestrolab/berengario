"""
Unit tests for tenant provisioning service.

Tests TenantProvisioner with mocked dependencies.
"""

from unittest.mock import MagicMock

import pytest

from src.platform.models import Tenant, TenantStatus, TenantUser, TenantUserRole
from src.platform.provisioning import (
    SLUG_PATTERN,
    TenantProvisioner,
    generate_slug,
)


class TestSlugValidation:
    """Tests for tenant slug validation."""

    def test_valid_slugs(self):
        """Test valid slug patterns."""
        valid = ["ab", "acme", "imperial-dols", "my-org-123", "a1", "test-org"]
        for slug in valid:
            assert TenantProvisioner.validate_slug(slug), f"'{slug}' should be valid"

    def test_invalid_slugs_too_short(self):
        """Test that single-character slugs are invalid."""
        assert not TenantProvisioner.validate_slug("a")
        assert not TenantProvisioner.validate_slug("")

    def test_invalid_slugs_too_long(self):
        """Test that slugs over 63 characters are invalid."""
        assert not TenantProvisioner.validate_slug("a" * 64)

    def test_invalid_slugs_uppercase(self):
        """Test that uppercase slugs are invalid."""
        assert not TenantProvisioner.validate_slug("Acme")
        assert not TenantProvisioner.validate_slug("ACME")

    def test_invalid_slugs_special_chars(self):
        """Test that special characters are invalid."""
        assert not TenantProvisioner.validate_slug("acme_corp")
        assert not TenantProvisioner.validate_slug("acme.corp")
        assert not TenantProvisioner.validate_slug("acme corp")
        assert not TenantProvisioner.validate_slug("acme@corp")

    def test_invalid_slugs_starting_with_hyphen(self):
        """Test that slugs starting with hyphen are invalid."""
        assert not TenantProvisioner.validate_slug("-acme")

    def test_invalid_slugs_ending_with_hyphen(self):
        """Test that slugs ending with hyphen are invalid."""
        assert not TenantProvisioner.validate_slug("acme-")

    def test_max_length_slug(self):
        """Test that 63-character slug is valid."""
        slug = "a" * 63
        assert TenantProvisioner.validate_slug(slug)

    def test_min_length_slug(self):
        """Test that 2-character slug is valid."""
        assert TenantProvisioner.validate_slug("ab")


class TestTenantProvisioner:
    """Tests for TenantProvisioner operations."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock TenantDBManager."""
        db_manager = MagicMock()
        db_manager.create_tenant_database.return_value = True
        db_manager.drop_tenant_database.return_value = True
        return db_manager

    @pytest.fixture
    def mock_storage(self):
        """Create a mock StorageBackend."""
        return MagicMock()

    @pytest.fixture
    def mock_key_manager(self):
        """Create a mock DatabaseKeyManager."""
        return MagicMock()

    @pytest.fixture
    def provisioner(self, mock_db_manager, mock_storage, mock_key_manager):
        """Create a TenantProvisioner with mocked dependencies."""
        return TenantProvisioner(
            db_manager=mock_db_manager,
            storage=mock_storage,
            key_manager=mock_key_manager,
        )

    @pytest.fixture
    def provisioner_no_encryption(self, mock_db_manager, mock_storage):
        """Create a TenantProvisioner without encryption."""
        return TenantProvisioner(
            db_manager=mock_db_manager,
            storage=mock_storage,
        )

    def _mock_platform_session(
        self, mock_db_manager, existing_tenant=None, existing_email=None
    ):
        """Helper to set up mock platform session context."""
        session = MagicMock()

        # Make query().filter().first() return None (no existing tenants) by default
        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            # Default: no existing records
            result.first.return_value = None
            return result

        query_result = MagicMock()
        query_result.filter = MagicMock(side_effect=filter_side_effect)
        session.query.return_value = query_result

        # Set up the context manager
        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        return session

    def test_create_tenant_invalid_slug(self, provisioner):
        """Test creating a tenant with invalid slug raises ValueError."""
        with pytest.raises(ValueError, match="Invalid slug"):
            provisioner.create_tenant(
                slug="INVALID",
                name="Test",
                admin_email="admin@test.com",
            )

    def test_create_tenant_empty_slug(self, provisioner):
        """Test creating a tenant with empty slug raises ValueError."""
        with pytest.raises(ValueError, match="Invalid slug"):
            provisioner.create_tenant(
                slug="",
                name="Test",
                admin_email="admin@test.com",
            )

    def test_suspend_tenant(self, provisioner, mock_db_manager):
        """Test suspending an active tenant."""
        session = MagicMock()
        tenant = Tenant(
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.suspend_tenant("acme")
        assert result is True
        assert tenant.status == TenantStatus.SUSPENDED

    def test_suspend_already_suspended(self, provisioner, mock_db_manager):
        """Test suspending an already-suspended tenant returns True."""
        session = MagicMock()
        tenant = Tenant(
            slug="acme",
            name="Acme",
            status=TenantStatus.SUSPENDED,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.suspend_tenant("acme")
        assert result is True

    def test_suspend_nonexistent_tenant(self, provisioner, mock_db_manager):
        """Test suspending a nonexistent tenant raises ValueError."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with pytest.raises(ValueError, match="Tenant not found"):
            provisioner.suspend_tenant("nonexistent")

    def test_resume_tenant(self, provisioner, mock_db_manager):
        """Test resuming a suspended tenant."""
        session = MagicMock()
        tenant = Tenant(
            slug="acme",
            name="Acme",
            status=TenantStatus.SUSPENDED,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.resume_tenant("acme")
        assert result is True
        assert tenant.status == TenantStatus.ACTIVE

    def test_resume_non_suspended_tenant(self, provisioner, mock_db_manager):
        """Test resuming an active tenant returns True (no-op)."""
        session = MagicMock()
        tenant = Tenant(
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.resume_tenant("acme")
        assert result is True
        assert tenant.status == TenantStatus.ACTIVE

    def test_add_user(self, provisioner, mock_db_manager):
        """Test adding a user to a tenant."""
        session = MagicMock()
        tenant = Tenant(
            id="tenant-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )

        # First call finds tenant, second finds no existing user
        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            result.first.return_value = None
            return result

        query_results = [
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=tenant))
                )
            ),
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        ]
        session.query.side_effect = query_results

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        user = provisioner.add_user("acme", "user@acme.com", TenantUserRole.TEACHER)

        assert isinstance(user, TenantUser)
        assert user.email == "user@acme.com"
        assert user.role == TenantUserRole.TEACHER

    def test_add_user_nonexistent_tenant(self, provisioner, mock_db_manager):
        """Test adding a user to a nonexistent tenant raises ValueError."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with pytest.raises(ValueError, match="Tenant not found"):
            provisioner.add_user("nonexistent", "user@test.com")

    def test_remove_user(self, provisioner, mock_db_manager):
        """Test removing a user from a tenant."""
        session = MagicMock()
        tenant = Tenant(
            id="tenant-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )
        user = TenantUser(
            email="user@acme.com",
            tenant_id="tenant-uuid",
            role=TenantUserRole.QUERIER,
        )

        # First call returns tenant, second returns user
        query_results = [
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=tenant))
                )
            ),
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=user))
                )
            ),
        ]
        session.query.side_effect = query_results

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.remove_user("acme", "user@acme.com")
        assert result is True
        session.delete.assert_called_once_with(user)

    def test_remove_nonexistent_user(self, provisioner, mock_db_manager):
        """Test removing a user that doesn't exist returns False."""
        session = MagicMock()
        tenant = Tenant(
            id="tenant-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="db",
            storage_path="path",
        )

        query_results = [
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=tenant))
                )
            ),
            MagicMock(
                filter=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        ]
        session.query.side_effect = query_results

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.remove_user("acme", "nonexistent@acme.com")
        assert result is False

    def test_delete_tenant(
        self, provisioner, mock_db_manager, mock_storage, mock_key_manager
    ):
        """Test deleting a tenant with crypto-shredding."""
        session = MagicMock()
        tenant = Tenant(
            id="tenant-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="berengario_tenant_acme",
            storage_path="tenants/acme",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner.delete_tenant("acme")

        assert result is True
        # Should have suspended first
        assert tenant.status == TenantStatus.SUSPENDED
        # Should have destroyed encryption key
        mock_key_manager.destroy_tenant_key_with_session.assert_called_once_with(
            session, "tenant-uuid"
        )
        # Should have deleted storage
        mock_storage.delete_tenant_data.assert_called_once_with("acme")
        # Should have dropped database
        mock_db_manager.drop_tenant_database.assert_called_once_with(
            "berengario_tenant_acme"
        )
        # Should have deleted tenant record
        session.delete.assert_called_once_with(tenant)

    def test_delete_tenant_nonexistent(self, provisioner, mock_db_manager):
        """Test deleting a nonexistent tenant raises ValueError."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with pytest.raises(ValueError, match="Tenant not found"):
            provisioner.delete_tenant("nonexistent")

    def test_delete_tenant_no_crypto_shred(
        self, provisioner_no_encryption, mock_db_manager, mock_storage
    ):
        """Test deleting a tenant without crypto-shredding."""
        session = MagicMock()
        tenant = Tenant(
            id="tenant-uuid",
            slug="acme",
            name="Acme",
            status=TenantStatus.ACTIVE,
            email_address="acme@berengar.io",
            db_name="berengario_tenant_acme",
            storage_path="tenants/acme",
        )
        session.query.return_value.filter.return_value.first.return_value = tenant

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = provisioner_no_encryption.delete_tenant("acme")

        assert result is True
        # Should still delete storage and drop database
        mock_storage.delete_tenant_data.assert_called_once()
        mock_db_manager.drop_tenant_database.assert_called_once()


class TestGenerateSlug:
    """Tests for generate_slug utility."""

    def test_simple_name(self):
        """Test slug from simple ASCII name."""
        assert generate_slug("Acme Corp") == "acme-corp"

    def test_unicode_name(self):
        """Test slug from unicode name (transliteration)."""
        assert generate_slug("Üniversität München") == "universitat-munchen"

    def test_special_characters(self):
        """Test slug strips special characters."""
        assert generate_slug("Hello, World! #2024") == "hello-world-2024"

    def test_multiple_spaces(self):
        """Test slug collapses whitespace to single hyphens."""
        assert generate_slug("Acme   Corp   Inc") == "acme-corp-inc"

    def test_leading_trailing_special(self):
        """Test slug strips leading/trailing non-alphanumeric."""
        assert generate_slug("---Acme---") == "acme"

    def test_too_short_raises(self):
        """Test slug too short raises ValueError."""
        with pytest.raises(ValueError, match="too short"):
            generate_slug("!")

    def test_max_length_truncation(self):
        """Test slug is truncated to 63 characters."""
        long_name = "A" * 100
        slug = generate_slug(long_name)
        assert len(slug) <= 63

    def test_accented_characters(self):
        """Test slug handles accented characters."""
        assert generate_slug("café résumé") == "cafe-resume"

    def test_numbers(self):
        """Test slug preserves numbers."""
        assert generate_slug("Team 42") == "team-42"

    def test_empty_string_raises(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="too short"):
            generate_slug("")


class TestSlugPattern:
    """Tests for the slug regex pattern directly."""

    def test_pattern_matches_valid(self):
        """Test slug pattern matches valid slugs."""
        assert SLUG_PATTERN.match("ab")
        assert SLUG_PATTERN.match("acme")
        assert SLUG_PATTERN.match("my-org")
        assert SLUG_PATTERN.match("test123")
        assert SLUG_PATTERN.match("a" * 63)

    def test_pattern_rejects_invalid(self):
        """Test slug pattern rejects invalid slugs."""
        assert not SLUG_PATTERN.match("")
        assert not SLUG_PATTERN.match("a")
        assert not SLUG_PATTERN.match("-acme")
        assert not SLUG_PATTERN.match("acme-")
        assert not SLUG_PATTERN.match("Acme")
        assert not SLUG_PATTERN.match("a" * 64)
        assert not SLUG_PATTERN.match("acme_corp")
