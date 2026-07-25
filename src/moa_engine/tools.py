from abc import ABC, abstractmethod
import asyncio
from typing import Any, Dict, List, Optional

from moa_engine.domain import Action, Tool


class BaseTool(ABC):
    """Abstract base class for tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema describing expected arguments for the tool."""
        pass

    def to_tool(self) -> Tool:
        """Convert BaseTool instance to Tool dataclass specification."""
        return Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool logic asynchronously and return a string result."""
        pass


class ToolRegistry:
    """Registry for managing and executing tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """Return list of Tool specifications for all registered tools."""
        return [tool.to_tool() for tool in self._tools.values()]

    async def execute(self, action: Action) -> str:
        """Execute an Action using the registered tool."""
        tool = self.get(action.tool_name)
        if not tool:
            return f"Error: Tool '{action.tool_name}' not found."
        try:
            return await tool.execute(**action.arguments)
        except Exception as e:
            return f"Error executing tool '{action.tool_name}': {e}"


class TerminalExecutionTool(BaseTool):
    """Tool to execute shell commands asynchronously in a subprocess."""

    @property
    def name(self) -> str:
        return "terminal_execution"

    @property
    def description(self) -> str:
        return "Выполняет shell-команду в терминале и возвращает результат (stdout/stderr)."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell-команда для выполнения в системе",
                }
            },
            "required": ["command"],
        }

    async def execute(self, command: str, **kwargs: Any) -> str:
        """Asynchronously execute shell command and return stdout or stderr."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(stderr_str)

            result = "\n".join(output_parts).strip()
            if not result:
                result = f"Command completed with exit code {proc.returncode}"
            return result
        except Exception as e:
            return f"Command execution error: {e}"
