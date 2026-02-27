"""
Per-tenant encryption with envelope encryption pattern.

Each tenant has a unique Tenant Encryption Key (TEK) which is encrypted
by a Master Encryption Key (MEK). This enables crypto-shredding:
deleting a tenant's key makes all their data permanently unreadable.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings

logger = logging.getLogger(__name__)


class KeyManager(ABC):
    """
    Abstract key management interface.

    Implementations store per-tenant encryption keys using different
    backends (database, HashiCorp Vault, AWS KMS, etc.).
    """

    @abstractmethod
    def get_tenant_key(self, tenant_id: str) -> bytes:
        """
        Retrieve the decrypted encryption key for a tenant.

        Args:
            tenant_id: Tenant UUID.

        Returns:
            Raw Fernet key bytes.

        Raises:
            KeyError: If no key exists for this tenant.
            ValueError: If key cannot be decrypted.
        """

    @abstractmethod
    def create_tenant_key(self, tenant_id: str) -> bytes:
        """
        Generate and store a new encryption key for a tenant.

        Args:
            tenant_id: Tenant UUID.

        Returns:
            The newly generated Fernet key bytes.

        Raises:
            ValueError: If a key already exists for this tenant.
        """

    @abstractmethod
    def destroy_tenant_key(self, tenant_id: str) -> None:
        """
        Permanently destroy a tenant's encryption key (crypto-shredding).

        After this operation, all data encrypted with this key is
        permanently unrecoverable.

        Args:
            tenant_id: Tenant UUID.
        """

    @abstractmethod
    def rotate_tenant_key(self, tenant_id: str) -> bytes:
        """
        Rotate a tenant's encryption key.

        Generates a new key and stores it. The old key is destroyed.
        Note: Data encrypted with the old key must be re-encrypted
        with the new key separately.

        Args:
            tenant_id: Tenant UUID.

        Returns:
            The new Fernet key bytes.
        """


class DatabaseKeyManager(KeyManager):
    """
    Stores per-tenant encryption keys in the platform database.

    TEKs are encrypted with the MEK (from environment variable)
    before storage. This is suitable for early-stage deployments.
    For production, consider VaultKeyManager or KMSKeyManager.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize database key manager.

        Args:
            master_key: Master Encryption Key (base64-encoded Fernet key).
                        If not provided, uses MASTER_ENCRYPTION_KEY from settings.

        Raises:
            ValueError: If no master key is configured.
        """
        key_str = master_key or settings.master_encryption_key
        if not key_str:
            raise ValueError(
                "Master encryption key not configured. Set MASTER_ENCRYPTION_KEY "
                "in environment. Generate with: python -c "
                '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

        try:
            self._master_fernet = Fernet(
                key_str.encode() if isinstance(key_str, str) else key_str
            )
        except Exception as e:
            raise ValueError(f"Invalid master encryption key: {e}")

        logger.info("DatabaseKeyManager initialized")

    def _get_db_session(self):
        """Get a platform database session (lazy import to avoid circular deps)."""

        # This assumes a global TenantDBManager instance exists
        # In practice, this is injected or accessed via a module-level singleton
        raise NotImplementedError(
            "DatabaseKeyManager requires a TenantDBManager instance. "
            "Use DatabaseKeyManagerWithSession instead."
        )

    def get_tenant_key(self, tenant_id: str) -> bytes:
        """Retrieve and decrypt a tenant's encryption key from the database."""

        # Caller must provide session context
        raise NotImplementedError("Use get_tenant_key_with_session()")

    def create_tenant_key(self, tenant_id: str) -> bytes:
        """Generate and store a new encrypted tenant key."""
        raise NotImplementedError("Use create_tenant_key_with_session()")

    def destroy_tenant_key(self, tenant_id: str) -> None:
        """Destroy a tenant's encryption key."""
        raise NotImplementedError("Use destroy_tenant_key_with_session()")

    def rotate_tenant_key(self, tenant_id: str) -> bytes:
        """Rotate a tenant's encryption key."""
        raise NotImplementedError("Use rotate_tenant_key_with_session()")

    def get_tenant_key_with_session(self, session, tenant_id: str) -> bytes:
        """
        Retrieve and decrypt a tenant's encryption key.

        Args:
            session: SQLAlchemy session for platform database.
            tenant_id: Tenant UUID.

        Returns:
            Decrypted Fernet key bytes.
        """
        from src.platform.models import TenantEncryptionKey

        key_record = (
            session.query(TenantEncryptionKey)
            .filter(TenantEncryptionKey.tenant_id == tenant_id)
            .first()
        )

        if not key_record:
            raise KeyError(f"No encryption key found for tenant: {tenant_id}")

        try:
            decrypted = self._master_fernet.decrypt(key_record.encrypted_key)
            return decrypted
        except InvalidToken:
            raise ValueError(
                f"Failed to decrypt key for tenant {tenant_id}. "
                "Master key may have changed."
            )

    def create_tenant_key_with_session(self, session, tenant_id: str) -> bytes:
        """
        Generate and store a new encryption key for a tenant.

        Args:
            session: SQLAlchemy session for platform database.
            tenant_id: Tenant UUID.

        Returns:
            The newly generated Fernet key bytes.
        """
        from src.platform.models import TenantEncryptionKey

        # Check if key already exists
        existing = (
            session.query(TenantEncryptionKey)
            .filter(TenantEncryptionKey.tenant_id == tenant_id)
            .first()
        )
        if existing:
            raise ValueError(f"Encryption key already exists for tenant: {tenant_id}")

        # Generate new Fernet key
        raw_key = Fernet.generate_key()

        # Encrypt with master key
        encrypted_key = self._master_fernet.encrypt(raw_key)

        # Store in database
        key_record = TenantEncryptionKey(
            tenant_id=tenant_id,
            encrypted_key=encrypted_key,
            key_version=1,
        )
        session.add(key_record)

        logger.info(f"Created encryption key for tenant: {tenant_id}")
        return raw_key

    def destroy_tenant_key_with_session(self, session, tenant_id: str) -> None:
        """
        Permanently destroy a tenant's encryption key.

        Args:
            session: SQLAlchemy session for platform database.
            tenant_id: Tenant UUID.
        """
        from src.platform.models import TenantEncryptionKey

        key_record = (
            session.query(TenantEncryptionKey)
            .filter(TenantEncryptionKey.tenant_id == tenant_id)
            .first()
        )

        if key_record:
            session.delete(key_record)
            logger.warning(
                f"Destroyed encryption key for tenant: {tenant_id} (crypto-shredding)"
            )
        else:
            logger.warning(f"No encryption key to destroy for tenant: {tenant_id}")

    def rotate_tenant_key_with_session(self, session, tenant_id: str) -> bytes:
        """
        Rotate a tenant's encryption key.

        Args:
            session: SQLAlchemy session for platform database.
            tenant_id: Tenant UUID.

        Returns:
            The new Fernet key bytes.
        """
        from src.platform.models import TenantEncryptionKey

        key_record = (
            session.query(TenantEncryptionKey)
            .filter(TenantEncryptionKey.tenant_id == tenant_id)
            .first()
        )

        if not key_record:
            raise KeyError(f"No encryption key found for tenant: {tenant_id}")

        # Generate new key
        new_raw_key = Fernet.generate_key()
        encrypted_key = self._master_fernet.encrypt(new_raw_key)

        # Update record
        key_record.encrypted_key = encrypted_key
        key_record.key_version += 1
        key_record.rotated_at = datetime.utcnow()

        logger.info(
            f"Rotated encryption key for tenant: {tenant_id} "
            f"(version {key_record.key_version})"
        )
        return new_raw_key


class TenantEncryptor:
    """
    Encrypts and decrypts data using per-tenant keys.

    Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
    """

    def __init__(self, key_manager: DatabaseKeyManager):
        """
        Initialize tenant encryptor.

        Args:
            key_manager: Key manager for retrieving tenant keys.
        """
        self.key_manager = key_manager

    def encrypt(self, session, tenant_id: str, plaintext: str) -> str:
        """
        Encrypt a string with a tenant's key.

        Args:
            session: Platform DB session.
            tenant_id: Tenant UUID.
            plaintext: String to encrypt.

        Returns:
            Base64-encoded encrypted string.
        """
        raw_key = self.key_manager.get_tenant_key_with_session(session, tenant_id)
        f = Fernet(raw_key)
        return f.encrypt(plaintext.encode()).decode()

    def decrypt(self, session, tenant_id: str, ciphertext: str) -> str:
        """
        Decrypt a string with a tenant's key.

        Args:
            session: Platform DB session.
            tenant_id: Tenant UUID.
            ciphertext: Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.
        """
        raw_key = self.key_manager.get_tenant_key_with_session(session, tenant_id)
        f = Fernet(raw_key)
        return f.decrypt(ciphertext.encode()).decode()
