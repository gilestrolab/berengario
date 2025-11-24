"""
Database migration script for adding query tracking columns.

This script applies the migration to add query optimization and source
document tracking columns to the conversation_messages table.

Usage:
    python migrations/apply_migration.py

The script will automatically detect your database type (SQLite or MariaDB)
from the configuration and apply the migration accordingly.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.config import settings
from src.email.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def apply_migration():
    """Apply the query tracking columns migration."""
    logger.info("Starting migration: Add query tracking columns")

    # Initialize database manager
    db_manager = DatabaseManager()

    # Read migration SQL
    migration_file = Path(__file__).parent / "001_add_query_tracking_columns.sql"
    with open(migration_file, "r") as f:
        sql_content = f.read()

    # Extract ALTER statements (skip comments and empty lines)
    statements = []
    for line in sql_content.split("\n"):
        line = line.strip()
        if line and not line.startswith("--"):
            if line.startswith("ALTER TABLE"):
                current_statement = line
            elif current_statement and not line.endswith(";"):
                current_statement += " " + line
            elif current_statement:
                current_statement += " " + line
                statements.append(current_statement.rstrip(";"))
                current_statement = None

    # Group statements that belong together
    grouped_statements = []
    current_group = []
    for stmt in statements:
        current_group.append(stmt)
        if "ADD COLUMN" in stmt:
            grouped_statements.append(current_group)
            current_group = []

    if current_group:
        grouped_statements.append(current_group)

    # Apply migration
    try:
        with db_manager.get_session() as session:
            logger.info(f"Applying migration to {settings.db_type} database...")

            # Apply each ALTER TABLE statement
            for i, stmt_group in enumerate(grouped_statements, 1):
                for stmt in stmt_group:
                    logger.info(f"Executing: {stmt[:80]}...")
                    try:
                        session.execute(text(stmt))
                    except Exception as e:
                        # Check if column already exists
                        if "duplicate column" in str(e).lower() or "already exists" in str(
                            e
                        ).lower():
                            logger.warning(f"Column already exists (skipping): {stmt[:50]}...")
                        else:
                            raise

            session.commit()
            logger.info("✅ Migration applied successfully!")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

    # Verify migration
    verify_migration(db_manager)


def verify_migration(db_manager: DatabaseManager):
    """Verify that the migration was applied correctly."""
    logger.info("Verifying migration...")

    with db_manager.get_session() as session:
        # Try to query the new columns
        result = session.execute(
            text(
                "SELECT original_query, optimized_query, optimization_applied, "
                "sources_used, retrieval_metadata FROM conversation_messages LIMIT 1"
            )
        )

        logger.info("✅ Migration verified - all new columns are accessible!")


if __name__ == "__main__":
    try:
        apply_migration()
        logger.info("\n🎉 Migration completed successfully!")
        logger.info(
            "\nNew columns added to conversation_messages table:\n"
            "  - original_query (TEXT)\n"
            "  - optimized_query (TEXT)\n"
            "  - optimization_applied (BOOLEAN)\n"
            "  - sources_used (JSON)\n"
            "  - retrieval_metadata (JSON)\n"
        )
    except Exception as e:
        logger.error(f"\n💥 Migration failed: {e}")
        sys.exit(1)
