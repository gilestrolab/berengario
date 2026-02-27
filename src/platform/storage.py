"""
Storage backend abstraction for multi-tenant file storage.

Provides a unified interface for storing and retrieving files,
with implementations for local filesystem and S3-compatible storage.
"""

import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """
    Abstract storage interface for tenant file operations.

    All paths are relative within a tenant's namespace. The backend
    handles mapping to the actual storage location (local path or S3 key).
    """

    @abstractmethod
    def put(
        self,
        tenant_slug: str,
        key: str,
        data: bytes,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Store a file.

        Args:
            tenant_slug: Tenant identifier.
            key: File path/key within tenant namespace (e.g., "documents/report.pdf").
            data: File content as bytes.
            metadata: Optional metadata dict to store with the file.

        Returns:
            Storage key/path of the stored file.
        """

    @abstractmethod
    def get(self, tenant_slug: str, key: str) -> bytes:
        """
        Retrieve a file.

        Args:
            tenant_slug: Tenant identifier.
            key: File path/key within tenant namespace.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If file does not exist.
        """

    @abstractmethod
    def delete(self, tenant_slug: str, key: str) -> None:
        """
        Delete a file.

        Args:
            tenant_slug: Tenant identifier.
            key: File path/key within tenant namespace.
        """

    @abstractmethod
    def exists(self, tenant_slug: str, key: str) -> bool:
        """
        Check if a file exists.

        Args:
            tenant_slug: Tenant identifier.
            key: File path/key within tenant namespace.

        Returns:
            True if file exists, False otherwise.
        """

    @abstractmethod
    def list_keys(self, tenant_slug: str, prefix: str = "") -> list[str]:
        """
        List file keys for a tenant.

        Args:
            tenant_slug: Tenant identifier.
            prefix: Optional prefix to filter keys.

        Returns:
            List of file keys matching the prefix.
        """

    @abstractmethod
    def delete_tenant_data(self, tenant_slug: str) -> None:
        """
        Delete all data for a tenant.

        WARNING: This is irreversible.

        Args:
            tenant_slug: Tenant identifier.
        """

    @abstractmethod
    def ensure_tenant_storage(self, tenant_slug: str) -> None:
        """
        Ensure storage exists for a tenant (create bucket/directory).

        Args:
            tenant_slug: Tenant identifier.
        """


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend.

    Stores files under a base directory with per-tenant subdirectories.
    Preserves current single-tenant behavior when used with a default tenant.

    Directory structure:
        {base_path}/{tenant_slug}/documents/
        {base_path}/{tenant_slug}/kb/documents/
        {base_path}/{tenant_slug}/kb/emails/
        {base_path}/{tenant_slug}/temp/
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize local storage backend.

        Args:
            base_path: Base directory for all tenant storage.
                       Defaults to "data/tenants" in multi-tenant mode,
                       or "data" in single-tenant mode.
        """
        if base_path:
            self.base_path = Path(base_path)
        elif settings.multi_tenant:
            self.base_path = Path("data/tenants")
        else:
            self.base_path = Path("data")

        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorageBackend initialized: base_path={self.base_path}")

    def _tenant_path(self, tenant_slug: str) -> Path:
        """Get the root path for a tenant."""
        return self.base_path / tenant_slug

    def _full_path(self, tenant_slug: str, key: str) -> Path:
        """Get full filesystem path for a tenant file."""
        return self._tenant_path(tenant_slug) / key

    def put(
        self,
        tenant_slug: str,
        key: str,
        data: bytes,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a file to local filesystem."""
        path = self._full_path(tenant_slug, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.debug(f"Stored file: {path} ({len(data)} bytes)")
        return key

    def get(self, tenant_slug: str, key: str) -> bytes:
        """Retrieve a file from local filesystem."""
        path = self._full_path(tenant_slug, key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_bytes()

    def delete(self, tenant_slug: str, key: str) -> None:
        """Delete a file from local filesystem."""
        path = self._full_path(tenant_slug, key)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted file: {path}")

            # Clean up empty parent directories up to tenant root
            parent = path.parent
            tenant_root = self._tenant_path(tenant_slug)
            while parent != tenant_root and parent.exists():
                try:
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    else:
                        break
                except OSError:
                    break

    def exists(self, tenant_slug: str, key: str) -> bool:
        """Check if file exists on local filesystem."""
        return self._full_path(tenant_slug, key).exists()

    def list_keys(self, tenant_slug: str, prefix: str = "") -> list[str]:
        """List files for a tenant on local filesystem."""
        tenant_root = self._tenant_path(tenant_slug)
        if not tenant_root.exists():
            return []

        search_root = tenant_root / prefix if prefix else tenant_root
        if not search_root.exists():
            return []

        keys = []
        for path in search_root.rglob("*"):
            if path.is_file():
                # Return path relative to tenant root
                keys.append(str(path.relative_to(tenant_root)))
        return sorted(keys)

    def delete_tenant_data(self, tenant_slug: str) -> None:
        """Delete all data for a tenant from local filesystem."""
        tenant_root = self._tenant_path(tenant_slug)
        if tenant_root.exists():
            shutil.rmtree(tenant_root)
            logger.info(f"Deleted all local storage for tenant: {tenant_slug}")

    def ensure_tenant_storage(self, tenant_slug: str) -> None:
        """Create tenant directory structure."""
        tenant_root = self._tenant_path(tenant_slug)
        subdirs = [
            "documents",
            "kb/documents",
            "kb/emails",
            "temp",
            "chroma_db",
            "config",
        ]
        for subdir in subdirs:
            (tenant_root / subdir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured local storage for tenant: {tenant_slug}")

    def get_tenant_path(self, tenant_slug: str) -> Path:
        """
        Get the filesystem path for a tenant's storage root.

        Useful for components that need direct filesystem access
        (e.g., ChromaDB PersistentClient).

        Args:
            tenant_slug: Tenant identifier.

        Returns:
            Path to tenant's storage directory.
        """
        return self._tenant_path(tenant_slug)


class S3StorageBackend(StorageBackend):
    """
    S3-compatible storage backend (MinIO, AWS S3, Cloudflare R2, etc.).

    Uses one bucket per tenant for strong isolation.
    Bucket naming: {prefix}{tenant_slug} (e.g., "berengario-tenant-acme").
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        bucket_prefix: Optional[str] = None,
    ):
        """
        Initialize S3 storage backend.

        Args:
            endpoint_url: S3-compatible endpoint URL.
            access_key: S3 access key ID.
            secret_key: S3 secret access key.
            region: S3 region.
            bucket_prefix: Prefix for tenant bucket names.
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage backend. "
                "Install with: pip install boto3"
            )

        self.bucket_prefix = bucket_prefix or settings.s3_bucket_prefix
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or settings.s3_endpoint_url,
            aws_access_key_id=access_key or settings.s3_access_key,
            aws_secret_access_key=secret_key or settings.s3_secret_key,
            region_name=region or settings.s3_region,
        )
        logger.info(
            f"S3StorageBackend initialized: endpoint={endpoint_url or settings.s3_endpoint_url}"
        )

    def _bucket_name(self, tenant_slug: str) -> str:
        """Get S3 bucket name for a tenant."""
        return f"{self.bucket_prefix}{tenant_slug}"

    def put(
        self,
        tenant_slug: str,
        key: str,
        data: bytes,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a file to S3."""
        bucket = self._bucket_name(tenant_slug)
        extra_args = {}
        if metadata:
            extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

        self.client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            **extra_args,
        )
        logger.debug(f"Stored to S3: s3://{bucket}/{key} ({len(data)} bytes)")
        return key

    def get(self, tenant_slug: str, key: str) -> bytes:
        """Retrieve a file from S3."""
        bucket = self._bucket_name(tenant_slug)
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"File not found: s3://{bucket}/{key}")

    def delete(self, tenant_slug: str, key: str) -> None:
        """Delete a file from S3."""
        bucket = self._bucket_name(tenant_slug)
        self.client.delete_object(Bucket=bucket, Key=key)
        logger.debug(f"Deleted from S3: s3://{bucket}/{key}")

    def exists(self, tenant_slug: str, key: str) -> bool:
        """Check if file exists in S3."""
        bucket = self._bucket_name(tenant_slug)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False

    def list_keys(self, tenant_slug: str, prefix: str = "") -> list[str]:
        """List file keys for a tenant in S3."""
        bucket = self._bucket_name(tenant_slug)
        keys = []

        try:
            paginator = self.client.get_paginator("list_objects_v2")
            page_params = {"Bucket": bucket}
            if prefix:
                page_params["Prefix"] = prefix

            for page in paginator.paginate(**page_params):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        except Exception as e:
            logger.error(f"Error listing S3 keys for {bucket}: {e}")

        return sorted(keys)

    def delete_tenant_data(self, tenant_slug: str) -> None:
        """Delete all data for a tenant (empty and delete bucket)."""
        bucket = self._bucket_name(tenant_slug)

        try:
            # Delete all objects first
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                objects = page.get("Contents", [])
                if objects:
                    delete_request = {
                        "Objects": [{"Key": obj["Key"]} for obj in objects]
                    }
                    self.client.delete_objects(Bucket=bucket, Delete=delete_request)

            # Delete the bucket
            self.client.delete_bucket(Bucket=bucket)
            logger.info(f"Deleted S3 bucket for tenant: {bucket}")
        except Exception as e:
            logger.error(f"Error deleting S3 tenant data for {bucket}: {e}")
            raise

    def ensure_tenant_storage(self, tenant_slug: str) -> None:
        """Create S3 bucket for a tenant."""
        bucket = self._bucket_name(tenant_slug)
        try:
            self.client.head_bucket(Bucket=bucket)
            logger.debug(f"S3 bucket already exists: {bucket}")
        except Exception:
            self.client.create_bucket(Bucket=bucket)
            logger.info(f"Created S3 bucket for tenant: {bucket}")


def create_storage_backend() -> StorageBackend:
    """
    Factory function to create the appropriate storage backend.

    Returns:
        StorageBackend instance based on configuration.
    """
    if settings.storage_backend == "s3":
        return S3StorageBackend()
    else:
        return LocalStorageBackend()
