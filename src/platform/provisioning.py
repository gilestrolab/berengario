"""
Tenant provisioning service.

Orchestrates the creation, suspension, and deletion of tenants
across all platform components (database, storage, encryption, email).
"""

import logging
import re
import unicodedata
from datetime import datetime
from typing import Optional

from src.config import settings
from src.platform.db_manager import TenantDBManager
from src.platform.encryption import DatabaseKeyManager
from src.platform.models import (
    Tenant,
    TenantStatus,
    TenantUser,
    TenantUserRole,
)
from src.platform.storage import StorageBackend

logger = logging.getLogger(__name__)

# Valid slug pattern: lowercase alphanumeric and hyphens, 2-63 chars
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$")


def generate_slug(name: str) -> str:
    """
    Generate a URL-safe slug from a human-readable name.

    Handles unicode characters by transliterating to ASCII,
    lowercases, replaces non-alphanumeric with hyphens, and
    trims to 2-63 characters.

    Args:
        name: Human-readable name (e.g., "Acme Corp").

    Returns:
        URL-safe slug (e.g., "acme-corp").

    Raises:
        ValueError: If name produces an empty or too-short slug.
    """
    # Transliterate unicode to ASCII (e.g., ü→u, é→e)
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    # Lowercase
    slug = slug.lower()
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Collapse multiple hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    # Trim to max 63 chars
    slug = slug[:63].rstrip("-")

    if len(slug) < 2:
        raise ValueError(
            f"Name '{name}' produces a slug that is too short ('{slug}'). "
            "Please provide a longer name."
        )

    return slug


class ProvisioningError(Exception):
    """Error during tenant provisioning."""


