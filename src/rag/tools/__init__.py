"""
RAG tool system for function calling and attachment generation.

This module provides a framework for LLM function calling, enabling
the generation of attachments like calendar files, CSV exports, etc.
"""

from .base import Tool, ToolParameter, ToolRegistry, get_registry
from .calendar_tools import create_calendar_event, create_calendar_from_data
from .context import (
    clear_tool_context,
    get_conversation_manager,
    get_kb_manager,
    get_tenant_id,
    get_tool_context,
    get_user_email,
    is_admin,
    is_email_request,
    set_tool_context,
    validate_admin_access,
)
from .database_tools import query_analytics, query_conversation_history
from .export_tools import create_json_file, create_text_file, export_to_csv
from .tool_executor import ToolExecutor

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
    "clear_tool_context",
    "get_conversation_manager",
    "get_kb_manager",
    "get_tenant_id",
    "get_tool_context",
    "get_user_email",
    "is_admin",
    "is_email_request",
    "query_analytics",
    "query_conversation_history",
    "set_tool_context",
    "validate_admin_access",
]
