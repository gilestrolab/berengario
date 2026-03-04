"""
Backup Manager for creating and managing data backups.

Handles creating zip archives of the data directory, sending download links,
and restoring from backup archives.
"""

import asyncio
import logging
import shutil
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages data backups for the Berengario system.

    Creates zip archives of the data directory and provides download links.
    """

    def __init__(
        self, data_dir: Optional[Path] = None, backup_dir: Optional[Path] = None
    ):
        """
        Initialize the Backup Manager.

        Args:
            data_dir: Path to the data directory to backup (default: data/).
            backup_dir: Path to store backup files (default: data_dir/backups).
        """
        self.data_dir = data_dir or Path("data")
        self.backup_dir = backup_dir or (self.data_dir / "backups")

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"BackupManager initialized: data={self.data_dir}, backups={self.backup_dir}"
        )

    def _get_backup_filename(self) -> str:
        """
        Generate a timestamped backup filename.

        Returns:
            Backup filename with timestamp.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Convert instance name to safe filename (lowercase, replace spaces with underscores)
        instance_name = (
            settings.instance_name.lower().replace(" ", "_").replace("-", "_")
        )
        return f"{instance_name}_backup_{timestamp}.zip"

    async def create_backup(self, exclude_backups: bool = True) -> Path:
        """
        Create a zip backup of the data directory.

        Args:
            exclude_backups: If True, exclude the backups directory itself.

        Returns:
            Path to the created backup file.

        Raises:
            Exception: If backup creation fails.
        """
        try:
            backup_filename = self._get_backup_filename()
            backup_path = self.backup_dir / backup_filename

            logger.info(f"Starting backup creation: {backup_filename}")

            # Run the zip operation in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._create_zip_archive, backup_path, exclude_backups
            )

            logger.info(
                f"Backup created successfully: {backup_path} ({backup_path.stat().st_size / (1024*1024):.2f} MB)"
            )
            return backup_path

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise

    def _create_zip_archive(self, backup_path: Path, exclude_backups: bool) -> None:
        """
        Create a zip archive of the data directory (blocking operation).

        Args:
            backup_path: Path where the backup file should be created.
            exclude_backups: If True, exclude the backups directory.

        Raises:
            Exception: If zip creation fails.
        """
        try:
            # Create zip file
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Walk through the data directory
                for item in self.data_dir.rglob("*"):
                    # Skip if it's the backup file itself
                    if item == backup_path:
                        continue

                    # Skip backups directory if requested
                    if exclude_backups:
                        # Check if this path is inside the backups directory
                        try:
                            item.relative_to(self.backup_dir)
                            continue  # Skip files in backups directory
                        except ValueError:
                            pass  # Not in backups directory, include it

                    # Skip hidden files and temp files
                    if item.name.startswith(".") or item.name.endswith(".tmp"):
                        continue

                    # Add file or directory to zip
                    if item.is_file():
                        # Calculate relative path from data directory
                        arcname = item.relative_to(self.data_dir.parent)
                        zipf.write(item, arcname)

        except Exception as e:
            logger.error(f"Error creating zip archive: {e}")
            # Clean up partial backup file
            if backup_path.exists():
                backup_path.unlink()
            raise

    def get_backup_path(self, filename: str) -> Optional[Path]:
        """
        Get the full path to a backup file.

        Args:
            filename: Name of the backup file.

        Returns:
            Path to the backup file if it exists, None otherwise.
        """
        backup_path = self.backup_dir / filename
        if backup_path.exists() and backup_path.is_file():
            return backup_path
        return None

    def list_backups(self) -> list[dict]:
        """
        List all available backup files.

        Returns:
            List of dictionaries containing backup file info.
        """
        try:
            backups = []
            for backup_file in sorted(self.backup_dir.glob("*.zip"), reverse=True):
                stat = backup_file.stat()
                backups.append(
                    {
                        "filename": backup_file.name,
                        "size_bytes": stat.st_size,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    }
                )
            return backups
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            return []

    def cleanup_old_backups(self, max_age_days: int = 7, max_count: int = 5) -> int:
        """
        Clean up old backup files.

        Args:
            max_age_days: Delete backups older than this many days.
            max_count: Keep at most this many recent backups.

        Returns:
            Number of backups deleted.
        """
        try:
            deleted = 0
            cutoff_time = datetime.now() - timedelta(days=max_age_days)

            # Get all backups sorted by modification time (newest first)
            backups = sorted(
                self.backup_dir.glob("*.zip"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for i, backup_file in enumerate(backups):
                stat = backup_file.stat()
                created = datetime.fromtimestamp(stat.st_ctime)

                # Delete if older than max_age_days OR beyond max_count
                if created < cutoff_time or i >= max_count:
                    logger.info(f"Deleting old backup: {backup_file.name}")
                    backup_file.unlink()
                    deleted += 1

            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old backup(s)")

            return deleted

        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
            return 0

    def delete_backup(self, filename: str) -> bool:
        """
        Delete a specific backup file.

        Args:
            filename: Name of the backup file to delete.

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            backup_path = self.backup_dir / filename
            if backup_path.exists() and backup_path.is_file():
                backup_path.unlink()
                logger.info(f"Deleted backup: {filename}")
                return True
            else:
                logger.warning(f"Backup file not found: {filename}")
                return False
        except Exception as e:
            logger.error(f"Error deleting backup {filename}: {e}")
            return False

    # Maximum uncompressed backup size (2 GB)
    MAX_RESTORE_SIZE = 2 * 1024 * 1024 * 1024

    def validate_backup(self, zip_path: Path) -> dict:
        """
        Validate a backup ZIP file for safety before restoring.

        Checks for path traversal, invalid entries, and ZIP bombs.

        Args:
            zip_path: Path to the ZIP file to validate.

        Returns:
            dict with keys: valid (bool), errors (list), warnings (list),
            file_count (int), total_size (int), top_level_dirs (list).
        """
        errors = []
        warnings = []
        file_count = 0
        total_size = 0
        top_level_dirs = set()

        if not zip_path.exists():
            return {
                "valid": False,
                "errors": [f"File not found: {zip_path}"],
                "warnings": [],
                "file_count": 0,
                "total_size": 0,
                "top_level_dirs": [],
            }

        if not zipfile.is_zipfile(zip_path):
            return {
                "valid": False,
                "errors": ["File is not a valid ZIP archive"],
                "warnings": [],
                "file_count": 0,
                "total_size": 0,
                "top_level_dirs": [],
            }

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    name = info.filename

                    # Reject path traversal
                    if ".." in name or name.startswith("/"):
                        errors.append(f"Path traversal detected: {name}")
                        continue

                    # All entries must start with data/
                    if not name.startswith("data/"):
                        errors.append(f"Entry outside data/ directory: {name}")
                        continue

                    # Reject entries targeting data/backups/
                    if name.startswith("data/backups/") or name == "data/backups":
                        warnings.append(f"Skipping backup directory entry: {name}")
                        continue

                    if not info.is_dir():
                        file_count += 1
                        total_size += info.file_size

                    # Track top-level directories under data/
                    parts = name.split("/")
                    if len(parts) > 1 and parts[1]:
                        top_level_dirs.add(parts[1])

                # Check total uncompressed size
                if total_size > self.MAX_RESTORE_SIZE:
                    errors.append(
                        f"Uncompressed size ({total_size / (1024**3):.2f} GB) "
                        f"exceeds maximum ({self.MAX_RESTORE_SIZE / (1024**3):.0f} GB)"
                    )

        except zipfile.BadZipFile:
            errors.append("Corrupted ZIP file")
        except Exception as e:
            errors.append(f"Error reading ZIP: {e}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "file_count": file_count,
            "total_size": total_size,
            "top_level_dirs": sorted(top_level_dirs),
        }

    def _restore_from_zip(
        self, zip_path: Path, create_pre_restore: bool = True
    ) -> dict:
        """
        Restore data from a backup ZIP file (blocking operation).

        Extracts the backup to a temp directory, then atomically swaps
        each subdirectory into place. Rolls back on failure.

        Args:
            zip_path: Path to the backup ZIP file.
            create_pre_restore: If True, create a safety backup before restoring.

        Returns:
            dict with keys: success (bool), pre_restore_backup (str or None),
            files_restored (int), errors (list).
        """
        errors = []
        pre_restore_backup = None
        files_restored = 0
        restore_id = uuid.uuid4().hex[:8]
        temp_dir = self.data_dir / f"_restore_temp_{restore_id}"
        swapped = []  # Track (original_path, old_backup_path) for rollback

        try:
            # Step 1: Validate
            report = self.validate_backup(zip_path)
            if not report["valid"]:
                return {
                    "success": False,
                    "pre_restore_backup": None,
                    "files_restored": 0,
                    "errors": report["errors"],
                }

            # Step 2: Create pre-restore safety backup
            if create_pre_restore:
                logger.info("Creating pre-restore safety backup...")
                safety_filename = (
                    f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                )
                safety_path = self.backup_dir / safety_filename
                self._create_zip_archive(safety_path, exclude_backups=True)
                pre_restore_backup = safety_filename
                logger.info(f"Pre-restore backup created: {safety_filename}")

            # Step 3: Extract ZIP to temp directory
            temp_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    name = info.filename
                    # Skip path traversal, non-data entries, and backup entries
                    if ".." in name or name.startswith("/"):
                        continue
                    if not name.startswith("data/"):
                        continue
                    if name.startswith("data/backups/") or name == "data/backups":
                        continue

                    # Extract to temp, stripping the leading "data/" prefix
                    # so temp_dir contains the subdirs directly
                    relative = name[len("data/") :]
                    if not relative:
                        continue

                    target = temp_dir / relative
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        files_restored += 1

            # Step 4: Swap directories atomically
            # Identify top-level subdirs extracted to temp_dir
            extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
            extracted_files = [f for f in temp_dir.iterdir() if f.is_file()]

            for extracted_subdir in extracted_dirs:
                subdir_name = extracted_subdir.name
                original = self.data_dir / subdir_name
                old_backup = self.data_dir / f"_restore_old_{restore_id}_{subdir_name}"

                if original.exists():
                    # Rename current aside
                    original.rename(old_backup)
                    swapped.append((original, old_backup))

                # Move extracted into place
                extracted_subdir.rename(original)

            # Handle top-level files (e.g., data/message_tracker.db)
            for extracted_file in extracted_files:
                file_name = extracted_file.name
                original = self.data_dir / file_name
                old_backup = self.data_dir / f"_restore_old_{restore_id}_{file_name}"

                if original.exists():
                    original.rename(old_backup)
                    swapped.append((original, old_backup))

                extracted_file.rename(original)

            logger.info(
                f"Restore completed: {files_restored} files restored "
                f"from {len(report['top_level_dirs'])} directories"
            )

        except Exception as e:
            logger.error(f"Restore failed, rolling back: {e}")
            errors.append(str(e))

            # Rollback: move originals back
            for original_path, old_path in reversed(swapped):
                try:
                    # Remove the restored version if it exists
                    if original_path.exists():
                        if original_path.is_dir():
                            shutil.rmtree(original_path)
                        else:
                            original_path.unlink()
                    # Restore original
                    old_path.rename(original_path)
                    logger.info(f"Rolled back: {original_path.name}")
                except Exception as rollback_err:
                    logger.error(
                        f"Rollback failed for {original_path.name}: {rollback_err}"
                    )
                    errors.append(f"Rollback failed for {original_path.name}")

        finally:
            # Cleanup temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Cleanup old backup directories (only on success)
            if not errors:
                for path in self.data_dir.iterdir():
                    if path.name.startswith(f"_restore_old_{restore_id}"):
                        try:
                            if path.is_dir():
                                shutil.rmtree(path)
                            else:
                                path.unlink()
                        except Exception:
                            pass

        return {
            "success": len(errors) == 0,
            "pre_restore_backup": pre_restore_backup,
            "files_restored": files_restored,
            "errors": errors,
        }

    async def restore_backup(
        self, zip_path: Path, create_pre_restore: bool = True
    ) -> dict:
        """
        Restore data from a backup ZIP file (async wrapper).

        Args:
            zip_path: Path to the backup ZIP file.
            create_pre_restore: If True, create a safety backup before restoring.

        Returns:
            dict with restore result details.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._restore_from_zip, zip_path, create_pre_restore
        )
