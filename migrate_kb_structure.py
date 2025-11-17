#!/usr/bin/env python3
"""
Migration script to reorganize data structure.

Old structure:
- data/documents/ (mixed documents + subdirectories)
- data/documents/attachments/ (email attachments)
- data/documents/emails/ (saved emails)

New structure:
- data/kb/documents/ (ALL documents - attachments + uploads)
- data/kb/emails/ (saved email copies)
- data/documents/ (kept for backward compatibility, can be used for manual drops)

This script:
1. Creates new directory structure
2. Moves files from old locations to new locations
3. Preserves the old directories (empty) for backward compatibility
"""

import shutil
from pathlib import Path


def migrate_kb_structure(dry_run: bool = True):
    """
    Migrate data from old structure to new KB structure.

    Args:
        dry_run: If True, only print what would be done without making changes
    """
    print("=" * 80)
    print("KB Structure Migration Script")
    print("=" * 80)
    print()

    if dry_run:
        print("DRY RUN MODE - No files will be moved")
        print()

    # Define paths
    old_attachments = Path("data/documents/attachments")
    old_emails = Path("data/documents/emails")
    new_documents = Path("data/kb/documents")
    new_emails = Path("data/kb/emails")

    # Create new directories
    print("Step 1: Creating new directory structure")
    print(f"  - {new_documents}")
    print(f"  - {new_emails}")
    print()

    if not dry_run:
        new_documents.mkdir(parents=True, exist_ok=True)
        new_emails.mkdir(parents=True, exist_ok=True)

    # Migrate attachments
    print("Step 2: Migrating email attachments")
    if old_attachments.exists():
        attachment_files = list(old_attachments.glob("*"))
        # Filter out directories, only get files
        attachment_files = [f for f in attachment_files if f.is_file()]
        print(f"  Found {len(attachment_files)} attachment(s) in {old_attachments}")

        for file in attachment_files:
            dest = new_documents / file.name
            if dry_run:
                print(f"    Would move: {file} -> {dest}")
            else:
                print(f"    Moving: {file.name}")
                shutil.move(str(file), str(dest))
    else:
        print(f"  No attachments directory found at {old_attachments}")
    print()

    # Migrate emails
    print("Step 3: Migrating saved emails")
    if old_emails.exists():
        email_files = list(old_emails.glob("*"))
        # Filter out directories, only get files
        email_files = [f for f in email_files if f.is_file()]
        print(f"  Found {len(email_files)} email(s) in {old_emails}")

        for file in email_files:
            dest = new_emails / file.name
            if dry_run:
                print(f"    Would move: {file} -> {dest}")
            else:
                print(f"    Moving: {file.name}")
                shutil.move(str(file), str(dest))
    else:
        print(f"  No emails directory found at {old_emails}")
    print()

    # Summary
    print("=" * 80)
    print("Migration Summary")
    print("=" * 80)
    if dry_run:
        print("This was a DRY RUN - no files were actually moved.")
        print()
        print("To perform the actual migration, run:")
        print("  python migrate_kb_structure.py --execute")
    else:
        print("Migration completed successfully!")
        print()
        print("New structure:")
        print(f"  - {new_documents} (all documents from attachments and uploads)")
        print(f"  - {new_emails} (saved email copies)")
        print()
        print("Old directories have been preserved (now empty):")
        print(f"  - {old_attachments}")
        print(f"  - {old_emails}")
        print()
        print("You can safely remove the old subdirectories:")
        print(f"  rm -rf {old_attachments}")
        print(f"  rm -rf {old_emails}")
    print()


if __name__ == "__main__":
    import sys

    # Check for --execute flag
    execute = "--execute" in sys.argv or "-e" in sys.argv

    migrate_kb_structure(dry_run=not execute)
