"""
Quick migration runner for adding query tracking columns.

Run this from the project root:
    python run_migration.py
"""

import logging
import sys
from pathlib import Path

from sqlalchemy import text

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import settings
from src.email.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Apply migration to add query tracking columns."""
    logger.info("🔧 Applying migration: Add query tracking columns")
    logger.info(f"   Database: {settings.get_database_url()}")

    db_manager = DatabaseManager()

    # Define ALTER TABLE statements
    statements = [
        "ALTER TABLE conversation_messages ADD COLUMN original_query TEXT NULL",
        "ALTER TABLE conversation_messages ADD COLUMN optimized_query TEXT NULL",
        "ALTER TABLE conversation_messages ADD COLUMN optimization_applied BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE conversation_messages ADD COLUMN sources_used JSON NULL",
        "ALTER TABLE conversation_messages ADD COLUMN retrieval_metadata JSON NULL",
    ]

    try:
        with db_manager.get_session() as session:
            for stmt in statements:
                logger.info(f"   Executing: {stmt[:60]}...")
                try:
                    session.execute(text(stmt))
                except Exception as e:
                    error_str = str(e).lower()
                    if "duplicate column" in error_str or "already exists" in error_str:
                        column_name = stmt.split("ADD COLUMN")[1].split()[0]
                        logger.warning(f"   ⚠️  Column '{column_name}' already exists (skipping)")
                    else:
                        raise

            session.commit()
            logger.info("✅ Migration completed successfully!")

        # Verify
        with db_manager.get_session() as session:
            session.execute(
                text(
                    "SELECT original_query, optimized_query, optimization_applied, "
                    "sources_used, retrieval_metadata FROM conversation_messages LIMIT 1"
                )
            )
            logger.info("✅ Verification passed - all columns accessible")

        logger.info(
            "\n📊 New columns added:\n"
            "   - original_query (TEXT)\n"
            "   - optimized_query (TEXT)\n"
            "   - optimization_applied (BOOLEAN)\n"
            "   - sources_used (JSON)\n"
            "   - retrieval_metadata (JSON)"
        )

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
