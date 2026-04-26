"""
Tool registry — maps role capabilities to callable tool handlers.

When the AgentDecisionLoop starts it calls ToolRegistry.get_tools_for_role()
to obtain the set of tools the LLM is allowed to invoke.  Each AgentTool is
converted to an LLM ToolDefinition (JSON Schema) before being sent to the
provider, then the LLM's tool_calls are resolved back to AgentTool.handler
for execution.

Role filtering uses simple case-insensitive substring matching against
required_roles.  An empty required_roles list means the tool is available to
all roles.

Lifecycle:
  1. ToolDefinitions (tool_definitions.py) call registry.register() once at
     import time.
  2. AgentEngineService passes the registry to each agent run.
  3. The decision loop calls get_tools_for_role() to build the per-run tool set.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentTool:
    """
    A tool available to the agent during a decision loop run.

    ``handler`` is the async callable that executes the tool and returns a
    JSON-serialisable result.  It receives the arguments dict produced by the
    LLM directly, so parameter names must match the JSON Schema exactly.

    ``required_roles`` is a list of role names that may call this tool.  An
    empty list means unrestricted (any role).  Matching is case-insensitive.
    """

    name: str
    description: str
    # JSON Schema for the tool parameters — sent verbatim to the LLM
    parameters: dict[str, Any]
    handler: Callable
    required_roles: list[str] = field(default_factory=list)


class ToolRegistry:
    """
    Registry of all tools available to agents.

    Thread-safety: register() is called once at module import time (single
    thread), and get_tools_for_role() is read-only, so no locking is needed.
    """

    def __init__(self) -> None:
        # name -> AgentTool, preserves insertion order (Python 3.7+)
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """
        Add a tool to the registry.  Overwrites any existing tool with the
        same name, which allows adapters to re-register after config reload.
        """
        if not tool.name:
            raise ValueError("AgentTool.name must not be empty")
        if tool.name in self._tools:
            logger.debug("Overwriting existing tool registration for '%s'", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool '%s'", tool.name)

    def get_tools_for_role(self, role: str) -> list[AgentTool]:
        """
        Return all tools accessible to the given role.

        A tool with an empty required_roles list is accessible to every role.
        Otherwise the role must appear in required_roles (case-insensitive).
        """
        if not role:
            raise ValueError("role must not be empty")
        role_lower = role.lower()
        return [
            t for t in self._tools.values()
            if not t.required_roles
            or role_lower in [r.lower() for r in t.required_roles]
        ]

    def get_tool(self, name: str) -> AgentTool | None:
        """Return the tool by name, or None if not registered."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return all registered tool names in insertion order."""
        return list(self._tools.keys())

    def build_executor(self) -> "RegistryToolExecutor":
        """
        Return a RegistryToolExecutor backed by this registry.

        The executor satisfies the interface expected by AgentDecisionLoop:
          await executor.execute(agent_id, tool_name, arguments, call_id)
        """
        return RegistryToolExecutor(self)

    def to_llm_definitions(self, role: str) -> list["ToolDefinition"]:
        """
        Return LLM-formatted ToolDefinition objects for the given role.

        Converts AgentTool (which carries a handler and required_roles metadata
        that the LLM doesn't need) to the lightweight ToolDefinition that the
        LLM adapter sends to the provider.

        Import is deferred to avoid a circular dependency between this module
        and the llm package.
        """
        from app.engine.llm.types import ToolDefinition  # deferred import

        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.parameters,
            )
            for tool in self.get_tools_for_role(role)
        ]

    def __len__(self) -> int:
        return len(self._tools)


@dataclass
class ToolExecutionResult:
    """
    The result of executing a single tool call.

    ``output`` is always a string so it can be inserted directly into the
    conversation as a "tool" role message.  Non-string results are serialised
    to JSON.  Errors are surfaced as ``success=False`` with the error message
    in ``output`` — this way the LLM can read the error and decide how to
    recover rather than having the run abort.
    """

    tool_name: str
    call_id: str
    output: str
    success: bool


class RegistryToolExecutor:
    """
    Tool executor that resolves tool names to AgentTool.handler calls.

    Satisfies the interface expected by AgentDecisionLoop:
      result = await executor.execute(agent_id, tool_name, arguments, call_id)

    AgentDecisionLoop accesses ``result.output`` and ``result.success``.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str,
    ) -> ToolExecutionResult:
        """
        Look up the tool by name and invoke its handler with the LLM-supplied
        arguments.  Returns a ToolExecutionResult regardless of success so the
        decision loop can always append a tool-result message.
        """
        tool = self._registry.get_tool(tool_name)
        if tool is None:
            logger.warning(
                "Agent %s called unknown tool '%s' (call_id=%s)",
                agent_id,
                tool_name,
                call_id,
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                call_id=call_id,
                output=f"Error: tool '{tool_name}' is not available.",
                success=False,
            )

        try:
            raw_result = await tool.handler(arguments)
        except Exception as exc:
            logger.warning(
                "Tool '%s' raised an exception for agent %s (call_id=%s): %s",
                tool_name,
                agent_id,
                call_id,
                exc,
                exc_info=True,
            )
            return ToolExecutionResult(
                tool_name=tool_name,
                call_id=call_id,
                output=f"Error executing {tool_name}: {exc}",
                success=False,
            )

        # Normalise output to a string that can be embedded in a message
        if isinstance(raw_result, str):
            output = raw_result
        else:
            try:
                output = json.dumps(raw_result, default=str)
            except (TypeError, ValueError):
                output = str(raw_result)

        logger.debug(
            "Tool '%s' succeeded for agent %s (call_id=%s, output_len=%d)",
            tool_name,
            agent_id,
            call_id,
            len(output),
        )
        return ToolExecutionResult(
            tool_name=tool_name,
            call_id=call_id,
            output=output,
            success=True,
        )
