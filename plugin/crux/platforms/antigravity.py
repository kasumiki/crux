"""Antigravity CLI adapter: the AfterTool hook replaces output after it runs."""

from __future__ import annotations


class AntigravityAdapter:
    """Antigravity integrates by replacing already-captured output (post-execution)."""

    name = "antigravity_cli"

    def extract_command(self, input_data: dict) -> str | None:
        tool_input = input_data.get("tool_input", {})
        cmd = tool_input.get("command") or tool_input.get("cmd")
        return str(cmd) if cmd is not None else None

    def extract_output(self, input_data: dict) -> str | None:
        response = input_data.get("tool_response", {})
        content = response.get("llmContent", response.get("output", ""))
        if isinstance(content, list):
            return "\n".join(str(c) for c in content)
        return str(content) if content else None

    @staticmethod
    def format_deny(compressed_output: str) -> dict:
        """Build an AfterTool response that swaps in the compressed output."""
        return {"decision": "deny", "reason": compressed_output}
