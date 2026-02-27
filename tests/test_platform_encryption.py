"""
Unit tests for platform encryption module.

Tests DatabaseKeyManager and TenantEncryptor using in-memory SQLite.
"""

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.platform.encryption import DatabaseKeyManager, TenantEncryptor
from src.platform.models import TenantEncryptionKey


class TestDatabaseKeyManager:
    """Tests for DatabaseKeyManager."""

    @pytest.fixture
    def master_key(self):
        """Generate a test master key."""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def key_manager(self, master_key):
        """Create a DatabaseKeyManager with a test master key."""
        return DatabaseKeyManager(master_key=master_key)

    @pytest.fixture
    def mock_session(self):
        """Create a mock SQLAlchemy session."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        return session

    def test_init_with_valid_key(self, master_key):
        """Test initialization with a valid Fernet key."""
        km = DatabaseKeyManager(master_key=master_key)
        assert km._master_fernet is not None

    def test_init_without_key_raises(self):
        """Test initialization without a key raises ValueError."""
        with patch("src.platform.encryption.settings") as mock_settings:
            mock_settings.master_encryption_key = ""
            with pytest.raises(
                ValueError, match="Master encryption key not configured"
            ):
                DatabaseKeyManager()

    def test_init_with_invalid_key_raises(self):
        """Test initialization with an invalid key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid master encryption key"):
            DatabaseKeyManager(master_key="not-a-valid-fernet-key")

    def test_create_tenant_key(self, key_manager, mock_session):
        """Test creating a new tenant encryption key."""
        raw_key = key_manager.create_tenant_key_with_session(mock_session, "tenant-1")

        # Should return valid Fernet key bytes
        assert isinstance(raw_key, bytes)
        # Verify it's a valid Fernet key
        Fernet(raw_key)

        # Should have added a key record to session
        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, TenantEncryptionKey)
        assert added.tenant_id == "tenant-1"
        assert added.key_version == 1

    def test_create_duplicate_key_raises(self, key_manager, mock_session):
        """Test creating a key for a tenant that already has one raises."""
        existing_key = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=b"existing",
            key_version=1,
        )
        mock_session.query.return_value.filter.return_value.first.return_value = (
            existing_key
        )

        with pytest.raises(ValueError, match="already exists"):
            key_manager.create_tenant_key_with_session(mock_session, "tenant-1")

    def test_get_tenant_key(self, key_manager, mock_session):
        """Test retrieving and decrypting a tenant key."""
        # First create a key
        raw_key = Fernet.generate_key()
        encrypted_key = key_manager._master_fernet.encrypt(raw_key)

        key_record = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=encrypted_key,
            key_version=1,
        )
        mock_session.query.return_value.filter.return_value.first.return_value = (
            key_record
        )

        result = key_manager.get_tenant_key_with_session(mock_session, "tenant-1")
        assert result == raw_key

    def test_get_nonexistent_key_raises(self, key_manager, mock_session):
        """Test getting a key for unknown tenant raises KeyError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(KeyError, match="No encryption key found"):
            key_manager.get_tenant_key_with_session(mock_session, "nonexistent")

    def test_get_key_wrong_master_raises(self, mock_session):
        """Test decryption fails when master key has changed."""
        # Encrypt with one key
        key1 = Fernet.generate_key()
        fernet1 = Fernet(key1)
        raw_key = Fernet.generate_key()
        encrypted = fernet1.encrypt(raw_key)

        key_record = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=encrypted,
            key_version=1,
        )
        mock_session.query.return_value.filter.return_value.first.return_value = (
            key_record
        )

        # Try to decrypt with a different master key
        different_master = Fernet.generate_key().decode()
        km = DatabaseKeyManager(master_key=different_master)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            km.get_tenant_key_with_session(mock_session, "tenant-1")

    def test_destroy_tenant_key(self, key_manager, mock_session):
        """Test destroying a tenant key."""
        key_record = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=b"data",
            key_version=1,
        )
        mock_session.query.return_value.filter.return_value.first.return_value = (
            key_record
        )

        key_manager.destroy_tenant_key_with_session(mock_session, "tenant-1")

        mock_session.delete.assert_called_once_with(key_record)

    def test_destroy_nonexistent_key(self, key_manager, mock_session):
        """Test destroying a nonexistent key doesn't raise."""
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        key_manager.destroy_tenant_key_with_session(mock_session, "nonexistent")
        mock_session.delete.assert_not_called()

    def test_rotate_tenant_key(self, key_manager, mock_session):
        """Test rotating a tenant's encryption key."""
        old_raw_key = Fernet.generate_key()
        old_encrypted = key_manager._master_fernet.encrypt(old_raw_key)

        key_record = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=old_encrypted,
            key_version=1,
        )
        mock_session.query.return_value.filter.return_value.first.return_value = (
            key_record
        )

        new_key = key_manager.rotate_tenant_key_with_session(mock_session, "tenant-1")

        # New key should be different from old
        assert new_key != old_raw_key
        # Version should be incremented
        assert key_record.key_version == 2
        # rotated_at should be set
        assert key_record.rotated_at is not None
        # New key should be valid Fernet key
        Fernet(new_key)

    def test_rotate_nonexistent_key_raises(self, key_manager, mock_session):
        """Test rotating a nonexistent key raises KeyError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(KeyError, match="No encryption key found"):
            key_manager.rotate_tenant_key_with_session(mock_session, "nonexistent")

    def test_base_methods_raise_not_implemented(self, key_manager):
        """Test that non-session methods raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            key_manager.get_tenant_key("tenant-1")
        with pytest.raises(NotImplementedError):
            key_manager.create_tenant_key("tenant-1")
        with pytest.raises(NotImplementedError):
            key_manager.destroy_tenant_key("tenant-1")
        with pytest.raises(NotImplementedError):
            key_manager.rotate_tenant_key("tenant-1")


