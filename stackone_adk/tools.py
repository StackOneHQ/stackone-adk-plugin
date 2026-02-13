"""StackOne tool adapter for Google ADK.

Converts StackOne's dynamically-discovered tools into ADK-compatible BaseTool instances.
Handles JSON Schema to FunctionDeclaration conversion and sync-to-async bridging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from stackone_ai.models import StackOneTool

logger = logging.getLogger(__name__)

# JSON Schema type string → google.genai types.Type enum
_TYPE_MAP: dict[str, types.Type] = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}


def _convert_property_to_schema(prop: dict[str, Any]) -> types.Schema:
    """Convert a single JSON Schema property dict to a types.Schema.

    Handles type, description, enum, nullable, array items, and nested objects.
    Unknown types default to STRING. Unknown fields are silently ignored.
    """
    type_str = prop.get("type", "string")
    schema_type = _TYPE_MAP.get(type_str, types.Type.STRING)

    kwargs: dict[str, Any] = {"type": schema_type}

    if "description" in prop:
        kwargs["description"] = prop["description"]

    if "enum" in prop:
        kwargs["enum"] = prop["enum"]

    if "nullable" in prop:
        kwargs["nullable"] = prop["nullable"]

    # Handle array items
    if schema_type == types.Type.ARRAY and "items" in prop:
        items = prop["items"]
        if isinstance(items, dict):
            kwargs["items"] = _convert_property_to_schema(items)

    # Handle nested object properties
    if schema_type == types.Type.OBJECT and "properties" in prop:
        nested_props, nested_required = _convert_parameters_to_schema(prop["properties"])
        kwargs["properties"] = nested_props
        if nested_required:
            kwargs["required"] = nested_required

    return types.Schema(**kwargs)


def _convert_parameters_to_schema(
    properties: dict[str, Any],
) -> tuple[dict[str, types.Schema], list[str]]:
    """Convert all JSON Schema properties to ADK Schema format.

    Returns:
        Tuple of (converted properties dict, list of required field names).
        Required fields are those with nullable=False (StackOne SDK convention).
    """
    converted: dict[str, types.Schema] = {}
    required: list[str] = []

    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        converted[name] = _convert_property_to_schema(prop)
        if prop.get("nullable") is False:
            required.append(name)

    return converted, required


class StackOneAdkTool(BaseTool):
    """Adapter that wraps a StackOneTool as an ADK BaseTool.

    Converts StackOne's JSON Schema parameters to ADK FunctionDeclarations
    and bridges the synchronous execute() method to async run_async().
    """

    def __init__(self, stackone_tool: StackOneTool) -> None:
        super().__init__(
            name=stackone_tool.name,
            description=stackone_tool.description,
        )
        self._stackone_tool = stackone_tool

    def _get_declaration(self) -> types.FunctionDeclaration:
        """Convert StackOne tool parameters to an ADK FunctionDeclaration."""
        properties = self._stackone_tool.parameters.properties

        if not properties:
            return types.FunctionDeclaration(
                name=self.name,
                description=self.description,
            )

        converted_props, required = _convert_parameters_to_schema(properties)

        parameters = types.Schema(
            type=types.Type.OBJECT,
            properties=converted_props,
        )
        if required:
            parameters.required = required

        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Execute the StackOne tool asynchronously.

        Runs the synchronous StackOneTool.execute() in a thread pool
        to avoid blocking the event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._stackone_tool.execute, args)
            if isinstance(result, dict):
                return result
            return {"result": result}
        except Exception as e:
            logger.error(f"Tool {self.name} execution failed: {e}")
            return {"error": str(e)}
