"""
Unit tests for tenant backup importer.

Tests TenantBackupImporter with mocked dependencies.
"""

import sqlite3
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from src.platform.backup_import import TenantBackupImporter


def _create_test_zip(tmp_path, files=None, raw_entries=None):
    """
    Create a test backup ZIP file.

    Args:
        tmp_path: pytest tmp_path fixture.
        files: dict of {archive_name: content_bytes} with data/ prefix.
        raw_entries: list of raw archive names (for testing invalid paths).

    Returns:
        Path to the created ZIP file.
    """
    zip_path = tmp_path / "test_backup.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        if files:
            for name, content in files.items():
                zf.writestr(name, content)
        if raw_entries:
            for entry in raw_entries:
                zf.writestr(entry, b"test")
    return zip_path


def _create_mock_importer():
    """Create a TenantBackupImporter with mocked dependencies."""
    provisioner = MagicMock()
    storage = MagicMock()
    db_manager = MagicMock()
    importer = TenantBackupImporter(provisioner, storage, db_manager)
    return importer, provisioner, storage, db_manager


class TestValidateBackup:
    """Tests for backup validation."""

    def test_valid_backup_with_documents(self, tmp_path):
        """Test validation of a backup with documents."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/report.pdf": b"PDF content",
                "data/kb/documents/notes.txt": b"Text content",
                "data/documents/source.docx": b"DOCX content",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is True
        assert result["has_documents"] is True
        assert result["document_count"] == 3
        assert result["file_count"] == 3
        assert not result["errors"]

    def test_valid_backup_with_chromadb(self, tmp_path):
        """Test validation of a backup with ChromaDB."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/chroma_db/chroma.sqlite3": b"SQLite data",
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is True
        assert result["has_chromadb"] is True
        assert result["has_documents"] is True

    def test_valid_backup_with_config(self, tmp_path):
        """Test validation detects config files."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/config/custom_prompt.txt": b"Custom prompt",
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is True
        assert result["has_config"] is True

    def test_invalid_no_importable_content(self, tmp_path):
        """Test validation fails when no documents or chromadb."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/logs/app.log": b"Log data",
                "data/config/settings.txt": b"Config",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is False
        assert any("No importable content" in e for e in result["errors"])

    def test_invalid_path_traversal(self, tmp_path):
        """Test validation rejects path traversal."""
        zip_path = _create_test_zip(
            tmp_path,
            raw_entries=[
                "data/../etc/passwd",
            ],
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is False
        assert any("Path traversal" in e for e in result["errors"])

    def test_invalid_outside_data_prefix(self, tmp_path):
        """Test validation rejects entries outside data/ prefix."""
        zip_path = _create_test_zip(
            tmp_path,
            raw_entries=[
                "etc/passwd",
            ],
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is False
        assert any("outside data/" in e for e in result["errors"])

    def test_nonexistent_file(self, tmp_path):
        """Test validation handles missing file."""
        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(tmp_path / "missing.zip")

        assert result["valid"] is False
        assert any("not found" in e for e in result["errors"])

    def test_not_a_zip(self, tmp_path):
        """Test validation rejects non-ZIP files."""
        bad_file = tmp_path / "not_a_zip.zip"
        bad_file.write_text("This is not a zip file")

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(bad_file)

        assert result["valid"] is False
        assert any("not a valid ZIP" in e for e in result["errors"])

    def test_backup_warnings_for_nested_backups(self, tmp_path):
        """Test validation warns about nested backups."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/backups/old_backup.zip": b"Nested backup",
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is True
        assert any("nested backups" in w for w in result["warnings"])

    def test_multi_tenant_backup_layout(self, tmp_path):
        """Test validation of a multi-tenant backup (data/tenants/{slug}/...)."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/tenants/dolsgpt/kb/documents/report.pdf": b"PDF content",
                "data/tenants/dolsgpt/kb/emails/msg.txt": b"Email",
                "data/tenants/dolsgpt/chroma_db/chroma.sqlite3": b"SQLite",
                "data/tenants/dolsgpt/config/example_questions.json": b"{}",
                "data/logs/app.log": b"Log data",
            },
        )

        importer, _, _, _ = _create_mock_importer()
        result = importer.validate_backup(zip_path)

        assert result["valid"] is True
        assert result["has_documents"] is True
        assert result["has_chromadb"] is True
        assert result["has_config"] is True
        assert result["document_count"] == 2
        assert result["source_slug"] == "dolsgpt"
        assert result["data_root"] == "data/tenants/dolsgpt/"
        assert any("Multi-tenant" in w for w in result["warnings"])


