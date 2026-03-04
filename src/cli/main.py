"""
Berengario CLI - Command-line interface for Berengario administration.

Provides unified command-line access to knowledge base, database, and backup operations.
"""

import logging
import sys

import typer
from rich.console import Console

from src.cli.commands import backup, db, kb
from src.cli.utils import print_error, print_info
from src.config import settings

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors by default
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create main Typer app
app = typer.Typer(
    name="berengario",
    help="Berengario CLI - Administration and management tool",
    add_completion=False,
)

# Add command groups
app.add_typer(kb.app, name="kb", help="Knowledge base operations")
app.add_typer(db.app, name="db", help="Database operations")
app.add_typer(backup.app, name="backup", help="Backup operations")

# Console for output
console = Console()


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """
    Berengario CLI - Command-line administration tool.

    Use COMMAND --help for detailed help on each command group.

    Examples:
        berengario kb list              # List all documents
        berengario kb reingest          # Reingest all documents
        berengario db init              # Initialize database
        berengario backup create        # Create backup
    """
    # Configure logging based on flags
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    elif verbose:
        logging.getLogger().setLevel(logging.INFO)
        logger.info("Verbose logging enabled")


@app.command("version")
def show_version():
    """
    Show Berengario version and instance information.
    """
    console.print()
    console.print("[bold cyan]Berengario CLI[/bold cyan]")
    console.print("─" * 40)
    console.print(f"Instance:     [bold]{settings.instance_name}[/bold]")
    console.print(f"Organization: [bold]{settings.organization}[/bold]")
    console.print(f"Description:  {settings.instance_description}")
    console.print()
    console.print("[dim]Configuration:[/dim]")
    console.print(f"  LLM Model:       {settings.openrouter_model}")
    console.print(f"  Embedding Model: {settings.openai_embedding_model}")
    console.print("  Database Type:   MariaDB")
    console.print(f"  KB Path:         {settings.chroma_db_path}")
    console.print()


@app.command("info")
def show_info():
    """
    Show system information and configuration.
    """
    from src.cli.utils import print_header, print_key_value

    print_header("Berengario System Information")

    # Instance info
    console.print("  [bold cyan]Instance:[/bold cyan]")
    print_key_value("  Name", settings.instance_name)
    print_key_value("  Organization", settings.organization)
    print_key_value("  Description", settings.instance_description)

    # Model info
    console.print()
    console.print("  [bold cyan]Models:[/bold cyan]")
    print_key_value("  LLM", settings.openrouter_model)
    print_key_value("  Embedding", settings.openai_embedding_model)

    # RAG config
    console.print()
    console.print("  [bold cyan]RAG Configuration:[/bold cyan]")
    print_key_value("  Chunk Size", str(settings.chunk_size))
    print_key_value("  Chunk Overlap", str(settings.chunk_overlap))
    print_key_value("  Top-K Retrieval", str(settings.top_k_retrieval))
    print_key_value("  Similarity Threshold", str(settings.similarity_threshold))

    # Database info
    console.print()
    console.print("  [bold cyan]Database:[/bold cyan]")
    print_key_value("  Type", "MariaDB")
    print_key_value("  Host", settings.db_host)
    print_key_value("  Port", str(settings.db_port))
    print_key_value("  Database", settings.db_name)

    # Paths
    console.print()
    console.print("  [bold cyan]Paths:[/bold cyan]")
    print_key_value("  Documents", str(settings.documents_path))
    print_key_value("  ChromaDB", str(settings.chroma_db_path))
    print_key_value("  Logs", str(settings.log_file))

    print_info("System information displayed")


def cli():
    """
    Entry point for CLI when installed via pip/setup.py.

    This function is referenced in pyproject.toml [project.scripts].
    """
    try:
        app()
    except KeyboardInterrupt:
        console.print()
        print_info("Operation cancelled by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        logger.exception("Unexpected error in CLI")
        print_error(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
