"""Tests for platform detection and per-host I/O adapters."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.platforms import (
    AntigravityAdapter,
    ClaudeAdapter,
    Platform,
    detect_platform,
    format_aftertool_deny,
    format_pretool_rewrite,
    get_command,
    get_tool_output,
)


class TestDetectPlatform:
    def test_claude_events(self):
        for ev in ("PreToolUse", "PostToolUse", "SessionStart"):
            assert detect_platform({"hook_event_name": ev}) is Platform.CLAUDE_CODE

    def test_antigravity_events(self):
        for ev in ("BeforeTool", "AfterTool"):
            assert detect_platform({"hook_event_name": ev}) is Platform.ANTIGRAVITY_CLI

    def test_fallback_heuristics(self):
        assert detect_platform({"tool_input": {}, "tool_response": {}}) is Platform.ANTIGRAVITY_CLI
        assert detect_platform({"tool_name": "Bash"}) is Platform.CLAUDE_CODE

    def test_unknown(self):
        assert detect_platform({}) is Platform.UNKNOWN


class TestExtractCommand:
    def test_claude_command(self):
        data = {"tool_input": {"command": "git status"}}
        assert get_command(data, Platform.CLAUDE_CODE) == "git status"

    def test_antigravity_command_or_cmd(self):
        assert get_command({"tool_input": {"cmd": "ls"}}, Platform.ANTIGRAVITY_CLI) == "ls"
        assert get_command({"tool_input": {"command": "ls"}}, Platform.ANTIGRAVITY_CLI) == "ls"

    def test_missing_command(self):
        assert get_command({"tool_input": {}}, Platform.CLAUDE_CODE) is None
        assert get_command({}, Platform.UNKNOWN) is None


class TestExtractOutput:
    def test_claude_has_no_captured_output(self):
        assert get_tool_output({"tool_input": {"command": "ls"}}, Platform.CLAUDE_CODE) is None

    def test_antigravity_llm_content_string(self):
        data = {"tool_response": {"llmContent": "hello"}}
        assert get_tool_output(data, Platform.ANTIGRAVITY_CLI) == "hello"

    def test_antigravity_llm_content_list(self):
        data = {"tool_response": {"llmContent": ["a", "b"]}}
        assert get_tool_output(data, Platform.ANTIGRAVITY_CLI) == "a\nb"

    def test_antigravity_output_fallback(self):
        data = {"tool_response": {"output": "world"}}
        assert get_tool_output(data, Platform.ANTIGRAVITY_CLI) == "world"

    def test_antigravity_empty(self):
        assert get_tool_output({"tool_response": {}}, Platform.ANTIGRAVITY_CLI) is None


class TestFormatResponses:
    def test_pretool_rewrite(self):
        out = format_pretool_rewrite("python3 wrap.py 'git status'")
        assert out["hookSpecificOutput"]["updatedInput"]["command"].endswith("'git status'")
        assert out["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_aftertool_deny(self):
        out = format_aftertool_deny("compressed")
        assert out == {"decision": "deny", "reason": "compressed"}

    def test_adapter_names(self):
        assert ClaudeAdapter().name == "claude_code"
        assert AntigravityAdapter().name == "antigravity_cli"
