"""
RAG tool system for function calling and attachment generation.

This module provides a framework for LLM function calling, enabling
the generation of attachments like calendar files, CSV exports, etc.
"""

from .base import Tool, ToolParameter, ToolRegistry, get_registry
from .calendar_tools import create_calendar_event, create_calendar_from_data
from .context import (
    clear_tool_context,
    get_tool_context,
    get_user_email,
    is_admin,
    is_email_request,
    set_tool_context,
    validate_admin_access,
)
from .export_tools import create_json_file, create_text_file, export_to_csv
from .tool_executor import ToolExecutor
from .whitelist_tools import (
    add_to_query_whitelist,
    add_to_teach_whitelist,
    remove_from_query_whitelist,
    remove_from_teach_whitelist,
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
    "add_to_query_whitelist",
    "add_to_teach_whitelist",
    "clear_tool_context",
    "get_tool_context",
    "get_user_email",
    "is_admin",
    "is_email_request",
    "remove_from_query_whitelist",
    "remove_from_teach_whitelist",
    "set_tool_context",
    "validate_admin_access",
]
