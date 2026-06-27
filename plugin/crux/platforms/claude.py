"""Claude Code adapter: the PreToolUse hook rewrites the command before it runs."""

from __future__ import annotations


class ClaudeAdapter:
    """Claude Code integrates by rewriting the Bash command (pre-execution)."""

    name = "claude_code"

    def extract_command(self, input_data: dict) -> str | None:
        cmd = input_data.get("tool_input", {}).get("command")
        return str(cmd) if cmd is not None else None

    def extract_output(self, input_data: dict) -> str | None:
        # Claude wraps the command and compresses what it produces; the hook
        # never receives pre-captured output.
        return None

    @staticmethod
    def format_rewrite(new_command: str, permission_decision: str = "allow") -> dict:
        """Build a PreToolUse response that replaces the command."""
        return {
            "hookSpecificOutput": {
                "permissionDecision": permission_decision,
                "updatedInput": {"command": new_command},
            }
        }
