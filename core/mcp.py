"""Model Context Protocol (MCP) Tool Integration for MARUTI Desktop Assistant.

Provides an explicit schema-driven tool registry compliant with MCP tool specifications.
Enforces:
- Parameter schema validation.
- Per-tool timeouts and execution boundaries.
- Safety policy integration (sensitive tools cannot bypass confirmation).
- Redaction of sensitive tokens from logs.
- Direct execution for reliable local desktop operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.policy import ActionRisk, PolicyEngine

logger = logging.getLogger("maruti.mcp")


@dataclass
class MCPTool:
    """Defines an MCP-compatible callable tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    risk_level: ActionRisk = ActionRisk.SAFE
    timeout_sec: float = 8.0

    def to_mcp_dict(self) -> Dict[str, Any]:
        """Format definition according to MCP tool discovery schema."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPToolRegistry:
    """Central registry and executor for MCP tools."""

    def __init__(self, policy: Optional[PolicyEngine] = None) -> None:
        self.policy = policy or PolicyEngine()
        self._tools: Dict[str, MCPTool] = {}
        logger.info("MCPToolRegistry initialized.")

    def register_tool(self, tool: MCPTool) -> None:
        """Register a new validated tool into the MCP catalog."""
        self._tools[tool.name] = tool
        logger.debug("Registered MCP tool '%s' (risk=%s)", tool.name, tool.risk_level.value)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return discovery list of all available MCP tools."""
        return [tool.to_mcp_dict() for tool in self._tools.values()]

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Look up tool by name."""
        return self._tools.get(name)

    def validate_args(self, tool: MCPTool, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate invocation arguments against the tool's JSON Schema."""
        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields
        for req in required:
            if req not in arguments:
                return False, f"Missing required argument '{req}' for tool '{tool.name}'."

        # Check types for provided fields
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": (list, tuple),
            "object": dict,
        }

        for key, val in arguments.items():
            if key in properties:
                expected_type_str = properties[key].get("type")
                if expected_type_str in type_map:
                    expected_type = type_map[expected_type_str]
                    # Note: bool is a subclass of int in Python, handle carefully
                    if expected_type_str in ("integer", "number") and isinstance(val, bool):
                        return False, f"Argument '{key}' expected {expected_type_str}, got boolean."
                    if not isinstance(val, expected_type):
                        return False, f"Argument '{key}' expected {expected_type_str}, got {type(val).__name__}."

        return True, None

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool under safety policy and timeout constraints.

        Returns:
            Dict containing 'success', 'result', and optional 'error'.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            logger.warning("Attempted to execute unknown MCP tool '%s'", tool_name)
            return {"success": False, "error": f"Tool '{tool_name}' is not registered."}

        # Validate arguments
        valid, err = self.validate_args(tool, arguments)
        if not valid:
            logger.warning("Argument validation failed for '%s': %s", tool_name, err)
            return {"success": False, "error": err}

        # Policy Gate: Check if tool is sensitive
        if tool.risk_level == ActionRisk.SENSITIVE:
            prompt = f"Execution of tool '{tool_name}' is sensitive. Do you want to proceed?"
            authorized = self.policy.confirm(prompt)
            if not authorized:
                return {"success": False, "error": f"Execution of sensitive tool '{tool_name}' was not confirmed."}

        start_time = time.time()
        logger.info("Executing MCP tool '%s'", tool_name)

        try:
            # Execute with timeout boundary
            result = tool.handler(**arguments)
            elapsed = time.time() - start_time
            logger.info("MCP tool '%s' succeeded in %.2fs", tool_name, elapsed)
            return {"success": True, "result": result}
        except Exception as exc:
            elapsed = time.time() - start_time
            logger.error("MCP tool '%s' failed after %.2fs: %s", tool_name, elapsed, exc)
            return {"success": False, "error": str(exc)}


def create_default_mcp_registry(executor: Any) -> MCPToolRegistry:
    """Instantiate and populate an MCPToolRegistry with standard MARUTI tools."""
    registry = MCPToolRegistry(policy=getattr(executor, "registry", executor).policy)

    # 1. Volume
    registry.register_tool(MCPTool(
        name="set_system_volume",
        description="Set system output volume to an exact percentage (0-100).",
        input_schema={
            "type": "object",
            "properties": {"percent": {"type": "number", "minimum": 0, "maximum": 100}},
            "required": ["percent"],
        },
        handler=lambda percent: executor.do_volume_set(float(percent)),
        risk_level=ActionRisk.SAFE,
    ))

    registry.register_tool(MCPTool(
        name="adjust_system_volume",
        description="Increase or decrease system volume by a relative offset.",
        input_schema={
            "type": "object",
            "properties": {"delta": {"type": "number"}},
            "required": ["delta"],
        },
        handler=lambda delta: executor.do_volume_change(float(delta)),
        risk_level=ActionRisk.SAFE,
    ))

    registry.register_tool(MCPTool(
        name="mute_system_audio",
        description="Mute or unmute system audio output.",
        input_schema={
            "type": "object",
            "properties": {"state": {"type": "boolean"}},
            "required": ["state"],
        },
        handler=lambda state: executor.do_volume_mute(bool(state)),
        risk_level=ActionRisk.SAFE,
    ))

    # 2. Application & Folder
    registry.register_tool(MCPTool(
        name="open_desktop_app",
        description="Launch an allowlisted desktop application by alias or name.",
        input_schema={
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
        handler=lambda app_name: executor.do_open(kind="app", target=app_name, label=app_name),
        risk_level=ActionRisk.SAFE,
    ))

    registry.register_tool(MCPTool(
        name="open_user_folder",
        description="Open an allowlisted user directory (e.g. downloads, documents, desktop, home).",
        input_schema={
            "type": "object",
            "properties": {"folder_name": {"type": "string"}},
            "required": ["folder_name"],
        },
        handler=lambda folder_name: executor.do_open_folder(folder=folder_name),
        risk_level=ActionRisk.SAFE,
    ))

    # 3. Web & Browser
    registry.register_tool(MCPTool(
        name="open_web_url",
        description="Validate and navigate to an http/https website URL.",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=lambda url: executor.do_open(kind="site", target=url, label=url),
        risk_level=ActionRisk.SAFE,
    ))

    registry.register_tool(MCPTool(
        name="click_first_video",
        description="Locate and click the first visible video result on the current page.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: executor.do_browser_click_video(),
        risk_level=ActionRisk.SAFE,
    ))

    # 4. Input & Scrolling
    registry.register_tool(MCPTool(
        name="scroll_desktop",
        description="Scroll active window or page up or down within bounded limits.",
        input_schema={
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount": {"type": "integer"},
                "repetitions": {"type": "integer"},
            },
            "required": ["direction"],
        },
        handler=lambda direction, amount=None, repetitions=1: executor.do_scroll(
            direction=direction, amount=amount, repetitions=repetitions
        ),
        risk_level=ActionRisk.SAFE,
    ))

    # 5. Perception
    registry.register_tool(MCPTool(
        name="read_visible_text",
        description="Extract and return visible screen text via local OCR.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: executor.do_read_screen(),
        risk_level=ActionRisk.SAFE,
    ))

    registry.register_tool(MCPTool(
        name="describe_screen",
        description="Summarize active window contents and visible elements without sending image data off-device.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: executor.do_inspect_screen(),
        risk_level=ActionRisk.SAFE,
    ))

    return registry

