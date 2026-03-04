"""
Base classes and registry for the RAG tool system.

Provides the foundation for defining and registering tools that can be
called by the LLM to generate attachments and perform actions.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ParameterType(str, Enum):
    """Parameter types for tool functions."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """
    Definition of a parameter for a tool function.

    Attributes:
        name: Parameter name
        type: Parameter type (string, integer, etc.)
        description: Human-readable description
        required: Whether parameter is required
        enum: Optional list of allowed values
        items: For array types, description of array items
    """

    name: str
    type: ParameterType
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, Any]] = None


@dataclass
class Tool:
    """
    Definition of a tool that can be called by the LLM.

    Attributes:
        name: Unique tool name
        description: Human-readable description of what the tool does
        parameters: List of parameters the tool accepts
        function: The actual function to execute
        returns_attachment: Whether this tool returns an attachment
    """

    name: str
    description: str
    parameters: List[ToolParameter]
    function: Callable
    returns_attachment: bool = True

    def to_openai_function(self) -> Dict[str, Any]:
        """
        Convert tool definition to OpenAI function calling format.

        Returns:
            Dictionary in OpenAI function format
        """
        parameters_dict = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param in self.parameters:
            prop = {
                "type": param.type.value,
                "description": param.description,
            }

            if param.enum:
                prop["enum"] = param.enum

            if param.items:
                prop["items"] = param.items

            parameters_dict["properties"][param.name] = prop

            if param.required:
                parameters_dict["required"].append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters_dict,
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool function with given parameters.

        Args:
            **kwargs: Tool parameters

        Returns:
            Tool result (typically attachment dict or data)

        Raises:
            Exception: If tool execution fails
        """
        try:
            logger.info(f"Executing tool: {self.name} with params: {kwargs}")
            result = self.function(**kwargs)
            logger.info(f"Tool {self.name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {e}", exc_info=True)
            raise


class ToolRegistry:
    """
    Central registry for managing available tools.

    Maintains a collection of tools and provides methods to register,
    retrieve, and list them.
    """

    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: Dict[str, Tool] = {}
        logger.info("ToolRegistry initialized")

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool to register

        Raises:
            ValueError: If tool with same name already exists
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name} already registered")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[Tool]:
        """
        Retrieve a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """
        Get list of all registered tools.

        Returns:
            List of Tool instances
        """
        return list(self._tools.values())

    def get_openai_functions(self) -> List[Dict[str, Any]]:
        """
        Get all tools in OpenAI function calling format.

        Returns:
            List of function definitions
        """
        return [tool.to_openai_function() for tool in self._tools.values()]


# Global registry instance
_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.

    Returns:
        Global ToolRegistry instance
    """
    return _global_registry


def register_tool(tool: Tool) -> None:
    """
    Register a tool in the global registry.

    Args:
        tool: Tool to register
    """
    _global_registry.register(tool)
