"""
Unit tests for platform storage backends.

Tests LocalStorageBackend with a temporary directory.
S3StorageBackend is tested with mocks (no real S3 needed).
"""

import importlib.util
from unittest.mock import MagicMock, patch

import pytest

from src.platform.storage import LocalStorageBackend, create_storage_backend

HAS_BOTO3 = importlib.util.find_spec("boto3") is not None


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a LocalStorageBackend with a temp directory."""
        return LocalStorageBackend(base_path=str(tmp_path))

    @pytest.fixture
    def tenant_slug(self):
        """Default test tenant slug."""
        return "test-tenant"

    def test_ensure_tenant_storage(self, storage, tenant_slug, tmp_path):
        """Test creating tenant directory structure."""
        storage.ensure_tenant_storage(tenant_slug)

        tenant_root = tmp_path / tenant_slug
        assert tenant_root.exists()
        assert (tenant_root / "documents").exists()
        assert (tenant_root / "kb" / "documents").exists()
        assert (tenant_root / "kb" / "emails").exists()
        assert (tenant_root / "temp").exists()
        assert (tenant_root / "chroma_db").exists()
        assert (tenant_root / "config").exists()

    def test_put_and_get(self, storage, tenant_slug):
        """Test storing and retrieving a file."""
        data = b"Hello, multi-tenancy!"
        storage.put(tenant_slug, "documents/test.txt", data)

        result = storage.get(tenant_slug, "documents/test.txt")
        assert result == data

    def test_put_creates_directories(self, storage, tenant_slug):
        """Test that put creates parent directories automatically."""
        data = b"nested content"
        storage.put(tenant_slug, "deep/nested/dir/file.txt", data)

        result = storage.get(tenant_slug, "deep/nested/dir/file.txt")
        assert result == data

    def test_get_nonexistent_file(self, storage, tenant_slug):
        """Test getting a file that doesn't exist raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            storage.get(tenant_slug, "nonexistent.txt")

    def test_delete(self, storage, tenant_slug):
        """Test deleting a file."""
        storage.put(tenant_slug, "to-delete.txt", b"delete me")
        assert storage.exists(tenant_slug, "to-delete.txt")

        storage.delete(tenant_slug, "to-delete.txt")
        assert not storage.exists(tenant_slug, "to-delete.txt")

    def test_delete_nonexistent_file(self, storage, tenant_slug):
        """Test deleting a nonexistent file doesn't raise."""
        storage.delete(tenant_slug, "nonexistent.txt")  # Should not raise

    def test_delete_cleans_empty_parents(self, storage, tenant_slug):
        """Test that delete cleans up empty parent directories."""
        storage.put(tenant_slug, "deep/nested/file.txt", b"data")
        storage.delete(tenant_slug, "deep/nested/file.txt")

        # Parent directories should be cleaned up
        tenant_root = storage._tenant_path(tenant_slug)
        assert not (tenant_root / "deep" / "nested").exists()
        assert not (tenant_root / "deep").exists()

    def test_exists(self, storage, tenant_slug):
        """Test file existence check."""
        assert not storage.exists(tenant_slug, "test.txt")

        storage.put(tenant_slug, "test.txt", b"data")
        assert storage.exists(tenant_slug, "test.txt")

    def test_list_keys_empty(self, storage, tenant_slug):
        """Test listing keys for empty tenant."""
        keys = storage.list_keys(tenant_slug)
        assert keys == []

    def test_list_keys(self, storage, tenant_slug):
        """Test listing keys for a tenant."""
        storage.put(tenant_slug, "file1.txt", b"data1")
        storage.put(tenant_slug, "docs/file2.pdf", b"data2")
        storage.put(tenant_slug, "docs/file3.txt", b"data3")

        keys = storage.list_keys(tenant_slug)
        assert len(keys) == 3
        assert "file1.txt" in keys
        assert "docs/file2.pdf" in keys
        assert "docs/file3.txt" in keys

    def test_list_keys_with_prefix(self, storage, tenant_slug):
        """Test listing keys with prefix filter."""
        storage.put(tenant_slug, "docs/a.txt", b"a")
        storage.put(tenant_slug, "docs/b.txt", b"b")
        storage.put(tenant_slug, "other/c.txt", b"c")

        keys = storage.list_keys(tenant_slug, prefix="docs")
        assert len(keys) == 2
        assert "docs/a.txt" in keys
        assert "docs/b.txt" in keys
        assert "other/c.txt" not in keys

    def test_delete_tenant_data(self, storage, tenant_slug):
        """Test deleting all data for a tenant."""
        storage.ensure_tenant_storage(tenant_slug)
        storage.put(tenant_slug, "file.txt", b"data")

        storage.delete_tenant_data(tenant_slug)

        assert not storage._tenant_path(tenant_slug).exists()

    def test_delete_tenant_data_nonexistent(self, storage, tenant_slug):
        """Test deleting data for nonexistent tenant doesn't raise."""
        storage.delete_tenant_data("nonexistent-tenant")  # Should not raise

    def test_get_tenant_path(self, storage, tenant_slug, tmp_path):
        """Test getting the filesystem path for a tenant."""
        path = storage.get_tenant_path(tenant_slug)
        assert path == tmp_path / tenant_slug

    def test_tenant_isolation(self, storage):
        """Test that different tenants have isolated storage."""
        storage.put("tenant-a", "shared.txt", b"tenant A data")
        storage.put("tenant-b", "shared.txt", b"tenant B data")

        assert storage.get("tenant-a", "shared.txt") == b"tenant A data"
        assert storage.get("tenant-b", "shared.txt") == b"tenant B data"

        # Deleting tenant A doesn't affect tenant B
        storage.delete_tenant_data("tenant-a")
        assert not storage.exists("tenant-a", "shared.txt")
        assert storage.exists("tenant-b", "shared.txt")


