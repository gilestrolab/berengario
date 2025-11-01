#!/usr/bin/env python3
"""
Initialize conversation tracking database tables.

This script creates the Conversation and ConversationMessage tables
in the database. Safe to run multiple times (idempotent).
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.email.db_manager import db_manager

def main():
    """Initialize conversation database tables."""
    print("Initializing conversation tracking database tables...")

    try:
        # Create all tables (including new conversation tables)
        db_manager.init_db()
        print("✓ Database tables initialized successfully")

        # Test connection
        if db_manager.test_connection():
            print("✓ Database connection test passed")
        else:
            print("✗ Database connection test failed")
            return 1

        # Show engine info
        info = db_manager.get_engine_info()
        print(f"\nDatabase Info:")
        print(f"  Type: {info['db_type']}")
        print(f"  URL: {info['url']}")
        print(f"  Driver: {info['driver']}")

        return 0

    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
