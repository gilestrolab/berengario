"""
Tests for BackupManager validate and restore functionality.

Uses tmp_path fixture for isolated filesystem operations.
"""

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.api.admin.backup_manager import BackupManager


@pytest.fixture
def backup_env(tmp_path):
    """
    Create a realistic data directory structure for backup tests.

    Returns:
        tuple: (BackupManager instance, data_dir Path)
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create sample subdirectories and files
    (data_dir / "chroma_db").mkdir()
    (data_dir / "chroma_db" / "index.bin").write_bytes(b"chroma_data_here")

    (data_dir / "config").mkdir()
    (data_dir / "config" / "custom_prompt.txt").write_text("Be helpful.")

    (data_dir / "documents").mkdir()
    (data_dir / "documents" / "guide.pdf").write_bytes(b"%PDF-fake")

    (data_dir / "logs").mkdir()
    (data_dir / "logs" / "app.log").write_text("log line 1\nlog line 2\n")

    # A top-level file in data/
    (data_dir / "message_tracker.db").write_bytes(b"sqlite_db_content")

    backup_dir = data_dir / "backups"
    backup_dir.mkdir()

    manager = BackupManager(data_dir=data_dir, backup_dir=backup_dir)
    return manager, data_dir


def _create_test_zip(zip_path: Path, entries: dict[str, bytes | None]):
    """
    Helper to create a ZIP file with given entries.

    Args:
        zip_path: Where to create the ZIP.
        entries: Mapping of archive name -> content (None for directories).
    """
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in entries.items():
            if content is None:
                # Directory entry
                zf.mkdir(name)
            else:
                zf.writestr(name, content)


# ============================================================================
# Validation tests
# ============================================================================


class TestValidateBackup:
    """Tests for BackupManager.validate_backup()."""

    def test_valid_backup(self, backup_env):
        """A well-formed backup passes validation."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/chroma_db/index.bin": b"data",
                "data/config/prompt.txt": b"prompt",
                "data/documents/doc.pdf": b"%PDF",
            },
        )

        result = manager.validate_backup(zip_path)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["file_count"] == 3
        assert set(result["top_level_dirs"]) == {"chroma_db", "config", "documents"}

    def test_file_not_found(self, backup_env):
        """Nonexistent file returns invalid."""
        manager, data_dir = backup_env
        result = manager.validate_backup(data_dir / "nonexistent.zip")
        assert result["valid"] is False
        assert any("not found" in e for e in result["errors"])

    def test_not_a_zip(self, backup_env):
        """Non-ZIP file returns invalid."""
        manager, data_dir = backup_env
        fake = data_dir / "backups" / "fake.zip"
        fake.write_text("this is not a zip")
        result = manager.validate_backup(fake)
        assert result["valid"] is False
        assert any("not a valid ZIP" in e for e in result["errors"])

    def test_path_traversal_dotdot(self, backup_env):
        """Entries with '..' are rejected."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "evil.zip"
        _create_test_zip(
            zip_path,
            {
                "data/../etc/passwd": b"root:x:0:0",
                "data/config/ok.txt": b"fine",
            },
        )
        result = manager.validate_backup(zip_path)
        assert result["valid"] is False
        assert any("Path traversal" in e for e in result["errors"])

    def test_absolute_path_rejected(self, backup_env):
        """Entries with absolute paths are rejected."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "abs.zip"
        _create_test_zip(
            zip_path,
            {
                "/etc/passwd": b"root:x:0:0",
            },
        )
        result = manager.validate_backup(zip_path)
        assert result["valid"] is False
        assert any("Path traversal" in e for e in result["errors"])

    def test_missing_data_prefix(self, backup_env):
        """Entries not under data/ are rejected."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "noprefix.zip"
        _create_test_zip(
            zip_path,
            {
                "src/main.py": b"print('hi')",
                "config.yaml": b"key: val",
            },
        )
        result = manager.validate_backup(zip_path)
        assert result["valid"] is False
        assert len(result["errors"]) == 2
        assert all("outside data/" in e for e in result["errors"])

    def test_backups_dir_warned(self, backup_env):
        """Entries targeting data/backups/ generate warnings, not errors."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "withbackups.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/ok.txt": b"fine",
                "data/backups/old.zip": b"zipdata",
            },
        )
        result = manager.validate_backup(zip_path)
        assert result["valid"] is True  # Warnings don't make it invalid
        assert len(result["warnings"]) == 1
        assert result["file_count"] == 1  # Only the config file counted

    def test_zip_bomb_rejected(self, backup_env):
        """Backup exceeding max uncompressed size is rejected."""
        manager, data_dir = backup_env
        manager.MAX_RESTORE_SIZE = 1000  # Set low limit for testing

        zip_path = data_dir / "backups" / "bomb.zip"
        _create_test_zip(
            zip_path,
            {
                "data/big_file.bin": b"x" * 1001,
            },
        )
        result = manager.validate_backup(zip_path)
        assert result["valid"] is False
        assert any("exceeds maximum" in e for e in result["errors"])

    def test_corrupted_zip(self, backup_env):
        """Corrupted ZIP file returns invalid."""
        manager, data_dir = backup_env
        zip_path = data_dir / "backups" / "corrupt.zip"
        # Write partial ZIP header to make is_zipfile True but content corrupt
        with open(zip_path, "wb") as f:
            f.write(b"PK\x03\x04" + b"\x00" * 100)
        result = manager.validate_backup(zip_path)
        assert result["valid"] is False


# ============================================================================
# Restore tests
# ============================================================================


