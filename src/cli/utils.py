"""
CLI utility functions for console output, formatting, and user interaction.
"""

import sys
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich import box
import typer


# Global console instance
console = Console()


def print_success(message: str) -> None:
    """
    Print success message in green.

    Args:
        message: Success message to display
    """
    console.print(f"✓ {message}", style="bold green")


def print_error(message: str) -> None:
    """
    Print error message in red.

    Args:
        message: Error message to display
    """
    console.print(f"✗ {message}", style="bold red")


def print_warning(message: str) -> None:
    """
    Print warning message in yellow.

    Args:
        message: Warning message to display
    """
    console.print(f"⚠ {message}", style="bold yellow")


def print_info(message: str) -> None:
    """
    Print info message in blue.

    Args:
        message: Info message to display
    """
    console.print(f"ℹ {message}", style="bold blue")


def print_header(title: str) -> None:
    """
    Print section header.

    Args:
        title: Header title
    """
    console.print()
    console.print(f"[bold cyan]{title}[/bold cyan]")
    console.print("─" * len(title), style="cyan")


def print_panel(content: str, title: Optional[str] = None, style: str = "cyan") -> None:
    """
    Print content in a bordered panel.

    Args:
        content: Panel content
        title: Optional panel title
        style: Border color style
    """
    panel = Panel(content, title=title, border_style=style, box=box.ROUNDED)
    console.print(panel)


def create_table(title: str, columns: list[str]) -> Table:
    """
    Create a rich table with standard formatting.

    Args:
        title: Table title
        columns: List of column headers

    Returns:
        Configured Table object
    """
    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold cyan")
    for column in columns:
        table.add_column(column, style="white")
    return table


def confirm(message: str, default: bool = False) -> bool:
    """
    Ask user for yes/no confirmation.

    Args:
        message: Confirmation prompt message
        default: Default value if user just presses Enter

    Returns:
        True if user confirms, False otherwise
    """
    return typer.confirm(message, default=default)


def confirm_destructive(action: str, target: str) -> bool:
    """
    Ask for confirmation on destructive operations with double check.

    Args:
        action: Action being performed (e.g., "delete", "clear")
        target: Target of the action (e.g., "all documents")

    Returns:
        True if user confirms twice, False otherwise
    """
    print_warning(f"You are about to {action} {target}. This action cannot be undone!")

    if not confirm(f"Are you sure you want to {action} {target}?"):
        print_info("Operation cancelled")
        return False

    # Double confirmation for extra safety
    if not confirm(f"Really {action} {target}? Type 'yes' to confirm", default=False):
        print_info("Operation cancelled")
        return False

    return True


def create_progress() -> Progress:
    """
    Create a progress bar with standard formatting.

    Returns:
        Configured Progress object
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def format_bytes(bytes_size: int) -> str:
    """
    Format bytes to human-readable string.

    Args:
        bytes_size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def format_count(count: int, singular: str, plural: str = None) -> str:
    """
    Format count with proper singular/plural form.

    Args:
        count: Number to format
        singular: Singular form (e.g., "document")
        plural: Plural form (e.g., "documents"), defaults to singular + 's'

    Returns:
        Formatted string (e.g., "5 documents")
    """
    if plural is None:
        plural = singular + 's'

    return f"{count} {singular if count == 1 else plural}"


def handle_error(error: Exception, context: str = "") -> None:
    """
    Handle and display error with context.

    Args:
        error: Exception that occurred
        context: Context description (e.g., "uploading document")
    """
    if context:
        print_error(f"Error {context}: {str(error)}")
    else:
        print_error(f"Error: {str(error)}")

    # Exit with error code
    sys.exit(1)


def print_key_value(key: str, value: str, key_width: int = 20) -> None:
    """
    Print key-value pair with aligned formatting.

    Args:
        key: Key name
        value: Value to display
        key_width: Width for key column alignment
    """
    console.print(f"  {key:<{key_width}} : [bold]{value}[/bold]")
