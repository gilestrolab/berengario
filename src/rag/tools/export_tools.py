"""
Export tools for generating data files (CSV, JSON, text).

Provides functions to export structured data in various formats.
"""

import csv
import json
import logging
from io import StringIO
from typing import Any, Dict, List

from .base import ParameterType, Tool, ToolParameter, register_tool

logger = logging.getLogger(__name__)


def export_to_csv(
    data: List[Dict[str, Any]],
    filename: str = "export.csv",
) -> Dict[str, Any]:
    """
    Export data to CSV format.

    Args:
        data: List of dictionaries to export
        filename: Name for the CSV file

    Returns:
        Dictionary with attachment data (content, filename, content_type)
    """
    try:
        if not data:
            raise ValueError("No data provided for CSV export")

        # Get all unique keys from all dicts
        all_keys = set()
        for item in data:
            all_keys.update(item.keys())

        fieldnames = sorted(all_keys)

        # Create CSV in memory
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

        csv_content = output.getvalue().encode("utf-8")

        # Ensure filename has .csv extension
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        logger.info(f"Exported {len(data)} rows to CSV")

        return {
            "content": csv_content,
            "filename": filename,
            "content_type": "text/csv",
        }

    except Exception as e:
        logger.error(f"Failed to export to CSV: {e}", exc_info=True)
        raise


def create_text_file(
    content: str,
    filename: str = "document.txt",
) -> Dict[str, Any]:
    """
    Create a plain text file.

    Args:
        content: Text content for the file
        filename: Name for the file

    Returns:
        Dictionary with attachment data (content, filename, content_type)
    """
    try:
        # Ensure filename has .txt extension
        if not filename.endswith(".txt"):
            filename = f"{filename}.txt"

        text_content = content.encode("utf-8")

        logger.info(f"Created text file: {filename}")

        return {
            "content": text_content,
            "filename": filename,
            "content_type": "text/plain",
        }

    except Exception as e:
        logger.error(f"Failed to create text file: {e}", exc_info=True)
        raise


def create_json_file(
    data: Any,
    filename: str = "data.json",
) -> Dict[str, Any]:
    """
    Export data to JSON format.

    Args:
        data: Data to export (dict, list, or any JSON-serializable object)
        filename: Name for the JSON file

    Returns:
        Dictionary with attachment data (content, filename, content_type)
    """
    try:
        # Convert to JSON with pretty printing
        json_content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

        # Ensure filename has .json extension
        if not filename.endswith(".json"):
            filename = f"{filename}.json"

        logger.info(f"Created JSON file: {filename}")

        return {
            "content": json_content,
            "filename": filename,
            "content_type": "application/json",
        }

    except Exception as e:
        logger.error(f"Failed to create JSON file: {e}", exc_info=True)
        raise


# Register tools
export_to_csv_tool = Tool(
    name="export_to_csv",
    description="Export tabular data to CSV format. Use this when the user wants to download data as a spreadsheet.",
    parameters=[
        ToolParameter(
            name="data",
            type=ParameterType.ARRAY,
            description="List of dictionaries to export, where each dict represents a row",
            required=True,
            items={"type": "object"},
        ),
        ToolParameter(
            name="filename",
            type=ParameterType.STRING,
            description="Name for the CSV file (without extension)",
            required=False,
        ),
    ],
    function=export_to_csv,
    returns_attachment=True,
)

create_text_file_tool = Tool(
    name="create_text_file",
    description="Create a plain text file. Use this for formatted text output or documentation.",
    parameters=[
        ToolParameter(
            name="content",
            type=ParameterType.STRING,
            description="The text content to include in the file",
            required=True,
        ),
        ToolParameter(
            name="filename",
            type=ParameterType.STRING,
            description="Name for the text file (without extension)",
            required=False,
        ),
    ],
    function=create_text_file,
    returns_attachment=True,
)

create_json_file_tool = Tool(
    name="create_json_file",
    description="Export structured data to JSON format. Use this for data that needs to be processed programmatically.",
    parameters=[
        ToolParameter(
            name="data",
            type=ParameterType.OBJECT,
            description="Data to export (any JSON-serializable data structure)",
            required=True,
        ),
        ToolParameter(
            name="filename",
            type=ParameterType.STRING,
            description="Name for the JSON file (without extension)",
            required=False,
        ),
    ],
    function=create_json_file,
    returns_attachment=True,
)

# Register tools in global registry
register_tool(export_to_csv_tool)
register_tool(create_text_file_tool)
register_tool(create_json_file_tool)
