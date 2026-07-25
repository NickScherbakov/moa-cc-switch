import pytest
from typing import Any

from moa_engine.domain import Action, Tool
from moa_engine.tools import BaseTool, TerminalExecutionTool, ToolRegistry


class DummyTool(BaseTool):
    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A dummy tool for testing."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"param": {"type": "string"}},
            "required": ["param"],
        }

    async def execute(self, param: str, **kwargs: Any) -> str:
        return f"Dummy result: {param}"


def test_tool_and_action_dataclasses():
    tool = Tool(name="t1", description="desc1", input_schema={"type": "object"})
    assert tool.name == "t1"
    assert tool.description == "desc1"
    assert tool.input_schema == {"type": "object"}

    action = Action(tool_name="t1", arguments={"key": "val"})
    assert action.tool_name == "t1"
    assert action.arguments == {"key": "val"}


def test_basetool_to_tool():
    dummy = DummyTool()
    tool_spec = dummy.to_tool()
    assert isinstance(tool_spec, Tool)
    assert tool_spec.name == "dummy_tool"
    assert tool_spec.description == "A dummy tool for testing."
    assert tool_spec.input_schema == {
        "type": "object",
        "properties": {"param": {"type": "string"}},
        "required": ["param"],
    }


@pytest.mark.asyncio
async def test_tool_registry():
    registry = ToolRegistry()
    dummy = DummyTool()
    registry.register(dummy)

    assert registry.get("dummy_tool") is dummy
    assert registry.get("non_existent") is None

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "dummy_tool"

    # Test execution
    action = Action(tool_name="dummy_tool", arguments={"param": "test_val"})
    res = await registry.execute(action)
    assert res == "Dummy result: test_val"

    # Test unknown tool execution
    unknown_action = Action(tool_name="unknown", arguments={})
    err_res = await registry.execute(unknown_action)
    assert "not found" in err_res


@pytest.mark.asyncio
async def test_terminal_execution_tool():
    term_tool = TerminalExecutionTool()
    assert term_tool.name == "terminal_execution"
    assert term_tool.to_tool().name == "terminal_execution"

    # Execute echo command
    res = await term_tool.execute(command="python -c \"print('hello from terminal')\"")
    assert "hello from terminal" in res