class TenantProvisioner:
    """
    Orchestrates tenant lifecycle operations.

    Handles creating, suspending, resuming, and deleting tenants
    with proper resource management across all platform components.

    Attributes:
        db_manager: TenantDBManager for database operations.
        storage: StorageBackend for file storage.
        key_manager: DatabaseKeyManager for encryption keys (optional).
    """

    def __init__(
        self,
        db_manager: TenantDBManager,
        storage: StorageBackend,
        key_manager: Optional[DatabaseKeyManager] = None,
    ):
        """
        Initialize tenant provisioner.

        Args:
            db_manager: Database manager for platform and tenant DBs.
            storage: Storage backend for file operations.
            key_manager: Key manager for per-tenant encryption (optional).
        """
        self.db_manager = db_manager
        self.storage = storage
        self.key_manager = key_manager
        logger.info("TenantProvisioner initialized")

    @staticmethod
    def validate_slug(slug: str) -> bool:
        """
        Validate a tenant slug.

        Slugs must be lowercase alphanumeric with optional hyphens,
        2-63 characters, and cannot start or end with a hyphen.

        Args:
            slug: Slug to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not slug or len(slug) < 2 or len(slug) > 63:
            return False
        return bool(SLUG_PATTERN.match(slug))

    def create_tenant(
        self,
        slug: str,
        name: str,
        admin_email: str,
        description: Optional[str] = None,
        organization: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> Tenant:
        """
        Provision a new tenant with all required resources.

        Steps:
        1. Validate slug uniqueness
        2. Create Tenant record (status=provisioning)
        3. Create tenant database
        4. Run migrations on tenant database
        5. Create storage (S3 bucket or local directory)
        6. Create encryption key (if key_manager configured)
        7. Create admin user
        8. Activate tenant (status=active)

        Args:
            slug: URL-safe tenant identifier.
            name: Human-readable tenant name.
            admin_email: Email of the initial admin user.
            description: Optional description (used in RAG prompts).
            organization: Optional organization name.
            custom_prompt: Optional custom RAG system prompt.
            llm_model: Optional per-tenant LLM model override.

        Returns:
            Created and activated Tenant model.

        Raises:
            ProvisioningError: If any provisioning step fails.
            ValueError: If slug is invalid or already taken.
        """
        # Validate slug format
        if not self.validate_slug(slug):
            raise ValueError(
                f"Invalid slug '{slug}'. Must be 2-63 chars, lowercase "
                "alphanumeric with optional hyphens."
            )

        db_name = f"berengario_tenant_{slug.replace('-', '_')}"
        email_address = f"{slug}@{settings.platform_domain}"
        storage_path = f"tenants/{slug}"

        logger.info(f"Provisioning tenant: slug={slug}, name={name}")

        with self.db_manager.get_platform_session() as session:
            # Check slug uniqueness
            existing = session.query(Tenant).filter(Tenant.slug == slug).first()
            if existing:
                raise ValueError(f"Tenant with slug '{slug}' already exists")

            # Check email uniqueness
            existing_email = (
                session.query(Tenant)
                .filter(Tenant.email_address == email_address)
                .first()
            )
            if existing_email:
                raise ValueError(f"Tenant with email '{email_address}' already exists")

            # Step 1: Create tenant record with invite code
            invite_code = Tenant.generate_invite_code()
            tenant = Tenant(
                slug=slug,
                name=name,
                description=description,
                organization=organization,
                status=TenantStatus.PROVISIONING,
                email_address=email_address,
                email_display_name=f"{name} AI Assistant",
                custom_prompt=custom_prompt,
                llm_model=llm_model,
                invite_code=invite_code,
                db_name=db_name,
                storage_path=storage_path,
            )
            session.add(tenant)
            session.flush()  # Get the generated ID

            tenant_id = tenant.id
            logger.info(f"Created tenant record: id={tenant_id}, slug={slug}")

            try:
                # Step 2: Create tenant database
                if not self.db_manager.create_tenant_database(db_name):
                    raise ProvisioningError(
                        f"Failed to create tenant database: {db_name}"
                    )

                # Step 3: Run migrations on tenant database
                self.db_manager.init_tenant_db(db_name)

                # Step 4: Create storage
                self.storage.ensure_tenant_storage(slug)

                # Step 5: Create encryption key (if configured)
                if self.key_manager:
                    self.key_manager.create_tenant_key_with_session(session, tenant_id)

                # Step 6: Create admin user
                admin_user = TenantUser(
                    email=admin_email,
                    tenant_id=tenant_id,
                    role=TenantUserRole.ADMIN,
                )
                session.add(admin_user)

                # Step 7: Activate tenant
                tenant.status = TenantStatus.ACTIVE
                logger.info(
                    f"Tenant provisioned successfully: slug={slug}, "
                    f"db={db_name}, email={email_address}"
                )

                return tenant

            except Exception as e:
                # Rollback: clean up partially provisioned resources
                logger.error(
                    f"Provisioning failed for tenant {slug}: {e}",
                    exc_info=True,
                )
                self._cleanup_failed_provisioning(slug, db_name)
                raise ProvisioningError(
                    f"Failed to provision tenant '{slug}': {e}"
                ) from e

    def _cleanup_failed_provisioning(self, slug: str, db_name: str) -> None:
        """
        Clean up resources from a failed provisioning attempt.

        Args:
            slug: Tenant slug.
            db_name: Tenant database name.
        """
        logger.warning(f"Cleaning up failed provisioning for: {slug}")

        try:
            self.db_manager.drop_tenant_database(db_name)
        except Exception as e:
            logger.warning(f"Failed to drop tenant DB during cleanup: {e}")

        try:
            self.storage.delete_tenant_data(slug)
        except Exception as e:
            logger.warning(f"Failed to delete tenant storage during cleanup: {e}")

    def suspend_tenant(self, slug: str) -> bool:
        """
        Suspend a tenant (disable all access).

        Args:
            slug: Tenant slug.

        Returns:
            True if suspended successfully.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            if tenant.status == TenantStatus.SUSPENDED:
                logger.info(f"Tenant already suspended: {slug}")
                return True

            tenant.status = TenantStatus.SUSPENDED
            tenant.updated_at = datetime.utcnow()
            logger.info(f"Tenant suspended: {slug}")
            return True

    def resume_tenant(self, slug: str) -> bool:
        """
        Resume a suspended tenant.

        Args:
            slug: Tenant slug.

        Returns:
            True if resumed successfully.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            if tenant.status != TenantStatus.SUSPENDED:
                logger.info(f"Tenant is not suspended: {slug}")
                return True

            tenant.status = TenantStatus.ACTIVE
            tenant.updated_at = datetime.utcnow()
            logger.info(f"Tenant resumed: {slug}")
            return True

    def delete_tenant(self, slug: str, crypto_shred: bool = True) -> bool:
        """
        Permanently delete a tenant and all associated data.

        Performs crypto-shredding first (if enabled), then cleans up
        all resources: database, storage, and platform records.

        Args:
            slug: Tenant slug.
            crypto_shred: Whether to destroy encryption key first.

        Returns:
            True if deleted successfully.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            tenant_id = tenant.id
            db_name = tenant.db_name

            logger.warning(f"Deleting tenant: {slug} (id={tenant_id})")

            # Step 1: Suspend tenant first (prevent any new access)
            tenant.status = TenantStatus.SUSPENDED
            session.flush()

            # Step 2: Crypto-shred (destroy encryption key)
            if crypto_shred and self.key_manager:
                try:
                    self.key_manager.destroy_tenant_key_with_session(session, tenant_id)
                except Exception as e:
                    logger.warning(f"Error during crypto-shredding for {slug}: {e}")

            # Step 3: Delete storage
            try:
                self.storage.delete_tenant_data(slug)
            except Exception as e:
                logger.warning(f"Error deleting storage for {slug}: {e}")

            # Step 4: Drop tenant database
            try:
                self.db_manager.drop_tenant_database(db_name)
            except Exception as e:
                logger.warning(f"Error dropping database for {slug}: {e}")

            # Step 5: Delete platform records (cascade deletes users and keys)
            session.delete(tenant)
            logger.info(f"Tenant deleted: {slug}")
            return True

    def add_user(
        self,
        slug: str,
        email: str,
        role: TenantUserRole = TenantUserRole.QUERIER,
    ) -> TenantUser:
        """
        Add a user to a tenant.

        Args:
            slug: Tenant slug.
            email: User's email address.
            role: User's role in the tenant.

        Returns:
            Created TenantUser.

        Raises:
            ValueError: If tenant not found or user already exists.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            # Check for existing user
            existing = (
                session.query(TenantUser)
                .filter(
                    TenantUser.email == email.lower(),
                    TenantUser.tenant_id == tenant.id,
                )
                .first()
            )
            if existing:
                raise ValueError(
                    f"User {email} already exists in tenant {slug} "
                    f"with role {existing.role.value}"
                )

            user = TenantUser(
                email=email.lower(),
                tenant_id=tenant.id,
                role=role,
            )
            session.add(user)
            logger.info(f"Added user {email} to tenant {slug} with role {role.value}")
            return user

    def remove_user(self, slug: str, email: str) -> bool:
        """
        Remove a user from a tenant.

        Args:
            slug: Tenant slug.
            email: User's email address.

        Returns:
            True if removed, False if not found.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            user = (
                session.query(TenantUser)
                .filter(
                    TenantUser.email == email.lower(),
                    TenantUser.tenant_id == tenant.id,
                )
                .first()
            )
            if not user:
                return False

            session.delete(user)
            logger.info(f"Removed user {email} from tenant {slug}")
            return True

    def get_tenant_users(self, slug: str) -> list[dict]:
        """
        List all users in a tenant.

        Args:
            slug: Tenant slug.

        Returns:
            List of user dictionaries.
        """
        with self.db_manager.get_platform_session() as session:
            tenant = session.query(Tenant).filter(Tenant.slug == slug).first()
            if not tenant:
                raise ValueError(f"Tenant not found: {slug}")

            users = (
                session.query(TenantUser)
                .filter(TenantUser.tenant_id == tenant.id)
                .all()
            )
            return [u.to_dict() for u in users]
