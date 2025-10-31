"""
Backup Manager for creating and managing data backups.

Handles creating zip archives of the data directory and sending download links.
"""

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BackupManager:
    """
    Manages data backups for the RAGInbox system.

    Creates zip archives of the data directory and provides download links.
    """

    def __init__(self, data_dir: Optional[Path] = None, backup_dir: Optional[Path] = None):
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

        logger.info(f"BackupManager initialized: data={self.data_dir}, backups={self.backup_dir}")

    def _get_backup_filename(self) -> str:
        """
        Generate a timestamped backup filename.

        Returns:
            Backup filename with timestamp.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"raginbox_backup_{timestamp}.zip"

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
                None,
                self._create_zip_archive,
                backup_path,
                exclude_backups
            )

            logger.info(f"Backup created successfully: {backup_path} ({backup_path.stat().st_size / (1024*1024):.2f} MB)")
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
            # Create a temporary directory for the zip
            temp_backup = backup_path.with_suffix('.tmp')

            # Define ignore function
            def ignore_patterns(directory, files):
                ignored = []
                if exclude_backups and Path(directory) == self.data_dir:
                    # Exclude backups directory and temp files
                    ignored.extend([
                        f for f in files
                        if f == 'backups' or f.startswith('.') or f.endswith('.tmp')
                    ])
                elif Path(directory).name == 'backups':
                    # Skip entire backups directory
                    ignored.extend(files)
                return ignored

            # Create the zip archive
            shutil.make_archive(
                str(temp_backup.with_suffix('')),
                'zip',
                root_dir=self.data_dir.parent,
                base_dir=self.data_dir.name,
                ignore=ignore_patterns
            )

            # Rename temp file to final name
            temp_zip = temp_backup.with_suffix('.zip')
            temp_zip.rename(backup_path)

        except Exception as e:
            logger.error(f"Error creating zip archive: {e}")
            # Clean up temp files
            if temp_backup.exists():
                temp_backup.unlink()
            temp_zip = temp_backup.with_suffix('.zip')
            if temp_zip.exists():
                temp_zip.unlink()
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
                backups.append({
                    "filename": backup_file.name,
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                })
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
                reverse=True
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
