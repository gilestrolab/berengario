"""
Backup CLI commands.

Manages system backups (create, list, delete, cleanup, restore).
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import typer

from src.cli.utils import (
    confirm_destructive,
    console,
    create_progress,
    create_table,
    format_bytes,
    format_count,
    handle_error,
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_success,
    print_warning,
)

# Setup logging
logger = logging.getLogger(__name__)

# Create Typer app for backup commands
app = typer.Typer(help="Backup operations")


@app.command("create")
def create_backup():
    """
    Create a new backup of the data directory.

    Creates a compressed ZIP file containing all data (KB, documents, config, logs).
    """
    try:
        print_header("Creating Backup")

        from src.api.admin.backup_manager import BackupManager

        backup_manager = BackupManager()

        # Create backup
        with create_progress() as progress:
            task = progress.add_task("Creating backup...", total=None)

            backup_file = backup_manager.create_backup()

            progress.update(task, completed=True)

        # Get file info
        backup_path = Path(backup_file)
        file_size = backup_path.stat().st_size

        console.print()
        print_success("Backup created successfully")
        print_key_value("Filename", backup_path.name)
        print_key_value("Size", format_bytes(file_size))
        print_key_value("Location", str(backup_path.parent))

    except Exception as e:
        handle_error(e, "creating backup")


@app.command("list")
def list_backups():
    """
    List all available backups.

    Shows backup filename, size, and creation date.
    """
    try:
        print_header("Available Backups")

        from src.api.admin.backup_manager import BackupManager

        backup_manager = BackupManager()

        backups = backup_manager.list_backups()

        if not backups:
            print_info("No backups found")
            return

        # Create table
        table = create_table(
            f"Backups ({len(backups)} total)", ["Filename", "Size", "Created"]
        )

        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b["created"], reverse=True)

        for backup in backups:
            table.add_row(
                backup["filename"],
                format_bytes(backup["size_bytes"]),
                backup["created"],
            )

        console.print(table)
        print_success(f"Listed {format_count(len(backups), 'backup')}")

    except Exception as e:
        handle_error(e, "listing backups")


@app.command("delete")
def delete_backup(
    filename: str = typer.Argument(..., help="Backup filename to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Delete a specific backup file.

    Use 'backup list' to see available backups.
    """
    try:
        from src.api.admin.backup_manager import BackupManager

        backup_manager = BackupManager()

        # Check if backup exists
        backups = backup_manager.list_backups()
        backup = next((b for b in backups if b["filename"] == filename), None)

        if not backup:
            print_error(f"Backup not found: {filename}")
            raise typer.Exit(1)

        # Confirm deletion
        if not force:
            if not confirm_destructive("delete", f"backup '{filename}'"):
                return

        # Delete backup
        backup_manager.delete_backup(filename)

        print_success(f"Deleted backup: {filename}")

    except Exception as e:
        handle_error(e, "deleting backup")


@app.command("cleanup")
def cleanup_backups(
    keep: int = typer.Option(
        5, "--keep", "-k", help="Number of recent backups to keep"
    ),
    days: int = typer.Option(
        7, "--days", "-d", help="Delete backups older than N days"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Clean up old backups.

    Removes backups older than N days, keeping at least K most recent backups.
    """
    try:
        print_header("Backup Cleanup")

        from src.api.admin.backup_manager import BackupManager

        backup_manager = BackupManager()

        backups = backup_manager.list_backups()

        if not backups:
            print_info("No backups found")
            return

        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b["created"], reverse=True)

        # Determine which to delete
        cutoff_date = datetime.now() - timedelta(days=days)
        to_delete = []

        for idx, backup in enumerate(backups):
            # Keep first N backups regardless of age
            if idx < keep:
                continue

            # Delete if older than cutoff
            created_dt = datetime.fromisoformat(backup["created"])
            if created_dt < cutoff_date:
                to_delete.append(backup)

        if not to_delete:
            print_info("No backups match cleanup criteria")
            print_key_value("Total Backups", str(len(backups)))
            print_key_value(
                "Retention", f"Keep {keep} most recent, delete older than {days} days"
            )
            return

        # Show what will be deleted
        console.print()
        print_warning(f"Found {len(to_delete)} backups to delete:")
        for backup in to_delete:
            console.print(f"  • {backup['filename']} ({backup['created']})")

        # Confirm deletion
        if not force:
            console.print()
            if not confirm_destructive("delete", f"{len(to_delete)} old backups"):
                return

        # Delete backups
        deleted_count = 0
        for backup in to_delete:
            try:
                backup_manager.delete_backup(backup["filename"])
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete {backup['filename']}: {e}")

        console.print()
        print_success("Cleanup complete")
        print_key_value("Deleted", str(deleted_count))
        print_key_value("Remaining", str(len(backups) - deleted_count))

    except Exception as e:
        handle_error(e, "cleaning up backups")


@app.command("restore")
def restore_backup(
    source: str = typer.Argument(
        ..., help="Backup filename (from 'backup list') or path to external ZIP file"
    ),
    no_pre_restore: bool = typer.Option(
        False, "--no-pre-restore", help="Skip creating a safety backup before restoring"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Restore data from a backup file.

    Replaces current data directories with contents from the backup.
    A pre-restore safety backup is created by default.

    Use 'backup list' to see available backups, or provide a path to an external ZIP.
    """
    try:
        print_header("Restore from Backup")

        from src.api.admin.backup_manager import BackupManager

        backup_manager = BackupManager()

        # Resolve source: check if it's a known backup name or an external path
        zip_path = None
        source_path = Path(source)

        if source_path.is_file():
            zip_path = source_path
        else:
            # Try as a backup filename
            resolved = backup_manager.get_backup_path(source)
            if resolved:
                zip_path = resolved

        if not zip_path:
            print_error(f"Backup not found: {source}")
            print_info(
                "Use 'backup list' to see available backups, or provide a full file path."
            )
            raise typer.Exit(1)

        # Validate the backup
        print_info(f"Validating: {zip_path.name}")
        report = backup_manager.validate_backup(zip_path)

        if not report["valid"]:
            print_error("Backup validation failed:")
            for err in report["errors"]:
                console.print(f"  [red]✗[/red] {err}")
            raise typer.Exit(1)

        # Show validation summary
        console.print()
        print_key_value("File", zip_path.name)
        print_key_value("Files", str(report["file_count"]))
        print_key_value("Size", format_bytes(report["total_size"]))
        print_key_value("Directories", ", ".join(report["top_level_dirs"]))

        if report["warnings"]:
            for warn in report["warnings"]:
                print_warning(warn)

        # Confirm restore
        if not force:
            console.print()
            print_warning(
                "This will REPLACE the data directories listed above with backup contents."
            )
            if not no_pre_restore:
                print_info("A safety backup will be created before restoring.")
            if not confirm_destructive("restore", f"from '{zip_path.name}'"):
                return

        # Perform restore
        with create_progress() as progress:
            task = progress.add_task("Restoring backup...", total=None)

            result = backup_manager._restore_from_zip(
                zip_path, create_pre_restore=not no_pre_restore
            )

            progress.update(task, completed=True)

        console.print()

        if result["success"]:
            print_success("Restore completed successfully")
            print_key_value("Files Restored", str(result["files_restored"]))
            if result["pre_restore_backup"]:
                print_key_value("Safety Backup", result["pre_restore_backup"])
        else:
            print_error("Restore failed (data has been rolled back):")
            for err in result["errors"]:
                console.print(f"  [red]✗[/red] {err}")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        handle_error(e, "restoring backup")
