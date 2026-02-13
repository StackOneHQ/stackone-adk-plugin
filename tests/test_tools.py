"""Tests for StackOne ADK tool adapter and schema conversion."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from google.genai import types

from stackone_adk.tools import (
    StackOneAdkTool,
    _convert_parameters_to_schema,
    _convert_property_to_schema,
)

# --- Schema conversion tests ---


class TestConvertPropertyToSchema:
    def test_string_type(self):
        schema = _convert_property_to_schema({"type": "string", "description": "A name"})
        assert schema.type == types.Type.STRING
        assert schema.description == "A name"

    def test_integer_type(self):
        schema = _convert_property_to_schema({"type": "integer"})
        assert schema.type == types.Type.INTEGER

    def test_number_type(self):
        schema = _convert_property_to_schema({"type": "number"})
        assert schema.type == types.Type.NUMBER

    def test_boolean_type(self):
        schema = _convert_property_to_schema({"type": "boolean"})
        assert schema.type == types.Type.BOOLEAN

    def test_array_type_with_items(self):
        schema = _convert_property_to_schema({
            "type": "array",
            "items": {"type": "string"},
            "description": "A list of tags",
        })
        assert schema.type == types.Type.ARRAY
        assert schema.items.type == types.Type.STRING
        assert schema.description == "A list of tags"

    def test_object_type_with_properties(self):
        schema = _convert_property_to_schema({
            "type": "object",
            "properties": {
                "name": {"type": "string", "nullable": False},
                "age": {"type": "integer", "nullable": True},
            },
        })
        assert schema.type == types.Type.OBJECT
        assert "name" in schema.properties
        assert "age" in schema.properties
        assert schema.required == ["name"]

    def test_enum_values(self):
        schema = _convert_property_to_schema({
            "type": "string",
            "enum": ["active", "inactive", "pending"],
        })
        assert schema.type == types.Type.STRING
        assert schema.enum == ["active", "inactive", "pending"]

    def test_nullable_field(self):
        schema = _convert_property_to_schema({"type": "string", "nullable": True})
        assert schema.nullable is True

    def test_non_nullable_field(self):
        schema = _convert_property_to_schema({"type": "string", "nullable": False})
        assert schema.nullable is False

    def test_unknown_type_defaults_to_string(self):
        schema = _convert_property_to_schema({"type": "custom_type"})
        assert schema.type == types.Type.STRING

    def test_missing_type_defaults_to_string(self):
        schema = _convert_property_to_schema({"description": "No type specified"})
        assert schema.type == types.Type.STRING

    def test_unknown_fields_ignored(self):
        schema = _convert_property_to_schema({
            "type": "string",
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "$ref": "#/components/schemas/Foo",
            "x-custom": "ignored",
        })
        assert schema.type == types.Type.STRING


class TestConvertParametersToSchema:
    def test_basic_properties(self):
        properties = {
            "name": {"type": "string", "nullable": False},
            "email": {"type": "string", "nullable": True},
        }
        converted, required = _convert_parameters_to_schema(properties)
        assert "name" in converted
        assert "email" in converted
        assert required == ["name"]

    def test_all_required(self):
        properties = {
            "a": {"type": "string", "nullable": False},
            "b": {"type": "integer", "nullable": False},
        }
        _, required = _convert_parameters_to_schema(properties)
        assert set(required) == {"a", "b"}

    def test_none_required(self):
        properties = {
            "a": {"type": "string", "nullable": True},
            "b": {"type": "integer", "nullable": True},
        }
        _, required = _convert_parameters_to_schema(properties)
        assert required == []

    def test_non_dict_property_skipped(self):
        properties = {
            "valid": {"type": "string", "nullable": False},
            "invalid": "not a dict",
        }
        converted, required = _convert_parameters_to_schema(properties)
        assert "valid" in converted
        assert "invalid" not in converted
        assert required == ["valid"]

    def test_empty_properties(self):
        converted, required = _convert_parameters_to_schema({})
        assert converted == {}
        assert required == []

    def test_nullable_not_set_means_not_required(self):
        properties = {
            "field": {"type": "string"},
        }
        _, required = _convert_parameters_to_schema(properties)
        assert required == []


# --- Tool adapter tests ---


def _make_mock_tool(
    name: str = "test_tool",
    description: str = "A test tool",
    properties: dict | None = None,
) -> MagicMock:
    """Create a mock StackOneTool for testing."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.parameters = MagicMock()
    tool.parameters.properties = properties or {}
    return tool


class TestStackOneAdkTool:
    def test_name_and_description(self):
        mock_tool = _make_mock_tool(name="calendly_list_events", description="List Calendly events")
        adk_tool = StackOneAdkTool(mock_tool)
        assert adk_tool.name == "calendly_list_events"
        assert adk_tool.description == "List Calendly events"

    def test_declaration_with_parameters(self):
        mock_tool = _make_mock_tool(
            name="calendly_list_events",
            description="List events",
            properties={
                "page_size": {"type": "integer", "description": "Number of results", "nullable": True},
                "status": {"type": "string", "description": "Filter by status", "nullable": False},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.name == "calendly_list_events"
        assert decl.description == "List events"
        assert decl.parameters is not None
        assert "page_size" in decl.parameters.properties
        assert "status" in decl.parameters.properties
        assert decl.parameters.required == ["status"]

    def test_declaration_empty_properties(self):
        mock_tool = _make_mock_tool(properties={})
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.name == "test_tool"
        assert decl.parameters is None

    def test_declaration_no_required_fields(self):
        mock_tool = _make_mock_tool(
            properties={
                "page_size": {"type": "integer", "nullable": True},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.parameters is not None
        assert not decl.parameters.required

    @pytest.mark.asyncio
    async def test_run_async_success(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = {"data": [{"id": "1", "name": "Event"}]}

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={"page_size": 10}, tool_context=tool_context)

        assert result == {"data": [{"id": "1", "name": "Event"}]}
        mock_tool.execute.assert_called_once_with({"page_size": 10})

    @pytest.mark.asyncio
    async def test_run_async_wraps_non_dict_result(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = "plain string result"

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={}, tool_context=tool_context)

        assert result == {"result": "plain string result"}

    @pytest.mark.asyncio
    async def test_run_async_handles_exception(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.side_effect = RuntimeError("API connection failed")

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={}, tool_context=tool_context)

        assert "error" in result
        assert "API connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_run_async_concurrent_execution(self):
        """Verify multiple tools can execute concurrently via run_in_executor."""
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = {"ok": True}

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()

        results = await asyncio.gather(
            adk_tool.run_async(args={"a": 1}, tool_context=tool_context),
            adk_tool.run_async(args={"b": 2}, tool_context=tool_context),
            adk_tool.run_async(args={"c": 3}, tool_context=tool_context),
        )

        assert len(results) == 3
        assert all(r == {"ok": True} for r in results)
        assert mock_tool.execute.call_count == 3