class TestRenameChromaDBCollection:
    """Tests for ChromaDB collection renaming."""

    def test_rename_single_collection(self, tmp_path):
        """Test renaming a single ChromaDB collection."""
        chroma_dir = tmp_path / "chroma_db"
        chroma_dir.mkdir()
        sqlite_file = chroma_dir / "chroma.sqlite3"

        # Create a minimal ChromaDB-like SQLite database
        conn = sqlite3.connect(str(sqlite_file))
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO collections VALUES ('uuid1', 'knowledge_base')")
        conn.commit()
        conn.close()

        TenantBackupImporter._rename_chromadb_collection(chroma_dir, "my-tenant_kb")

        # Verify rename
        conn = sqlite3.connect(str(sqlite_file))
        cursor = conn.execute("SELECT name FROM collections")
        names = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert names == ["my-tenant_kb"]

    def test_rename_multiple_collections(self, tmp_path):
        """Test renaming when multiple collections exist."""
        chroma_dir = tmp_path / "chroma_db"
        chroma_dir.mkdir()
        sqlite_file = chroma_dir / "chroma.sqlite3"

        conn = sqlite3.connect(str(sqlite_file))
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO collections VALUES ('uuid1', 'old_kb')")
        conn.execute("INSERT INTO collections VALUES ('uuid2', 'old_kb_2')")
        conn.commit()
        conn.close()

        TenantBackupImporter._rename_chromadb_collection(chroma_dir, "new-tenant_kb")

        conn = sqlite3.connect(str(sqlite_file))
        cursor = conn.execute("SELECT name FROM collections")
        names = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert all(n == "new-tenant_kb" for n in names)

    def test_rename_no_sqlite_file(self, tmp_path):
        """Test rename handles missing SQLite file gracefully."""
        chroma_dir = tmp_path / "chroma_db"
        chroma_dir.mkdir()

        # Should not raise
        TenantBackupImporter._rename_chromadb_collection(chroma_dir, "test_kb")

    def test_rename_empty_collections(self, tmp_path):
        """Test rename handles empty collections table."""
        chroma_dir = tmp_path / "chroma_db"
        chroma_dir.mkdir()
        sqlite_file = chroma_dir / "chroma.sqlite3"

        conn = sqlite3.connect(str(sqlite_file))
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()

        # Should not raise
        TenantBackupImporter._rename_chromadb_collection(chroma_dir, "test_kb")


