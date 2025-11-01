"""
RAG tool system for function calling and attachment generation.

This module provides a framework for LLM function calling, enabling
the generation of attachments like calendar files, CSV exports, etc.
"""

from .base import Tool, ToolRegistry, ToolParameter, get_registry
from .calendar_tools import create_calendar_event, create_calendar_from_data
from .export_tools import export_to_csv, create_text_file, create_json_file
from .tool_executor import ToolExecutor
from .whitelist_tools import (
    add_to_teach_whitelist,
    remove_from_teach_whitelist,
    add_to_query_whitelist,
    remove_from_query_whitelist,
    set_tool_context,
    clear_tool_context,
)

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolParameter",
    "get_registry",
    "ToolExecutor",
    "create_calendar_event",
    "create_calendar_from_data",
    "export_to_csv",
    "create_text_file",
    "create_json_file",
]
