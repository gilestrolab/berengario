"""
Platform bootstrap — shared infrastructure initialization.

Initializes TenantDBManager / storage / encryption / provisioner and
auto-provisions a default tenant when none exist (ST mode).
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PlatformInfra:
    """
    Bundle of platform-level infrastructure singletons.

    Attributes:
        db_manager: TenantDBManager with platform DB initialized.
        storage: StorageBackend (local or S3).
        key_manager: DatabaseKeyManager (None when MEK is not configured).
        provisioner: TenantProvisioner (None when not requested).
    """

    db_manager: object  # TenantDBManager
    storage: object  # StorageBackend
    key_manager: Optional[object] = None  # DatabaseKeyManager | None
    provisioner: Optional[object] = None  # TenantProvisioner | None


def auto_provision_default_tenant(db_manager, storage, key_manager=None) -> None:
    """
    Auto-provision a default tenant when none exist.

    Reads INSTANCE_NAME, INSTANCE_DESCRIPTION, ORGANIZATION, and
    EMAIL_TARGET_ADDRESS from settings to create the tenant and its
    database/storage. Skips silently if tenants already exist.

    Args:
        db_manager: TenantDBManager instance.
        storage: StorageBackend instance.
        key_manager: DatabaseKeyManager instance (optional).
    """
    from src.config import settings
    from src.platform.models import Tenant

    with db_manager.get_platform_session() as session:
        count = session.query(Tenant).count()
        if count > 0:
            logger.debug(f"Platform has {count} tenant(s), skipping auto-provisioning")
            return

    logger.info(
        "No tenants found — auto-provisioning default tenant from .env settings"
    )

    from src.platform.provisioning import TenantProvisioner, generate_slug

    slug = generate_slug(settings.instance_name)
    name = settings.instance_name
    description = settings.instance_description
    organization = settings.organization or ""
    email_address = settings.email_target_address

    provisioner = TenantProvisioner(db_manager, storage, key_manager)

    try:
        tenant = provisioner.create_tenant(
            slug=slug,
            name=name,
            description=description,
            organization=organization,
            admin_email=email_address,  # Bot's own address as placeholder admin
            email_address=email_address,
        )
        logger.info(
            f"Default tenant auto-provisioned: slug='{tenant.slug}', "
            f"name='{tenant.name}', email='{email_address}'"
        )
    except Exception as e:
        logger.error(f"Failed to auto-provision default tenant: {e}", exc_info=True)
        raise


def bootstrap_platform(*, include_provisioner: bool = False) -> PlatformInfra:
    """
    Initialize the shared platform infrastructure.

    Creates TenantDBManager (with platform DB tables), a storage backend,
    and optionally a DatabaseKeyManager and TenantProvisioner.
    Always auto-provisions a default tenant when none exist.

    Args:
        include_provisioner: If True, also create a TenantProvisioner
            (needed by platform_admin, not by web/email services).

    Returns:
        PlatformInfra with all initialized components.
    """
    from src.config import settings
    from src.platform.db_manager import TenantDBManager
    from src.platform.storage import create_storage_backend

    logger.info("Bootstrapping platform infrastructure...")

    db_manager = TenantDBManager()
    db_manager.init_platform_db()

    storage = create_storage_backend()

    key_manager = None
    if settings.master_encryption_key:
        from src.platform.encryption import DatabaseKeyManager

        key_manager = DatabaseKeyManager()
        logger.info("DatabaseKeyManager initialized (MEK configured)")

    # Auto-provision default tenant when none exist
    auto_provision_default_tenant(db_manager, storage, key_manager)

    provisioner = None
    if include_provisioner:
        from src.platform.provisioning import TenantProvisioner

        provisioner = TenantProvisioner(db_manager, storage, key_manager)

    logger.info("Platform infrastructure ready")
    return PlatformInfra(
        db_manager=db_manager,
        storage=storage,
        key_manager=key_manager,
        provisioner=provisioner,
    )