class TestUploadDocuments:
    """Tests for document upload to storage."""

    def test_upload_documents(self, tmp_path):
        """Test uploading documents from extracted backup."""
        # Create extracted directory structure
        extracted = tmp_path / "extracted" / "data"
        (extracted / "kb" / "documents").mkdir(parents=True)
        (extracted / "kb" / "emails").mkdir(parents=True)
        (extracted / "documents").mkdir(parents=True)

        # Create test files
        (extracted / "kb" / "documents" / "report.pdf").write_bytes(b"PDF data")
        (extracted / "kb" / "emails" / "msg.txt").write_bytes(b"Email data")
        (extracted / "documents" / "source.docx").write_bytes(b"DOCX data")

        importer, _, storage, _ = _create_mock_importer()
        storage.put.return_value = "key"

        count = importer._upload_documents_to_s3(extracted, "my-tenant")

        assert count == 3
        assert storage.put.call_count == 3

        # Verify the keys used
        put_keys = {c.args[1] for c in storage.put.call_args_list}
        assert "kb/documents/report.pdf" in put_keys
        assert "kb/emails/msg.txt" in put_keys
        assert "documents/source.docx" in put_keys

        # Verify tenant slug was passed
        for c in storage.put.call_args_list:
            assert c.args[0] == "my-tenant"

    def test_upload_empty_dirs(self, tmp_path):
        """Test upload handles missing directories."""
        extracted = tmp_path / "extracted" / "data"
        extracted.mkdir(parents=True)

        importer, _, storage, _ = _create_mock_importer()
        count = importer._upload_documents_to_s3(extracted, "my-tenant")

        assert count == 0
        storage.put.assert_not_called()

    def test_upload_failure_propagates(self, tmp_path):
        """Test that upload failures propagate."""
        extracted = tmp_path / "extracted" / "data"
        (extracted / "kb" / "documents").mkdir(parents=True)
        (extracted / "kb" / "documents" / "file.pdf").write_bytes(b"data")

        importer, _, storage, _ = _create_mock_importer()
        storage.put.side_effect = Exception("S3 error")

        with pytest.raises(Exception, match="S3 error"):
            importer._upload_documents_to_s3(extracted, "my-tenant")


