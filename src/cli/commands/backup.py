"""
Backup CLI commands.

Manages system backups (create, list, delete, cleanup).
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