class TestRestoreBackup:
    """Tests for BackupManager._restore_from_zip()."""

    def test_restore_replaces_data(self, backup_env):
        """Restore replaces existing data with backup contents."""
        manager, data_dir = backup_env

        # Create a backup with different content
        zip_path = data_dir / "backups" / "restore_test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"New prompt content",
                "data/chroma_db/index.bin": b"new_chroma_data",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)

        assert result["success"] is True
        assert result["files_restored"] == 2
        assert result["errors"] == []

        # Verify content was replaced
        assert (
            data_dir / "config" / "custom_prompt.txt"
        ).read_text() == "New prompt content"
        assert (data_dir / "chroma_db" / "index.bin").read_bytes() == b"new_chroma_data"

    def test_pre_restore_backup_created(self, backup_env):
        """Pre-restore safety backup is created when requested."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "restore_test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"Updated",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=True)

        assert result["success"] is True
        assert result["pre_restore_backup"] is not None
        assert result["pre_restore_backup"].startswith("pre_restore_")

        # Verify the safety backup exists
        safety_path = data_dir / "backups" / result["pre_restore_backup"]
        assert safety_path.exists()

    def test_directories_not_in_backup_preserved(self, backup_env):
        """Directories not present in the backup remain untouched."""
        manager, data_dir = backup_env

        # Backup only touches config, not documents or logs
        zip_path = data_dir / "backups" / "partial.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"Updated",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)
        assert result["success"] is True

        # Documents and logs should be unchanged
        assert (data_dir / "documents" / "guide.pdf").read_bytes() == b"%PDF-fake"
        assert (data_dir / "logs" / "app.log").exists()

    def test_new_directory_created(self, backup_env):
        """Restore creates directories that didn't exist before."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "newdir.zip"
        _create_test_zip(
            zip_path,
            {
                "data/new_stuff/file.txt": b"hello world",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)
        assert result["success"] is True
        assert (data_dir / "new_stuff" / "file.txt").read_text() == "hello world"

    def test_top_level_file_restored(self, backup_env):
        """Top-level files in data/ (e.g., message_tracker.db) are restored."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "dbfile.zip"
        _create_test_zip(
            zip_path,
            {
                "data/message_tracker.db": b"new_db_content",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)
        assert result["success"] is True
        assert (data_dir / "message_tracker.db").read_bytes() == b"new_db_content"

    def test_rollback_on_failure(self, backup_env):
        """On failure, original data is rolled back."""
        manager, data_dir = backup_env

        # Save original content
        original_prompt = (data_dir / "config" / "custom_prompt.txt").read_text()

        zip_path = data_dir / "backups" / "fail_test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"This will be rolled back",
                "data/chroma_db/index.bin": b"also_rolled_back",
            },
        )

        # Patch rename to fail only during the swap phase (not during rollback)
        original_rename = Path.rename
        call_count = 0
        fail_active = True

        def failing_rename(self_path, target):
            nonlocal call_count, fail_active
            call_count += 1
            # Fail on the 4th rename (after first dir swap succeeds)
            # Then allow rollback renames to work
            if call_count == 4 and fail_active:
                fail_active = False  # Disable for rollback
                raise OSError("Simulated disk failure")
            return original_rename(self_path, target)

        with patch.object(Path, "rename", failing_rename):
            result = manager._restore_from_zip(zip_path, create_pre_restore=False)

        assert result["success"] is False
        assert len(result["errors"]) > 0

        # Original config should be restored (rolled back)
        assert (
            data_dir / "config" / "custom_prompt.txt"
        ).read_text() == original_prompt

    def test_temp_dirs_cleaned_up(self, backup_env):
        """Temp directories are cleaned up after restore (success or failure)."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "cleanup_test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"Updated",
            },
        )

        manager._restore_from_zip(zip_path, create_pre_restore=False)

        # No temp or old dirs should remain
        remaining = [
            p.name for p in data_dir.iterdir() if p.name.startswith("_restore_")
        ]
        assert remaining == []

    def test_backups_dir_entries_skipped(self, backup_env):
        """Entries targeting data/backups/ are skipped during restore."""
        manager, data_dir = backup_env

        # Place a marker in backups dir
        marker = data_dir / "backups" / "keep_me.txt"
        marker.write_text("important")

        zip_path = data_dir / "backups" / "with_backups.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"Updated",
                "data/backups/injected.zip": b"bad_backup",
            },
        )

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)
        assert result["success"] is True
        # The marker should still exist, and the injected backup should NOT
        assert marker.exists()
        assert not (data_dir / "backups" / "injected.zip").exists()

    def test_invalid_backup_returns_errors(self, backup_env):
        """Restoring from an invalid backup returns errors without modifying data."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "invalid.zip"
        _create_test_zip(
            zip_path,
            {
                "src/evil.py": b"import os; os.system('rm -rf /')",
            },
        )

        original_prompt = (data_dir / "config" / "custom_prompt.txt").read_text()

        result = manager._restore_from_zip(zip_path, create_pre_restore=False)
        assert result["success"] is False
        assert len(result["errors"]) > 0

        # Data unchanged
        assert (
            data_dir / "config" / "custom_prompt.txt"
        ).read_text() == original_prompt


class TestRestoreBackupAsync:
    """Tests for the async restore_backup() wrapper."""

    @pytest.mark.asyncio
    async def test_async_restore(self, backup_env):
        """Async wrapper delegates to _restore_from_zip correctly."""
        manager, data_dir = backup_env

        zip_path = data_dir / "backups" / "async_test.zip"
        _create_test_zip(
            zip_path,
            {
                "data/config/custom_prompt.txt": b"Async restored",
            },
        )

        result = await manager.restore_backup(zip_path, create_pre_restore=False)
        assert result["success"] is True
        assert (
            data_dir / "config" / "custom_prompt.txt"
        ).read_text() == "Async restored"
