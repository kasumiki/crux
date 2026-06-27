"""Platform detection and per-host I/O adapters.

Adding a third host means adding one adapter module + a registry entry here;
the engine, gate, and processors stay untouched.
"""

from __future__ import annotations

from enum import Enum

from .antigravity import AntigravityAdapter
from .base import PlatformAdapter
from .claude import ClaudeAdapter


class Platform(Enum):
    CLAUDE_CODE = "claude_code"
    ANTIGRAVITY_CLI = "antigravity_cli"
    UNKNOWN = "unknown"


_ADAPTERS: dict[Platform, PlatformAdapter] = {
    Platform.CLAUDE_CODE: ClaudeAdapter(),
    Platform.ANTIGRAVITY_CLI: AntigravityAdapter(),
}


def detect_platform(input_data: dict) -> Platform:
    """Detect the host from the hook event name or payload shape."""
    event = input_data.get("hook_event_name", "")
    if event in ("PreToolUse", "PostToolUse", "SessionStart"):
        return Platform.CLAUDE_CODE
    if event in ("BeforeTool", "AfterTool"):
        return Platform.ANTIGRAVITY_CLI
    # Fallback heuristics: Antigravity carries tool_response, Claude carries tool_name.
    if "tool_input" in input_data and "tool_response" in input_data:
        return Platform.ANTIGRAVITY_CLI
    if "tool_name" in input_data:
        return Platform.CLAUDE_CODE
    return Platform.UNKNOWN


def get_command(input_data: dict, platform: Platform) -> str | None:
    """Extract the command string from hook input."""
    adapter = _ADAPTERS.get(platform)
    return adapter.extract_command(input_data) if adapter else None


def get_tool_output(input_data: dict, platform: Platform) -> str | None:
    """Extract captured tool output from hook input (Antigravity AfterTool only)."""
    adapter = _ADAPTERS.get(platform)
    return adapter.extract_output(input_data) if adapter else None


def format_pretool_rewrite(new_command: str, permission_decision: str = "allow") -> dict:
    """Format a PreToolUse response that rewrites the command (Claude Code)."""
    return ClaudeAdapter.format_rewrite(new_command, permission_decision)


def format_aftertool_deny(compressed_output: str) -> dict:
    """Format an AfterTool response that replaces output (Antigravity CLI)."""
    return AntigravityAdapter.format_deny(compressed_output)


__all__ = [
    "AntigravityAdapter",
    "ClaudeAdapter",
    "Platform",
    "PlatformAdapter",
    "detect_platform",
    "format_aftertool_deny",
    "format_pretool_rewrite",
    "get_command",
    "get_tool_output",
]