class TestTenantEncryptor:
    """Tests for TenantEncryptor."""

    @pytest.fixture
    def setup_encryptor(self):
        """Create encryptor with a test key manager and session."""
        master_key = Fernet.generate_key().decode()
        key_manager = DatabaseKeyManager(master_key=master_key)

        # Create a mock session that returns a valid encrypted key
        raw_key = Fernet.generate_key()
        encrypted_key = key_manager._master_fernet.encrypt(raw_key)

        session = MagicMock()
        key_record = TenantEncryptionKey(
            tenant_id="tenant-1",
            encrypted_key=encrypted_key,
            key_version=1,
        )
        session.query.return_value.filter.return_value.first.return_value = key_record

        encryptor = TenantEncryptor(key_manager)
        return encryptor, session

    def test_encrypt_decrypt_roundtrip(self, setup_encryptor):
        """Test that encrypt then decrypt returns original plaintext."""
        encryptor, session = setup_encryptor

        plaintext = "Hello, this is sensitive data!"
        ciphertext = encryptor.encrypt(session, "tenant-1", plaintext)

        # Ciphertext should be different from plaintext
        assert ciphertext != plaintext

        # Decryption should return original
        result = encryptor.decrypt(session, "tenant-1", ciphertext)
        assert result == plaintext

    def test_encrypt_produces_different_ciphertexts(self, setup_encryptor):
        """Test that encrypting same plaintext twice gives different results."""
        encryptor, session = setup_encryptor

        plaintext = "same data"
        ct1 = encryptor.encrypt(session, "tenant-1", plaintext)
        ct2 = encryptor.encrypt(session, "tenant-1", plaintext)

        # Fernet includes timestamp, so same plaintext gives different ciphertext
        assert ct1 != ct2

    def test_encrypt_returns_string(self, setup_encryptor):
        """Test that encrypted result is a string (base64)."""
        encryptor, session = setup_encryptor

        result = encryptor.encrypt(session, "tenant-1", "test")
        assert isinstance(result, str)

    def test_decrypt_returns_string(self, setup_encryptor):
        """Test that decrypted result is a string."""
        encryptor, session = setup_encryptor

        ciphertext = encryptor.encrypt(session, "tenant-1", "test data")
        result = encryptor.decrypt(session, "tenant-1", ciphertext)
        assert isinstance(result, str)
        assert result == "test data"