@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed (optional dependency)")
class TestS3StorageBackend:
    """Tests for S3StorageBackend (mocked boto3)."""

    @pytest.fixture
    def s3_setup(self):
        """Mock boto3 and provide S3StorageBackend class for S3 tests."""
        from src.platform.storage import S3StorageBackend as S3Cls  # noqa: N813

        with patch("src.platform.storage.settings") as mock_settings:
            mock_settings.s3_endpoint_url = "http://localhost:9000"
            mock_settings.s3_access_key = "test-key"
            mock_settings.s3_secret_key = "test-secret"
            mock_settings.s3_region = "us-east-1"
            mock_settings.s3_bucket_prefix = "berengario-tenant-"

            with patch("boto3.client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client
                yield S3Cls, mock_client

    def _make_storage(self, s3_setup):
        """Create an S3StorageBackend from the fixture."""
        cls, _ = s3_setup
        return cls(
            endpoint_url="http://localhost:9000",
            access_key="test",
            secret_key="test",
            bucket_prefix="berengario-tenant-",
        )

    def test_bucket_name(self, s3_setup):
        """Test bucket name generation."""
        storage = self._make_storage(s3_setup)

        assert storage._bucket_name("acme") == "berengario-tenant-acme"
        assert (
            storage._bucket_name("imperial-dols") == "berengario-tenant-imperial-dols"
        )

    def test_put(self, s3_setup):
        """Test storing a file to S3."""
        _, mock_client = s3_setup
        storage = self._make_storage(s3_setup)

        result = storage.put("acme", "docs/test.pdf", b"pdf-data")

        mock_client.put_object.assert_called_once_with(
            Bucket="berengario-tenant-acme",
            Key="docs/test.pdf",
            Body=b"pdf-data",
        )
        assert result == "docs/test.pdf"

    def test_put_with_metadata(self, s3_setup):
        """Test storing with metadata."""
        _, mock_client = s3_setup
        storage = self._make_storage(s3_setup)

        storage.put("acme", "file.txt", b"data", metadata={"type": "document"})

        mock_client.put_object.assert_called_once_with(
            Bucket="berengario-tenant-acme",
            Key="file.txt",
            Body=b"data",
            Metadata={"type": "document"},
        )

    def test_get(self, s3_setup):
        """Test retrieving a file from S3."""
        _, mock_client = s3_setup
        storage = self._make_storage(s3_setup)

        mock_body = MagicMock()
        mock_body.read.return_value = b"file-content"
        mock_client.get_object.return_value = {"Body": mock_body}

        result = storage.get("acme", "file.txt")

        assert result == b"file-content"
        mock_client.get_object.assert_called_once_with(
            Bucket="berengario-tenant-acme",
            Key="file.txt",
        )

    def test_delete(self, s3_setup):
        """Test deleting a file from S3."""
        _, mock_client = s3_setup
        storage = self._make_storage(s3_setup)

        storage.delete("acme", "file.txt")

        mock_client.delete_object.assert_called_once_with(
            Bucket="berengario-tenant-acme",
            Key="file.txt",
        )

    def test_ensure_tenant_storage_creates_bucket(self, s3_setup):
        """Test creating a new S3 bucket for tenant."""
        _, mock_client = s3_setup
        storage = self._make_storage(s3_setup)

        mock_client.head_bucket.side_effect = Exception("Not found")

        storage.ensure_tenant_storage("acme")

        mock_client.create_bucket.assert_called_once_with(
            Bucket="berengario-tenant-acme"
        )


class TestCreateStorageBackend:
    """Tests for create_storage_backend factory."""

    def test_creates_local_backend_by_default(self):
        """Test factory creates LocalStorageBackend when storage_backend=local."""
        with patch("src.platform.storage.settings") as mock_settings:
            mock_settings.storage_backend = "local"
            mock_settings.multi_tenant = False

            backend = create_storage_backend()
            assert isinstance(backend, LocalStorageBackend)