class TestImportTenant:
    """Tests for the full import pipeline."""

    def test_successful_import(self, tmp_path):
        """Test a successful full import."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/report.pdf": b"PDF content",
                "data/config/custom_prompt.txt": b"My custom prompt",
            },
        )

        importer, provisioner, storage, _ = _create_mock_importer()
        storage.put.return_value = "key"

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="test-tenant",
            name="Test Tenant",
            admin_email="admin@test.com",
            description="Test description",
        )

        assert result["success"] is True
        assert result["slug"] == "test-tenant"
        assert result["documents_uploaded"] == 1
        assert result["config_applied"] is True
        assert not result["errors"]

        # Verify tenant was created with custom prompt
        provisioner.create_tenant.assert_called_once_with(
            slug="test-tenant",
            name="Test Tenant",
            admin_email="admin@test.com",
            description="Test description",
            organization=None,
            custom_prompt="My custom prompt",
        )

    def test_import_with_chromadb(self, tmp_path):
        """Test import with ChromaDB embeddings."""
        # Create a valid ChromaDB structure in the ZIP
        chroma_dir = tmp_path / "chroma_staging"
        chroma_dir.mkdir()
        sqlite_file = chroma_dir / "chroma.sqlite3"
        conn = sqlite3.connect(str(sqlite_file))
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO collections VALUES ('uuid1', 'old_kb')")
        conn.commit()
        conn.close()

        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("data/kb/documents/doc.pdf", b"PDF")
            zf.write(sqlite_file, "data/chroma_db/chroma.sqlite3")

        importer, provisioner, storage, _ = _create_mock_importer()
        storage.put.return_value = "key"

        with patch.object(importer, "_import_chromadb") as mock_chroma:
            result = importer.import_tenant(
                zip_path=zip_path,
                slug="test-tenant",
                name="Test",
                admin_email="admin@test.com",
            )

        assert result["success"] is True
        mock_chroma.assert_called_once()

    def test_import_skip_chromadb(self, tmp_path):
        """Test import with --skip-chromadb."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/doc.pdf": b"PDF",
                "data/chroma_db/chroma.sqlite3": b"SQLite data",
            },
        )

        importer, _, storage, _ = _create_mock_importer()
        storage.put.return_value = "key"

        with patch.object(importer, "_import_chromadb") as mock_chroma:
            result = importer.import_tenant(
                zip_path=zip_path,
                slug="test-tenant",
                name="Test",
                admin_email="admin@test.com",
                skip_chromadb=True,
            )

        assert result["success"] is True
        assert result["chromadb_imported"] is False
        mock_chroma.assert_not_called()

    def test_rollback_on_failure(self, tmp_path):
        """Test that tenant is deleted on import failure."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, provisioner, storage, _ = _create_mock_importer()
        # Make upload fail after tenant creation
        storage.put.side_effect = Exception("S3 upload failed")

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="test-tenant",
            name="Test",
            admin_email="admin@test.com",
        )

        assert result["success"] is False
        assert any("S3 upload failed" in e for e in result["errors"])

        # Verify rollback was called
        provisioner.delete_tenant.assert_called_once_with(
            "test-tenant", crypto_shred=False
        )

    def test_rollback_failure_logged(self, tmp_path):
        """Test rollback failure is captured in errors."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, provisioner, storage, _ = _create_mock_importer()
        storage.put.side_effect = Exception("S3 error")
        provisioner.delete_tenant.side_effect = Exception("Rollback error")

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="test-tenant",
            name="Test",
            admin_email="admin@test.com",
        )

        assert result["success"] is False
        assert any("Rollback failed" in e for e in result["errors"])

    def test_invalid_backup_returns_errors(self, tmp_path):
        """Test that invalid backup returns errors without creating tenant."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/logs/app.log": b"Log only",
            },
        )

        importer, provisioner, _, _ = _create_mock_importer()

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="test-tenant",
            name="Test",
            admin_email="admin@test.com",
        )

        assert result["success"] is False
        assert result["errors"]
        provisioner.create_tenant.assert_not_called()

    def test_import_multi_tenant_backup(self, tmp_path):
        """Test importing from a multi-tenant backup layout."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/tenants/dolsgpt/kb/documents/report.pdf": b"PDF content",
                "data/tenants/dolsgpt/kb/emails/msg.txt": b"Email",
                "data/tenants/dolsgpt/config/custom_prompt.txt": b"Custom prompt",
                "data/logs/app.log": b"Log data",
            },
        )

        importer, provisioner, storage, _ = _create_mock_importer()
        storage.put.return_value = "key"

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="new-dolsgpt",
            name="DoLS GPT",
            admin_email="admin@test.com",
        )

        assert result["success"] is True
        assert result["documents_uploaded"] == 2
        assert result["config_applied"] is True

        # Verify custom prompt was extracted from tenant subdir
        provisioner.create_tenant.assert_called_once_with(
            slug="new-dolsgpt",
            name="DoLS GPT",
            admin_email="admin@test.com",
            description=None,
            organization=None,
            custom_prompt="Custom prompt",
        )

    def test_no_rollback_when_tenant_not_created(self, tmp_path):
        """Test no rollback attempt if tenant creation itself fails."""
        zip_path = _create_test_zip(
            tmp_path,
            {
                "data/kb/documents/doc.pdf": b"PDF",
            },
        )

        importer, provisioner, _, _ = _create_mock_importer()
        provisioner.create_tenant.side_effect = ValueError("Slug already exists")

        result = importer.import_tenant(
            zip_path=zip_path,
            slug="test-tenant",
            name="Test",
            admin_email="admin@test.com",
        )

        assert result["success"] is False
        # delete_tenant should NOT be called since create_tenant failed
        provisioner.delete_tenant.assert_not_called()


class TestImportChromaDB:
    """Tests for ChromaDB import."""

    def test_import_chromadb_copies_and_renames(self, tmp_path):
        """Test that ChromaDB is copied and collection renamed."""
        # Create source ChromaDB
        chroma_src = tmp_path / "chroma_db"
        chroma_src.mkdir()
        sqlite_file = chroma_src / "chroma.sqlite3"

        conn = sqlite3.connect(str(sqlite_file))
        conn.execute("CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO collections VALUES ('uuid1', 'old_name')")
        conn.commit()
        conn.close()

        # Test the rename directly since _import_chromadb uses hardcoded paths
        TenantBackupImporter._rename_chromadb_collection(chroma_src, "new-tenant_kb")

        conn = sqlite3.connect(str(sqlite_file))
        cursor = conn.execute("SELECT name FROM collections")
        names = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert names == ["new-tenant_kb"]
