"""
Database CLI commands.

Manages database initialization, testing, and statistics.
"""

import logging
from datetime import datetime, timedelta

import typer

from src.cli.utils import (
    console,
    print_success,
    print_error,
    print_info,
    print_header,
    create_table,
    print_key_value,
    handle_error,
    format_count,
)
from src.config import settings
from src.email.db_manager import db_manager
from src.email.message_tracker import MessageTracker

# Initialize message tracker instance
message_tracker = MessageTracker()

# Setup logging
logger = logging.getLogger(__name__)

# Create Typer app for DB commands
app = typer.Typer(help="Database operations")


@app.command("init")
def init_database():
    """
    Initialize database tables.

    Creates all required tables if they don't exist. Safe to run multiple times.
    """
    try:
        print_header("Database Initialization")

        # Test connection first
        if not db_manager.test_connection():
            print_error("Database connection failed!")
            raise typer.Exit(1)

        print_info("Database connection successful")

        # Initialize database
        db_manager.init_db()

        print_success("Database tables initialized successfully")

    except Exception as e:
        handle_error(e, "initializing database")


@app.command("test")
def test_connection():
    """
    Test database connection.

    Verifies that the database is accessible and properly configured.
    """
    try:
        print_header("Database Connection Test")

        # Test connection
        if db_manager.test_connection():
            print_success("Database connection successful")

            # Get engine info
            info = db_manager.get_engine_info()

            console.print()
            print_key_value("Database Type", info['db_type'])
            print_key_value("Database URL", info['url'])
            print_key_value("Driver", info['driver'])

        else:
            print_error("Database connection failed")
            raise typer.Exit(1)

    except Exception as e:
        handle_error(e, "testing database connection")


@app.command("info")
def show_info():
    """
    Show database information.

    Displays database type, URL, driver, and configuration.
    """
    try:
        print_header("Database Information")

        # Get engine info
        info = db_manager.get_engine_info()

        print_key_value("Database Type", info['db_type'])
        print_key_value("Database URL", info['url'])
        print_key_value("Driver", info['driver'])

        console.print()
        console.print("  [bold cyan]Configuration:[/bold cyan]")

        if settings.db_type == "mariadb":
            print_key_value("  Host", settings.db_host)
            print_key_value("  Port", str(settings.db_port))
            print_key_value("  Database", settings.db_name)
            print_key_value("  User", settings.db_user)
        else:
            print_key_value("  SQLite Path", str(settings.sqlite_db_path))

        print_success("Database information displayed")

    except Exception as e:
        handle_error(e, "getting database info")


@app.command("stats")
def show_stats(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show stats for"),
):
    """
    Show database statistics.

    Displays message processing statistics, conversation counts, and more.
    """
    try:
        print_header("Database Statistics")

        # Get processing stats
        stats = message_tracker.get_stats()

        # Overall stats
        console.print("  [bold cyan]Overall Statistics:[/bold cyan]")
        print_key_value("Total Messages", str(stats['total_processed']))
        print_key_value("Successful", str(stats['successful']))
        print_key_value("Errors", str(stats['errors']))

        if stats['total_processed'] > 0:
            success_rate = (stats['successful'] / stats['total_processed']) * 100
            print_key_value("Success Rate", f"{success_rate:.1f}%")

        # Recent activity (last N days)
        console.print()
        console.print(f"  [bold cyan]Activity (Last {days} days):[/bold cyan]")

        # Get daily stats
        cutoff_date = datetime.now() - timedelta(days=days)
        with db_manager.get_session() as session:
            from src.email.db_models import ProcessingStats
            recent_stats = (
                session.query(ProcessingStats)
                .filter(ProcessingStats.date >= cutoff_date.date())
                .order_by(ProcessingStats.date.desc())
                .all()
            )

        if recent_stats:
            table = create_table(
                f"Daily Activity ({len(recent_stats)} days)",
                ["Date", "Processed", "Successful", "Errors"]
            )

            for day_stat in recent_stats:
                table.add_row(
                    str(day_stat.date),
                    str(day_stat.total_processed),
                    str(day_stat.successful),
                    str(day_stat.errors),
                )

            console.print(table)
        else:
            print_info(f"No activity in the last {days} days")

        # Conversation stats
        console.print()
        console.print("  [bold cyan]Conversations:[/bold cyan]")

        with db_manager.get_session() as session:
            from src.email.db_models import Conversation, ConversationMessage

            total_conversations = session.query(Conversation).count()
            total_messages = session.query(ConversationMessage).count()

            email_conversations = session.query(Conversation).filter(
                Conversation.channel == 'email'
            ).count()

            webchat_conversations = session.query(Conversation).filter(
                Conversation.channel == 'webchat'
            ).count()

            print_key_value("Total Conversations", str(total_conversations))
            print_key_value("Total Messages", str(total_messages))
            print_key_value("Email Threads", str(email_conversations))
            print_key_value("Webchat Threads", str(webchat_conversations))

        print_success("Statistics displayed successfully")

    except Exception as e:
        handle_error(e, "getting statistics")
