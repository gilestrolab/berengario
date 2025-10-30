"""
Tool executor for processing LLM function calls and generating attachments.

Handles execution of tools requested by the LLM and manages the results.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import ToolRegistry, get_registry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Executes tools based on LLM function calls.

    Manages tool execution, error handling, and result formatting.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        Initialize tool executor.

        Args:
            registry: Tool registry to use (defaults to global registry)
        """
        self.registry = registry or get_registry()
        logger.info("ToolExecutor initialized")

    def execute_function_call(
        self,
        function_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a single function call.

        Args:
            function_name: Name of the function to call
            arguments: Function arguments

        Returns:
            Dictionary with execution results:
            - success (bool): Whether execution succeeded
            - result (Any): Function result if successful
            - error (str): Error message if failed
            - is_attachment (bool): Whether result is an attachment
        """
        try:
            logger.info(f"Executing function: {function_name}")

            tool = self.registry.get(function_name)
            if not tool:
                error_msg = f"Tool {function_name} not found"
                logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'is_attachment': False,
                }

            # Execute tool
            result = tool.execute(**arguments)

            return {
                'success': True,
                'result': result,
                'error': None,
                'is_attachment': tool.returns_attachment,
            }

        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'error': error_msg,
                'is_attachment': False,
            }

    def execute_function_calls(
        self,
        function_calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Execute multiple function calls.

        Args:
            function_calls: List of function calls, each with 'name' and 'arguments'

        Returns:
            Dictionary with:
            - results (List): List of individual results
            - attachments (List): List of attachments to include in email
            - success_count (int): Number of successful executions
            - error_count (int): Number of failed executions
        """
        results = []
        attachments = []
        success_count = 0
        error_count = 0

        for call in function_calls:
            function_name = call.get('name')
            arguments = call.get('arguments', {})

            result = self.execute_function_call(function_name, arguments)
            results.append(result)

            if result['success']:
                success_count += 1
                if result['is_attachment'] and result['result']:
                    attachments.append(result['result'])
            else:
                error_count += 1

        logger.info(
            f"Executed {len(function_calls)} function calls: "
            f"{success_count} successful, {error_count} failed"
        )

        return {
            'results': results,
            'attachments': attachments,
            'success_count': success_count,
            'error_count': error_count,
        }

    def get_tool_descriptions(self) -> str:
        """
        Get formatted descriptions of all available tools.

        Returns:
            String describing all available tools
        """
        tools = self.registry.list_tools()

        descriptions = ["Available tools:"]
        for tool in tools:
            descriptions.append(f"\n- {tool.name}: {tool.description}")

        return "\n".join(descriptions)
