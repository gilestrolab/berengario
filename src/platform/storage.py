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
    S3-compatible storage backend (MinIO, AWS S3, Garage, Cloudflare R2, etc.).

    Supports two modes:
    - Single bucket (s3_bucket_name set): All tenants share one bucket,
      isolated by key prefixes (e.g., "{tenant_slug}/documents/file.pdf").
    - Per-tenant buckets (s3_bucket_prefix set): Each tenant gets its own
      bucket named "{prefix}{tenant_slug}".
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        bucket_name: Optional[str] = None,
        bucket_prefix: Optional[str] = None,
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage backend. "
                "Install with: pip install boto3"
            )

        self.single_bucket = bucket_name or settings.s3_bucket_name or ""
        self.bucket_prefix = bucket_prefix or settings.s3_bucket_prefix
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or settings.s3_endpoint_url,
            aws_access_key_id=access_key or settings.s3_access_key,
            aws_secret_access_key=secret_key or settings.s3_secret_key,
            region_name=region or settings.s3_region,
        )
        mode = (
            f"single-bucket={self.single_bucket}"
            if self.single_bucket
            else f"per-tenant prefix={self.bucket_prefix}"
        )
        logger.info(
            f"S3StorageBackend initialized: endpoint={endpoint_url or settings.s3_endpoint_url}, {mode}"
        )

    def _bucket_name(self, tenant_slug: str) -> str:
        """Get S3 bucket name for a tenant."""
        if self.single_bucket:
            return self.single_bucket
        return f"{self.bucket_prefix}{tenant_slug}"

    def _object_key(self, tenant_slug: str, key: str) -> str:
        """Get the full S3 object key, prefixed with tenant slug in single-bucket mode."""
        if self.single_bucket:
            return f"{tenant_slug}/{key}"
        return key

    def _strip_tenant_prefix(self, tenant_slug: str, object_key: str) -> str:
        """Strip tenant prefix from object key in single-bucket mode."""
        if self.single_bucket:
            prefix = f"{tenant_slug}/"
            if object_key.startswith(prefix):
                return object_key[len(prefix) :]
        return object_key

    def put(
        self,
        tenant_slug: str,
        key: str,
        data: bytes,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a file to S3."""
        bucket = self._bucket_name(tenant_slug)
        obj_key = self._object_key(tenant_slug, key)
        extra_args = {}
        if metadata:
            extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

        self.client.put_object(
            Bucket=bucket,
            Key=obj_key,
            Body=data,
            **extra_args,
        )
        logger.debug(f"Stored to S3: s3://{bucket}/{obj_key} ({len(data)} bytes)")
        return key

    def get(self, tenant_slug: str, key: str) -> bytes:
        """Retrieve a file from S3."""
        bucket = self._bucket_name(tenant_slug)
        obj_key = self._object_key(tenant_slug, key)
        try:
            response = self.client.get_object(Bucket=bucket, Key=obj_key)
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"File not found: s3://{bucket}/{obj_key}")

    def delete(self, tenant_slug: str, key: str) -> None:
        """Delete a file from S3."""
        bucket = self._bucket_name(tenant_slug)
        obj_key = self._object_key(tenant_slug, key)
        self.client.delete_object(Bucket=bucket, Key=obj_key)
        logger.debug(f"Deleted from S3: s3://{bucket}/{obj_key}")

    def exists(self, tenant_slug: str, key: str) -> bool:
        """Check if file exists in S3."""
        bucket = self._bucket_name(tenant_slug)
        obj_key = self._object_key(tenant_slug, key)
        try:
            self.client.head_object(Bucket=bucket, Key=obj_key)
            return True
        except Exception:
            return False

    def list_keys(self, tenant_slug: str, prefix: str = "") -> list[str]:
        """List file keys for a tenant in S3."""
        bucket = self._bucket_name(tenant_slug)
        keys = []

        # In single-bucket mode, scope listing to tenant prefix
        if self.single_bucket:
            s3_prefix = f"{tenant_slug}/{prefix}" if prefix else f"{tenant_slug}/"
        else:
            s3_prefix = prefix

        try:
            paginator = self.client.get_paginator("list_objects_v2")
            page_params = {"Bucket": bucket}
            if s3_prefix:
                page_params["Prefix"] = s3_prefix

            for page in paginator.paginate(**page_params):
                for obj in page.get("Contents", []):
                    keys.append(self._strip_tenant_prefix(tenant_slug, obj["Key"]))
        except Exception as e:
            logger.error(f"Error listing S3 keys for {bucket}: {e}")

        return sorted(keys)

    def delete_tenant_data(self, tenant_slug: str) -> None:
        """Delete all data for a tenant."""
        bucket = self._bucket_name(tenant_slug)

        if self.single_bucket:
            # Delete all objects under the tenant prefix
            s3_prefix = f"{tenant_slug}/"
            try:
                paginator = self.client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
                    objects = page.get("Contents", [])
                    if objects:
                        delete_request = {
                            "Objects": [{"Key": obj["Key"]} for obj in objects]
                        }
                        self.client.delete_objects(
                            Bucket=bucket, Delete=delete_request
                        )
                logger.info(
                    f"Deleted tenant data from S3: s3://{bucket}/{s3_prefix}"
                )
            except Exception as e:
                logger.error(
                    f"Error deleting S3 tenant data for {tenant_slug}: {e}"
                )
                raise
        else:
            # Per-tenant bucket: delete all objects then delete the bucket
            try:
                paginator = self.client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket):
                    objects = page.get("Contents", [])
                    if objects:
                        delete_request = {
                            "Objects": [{"Key": obj["Key"]} for obj in objects]
                        }
                        self.client.delete_objects(
                            Bucket=bucket, Delete=delete_request
                        )
                self.client.delete_bucket(Bucket=bucket)
                logger.info(f"Deleted S3 bucket for tenant: {bucket}")
            except Exception as e:
                logger.error(
                    f"Error deleting S3 tenant data for {bucket}: {e}"
                )
                raise

    def ensure_tenant_storage(self, tenant_slug: str) -> None:
        """Ensure storage exists for a tenant."""
        bucket = self._bucket_name(tenant_slug)
        try:
            self.client.head_bucket(Bucket=bucket)
            logger.debug(f"S3 bucket already exists: {bucket}")
        except Exception:
            if self.single_bucket:
                self.client.create_bucket(Bucket=bucket)
                logger.info(f"Created shared S3 bucket: {bucket}")
            else:
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
