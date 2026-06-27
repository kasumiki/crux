"""Platform adapter protocol.

An adapter encapsulates how one host (Claude Code, Antigravity, …) delivers a
command and tool output to a hook. The compression engine and gate are
platform-agnostic; only this thin layer knows the per-host JSON shapes.

The two hosts differ in *lifecycle* (Claude rewrites the command before it runs;
Antigravity replaces output after), so response formatting stays host-specific
on each adapter rather than being forced behind one signature.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformAdapter(Protocol):
    """How a platform exposes the command and (optionally) captured output."""

    name: str

    def extract_command(self, input_data: dict) -> str | None:
        """Return the shell command from the hook payload, or None."""
        ...

    def extract_output(self, input_data: dict) -> str | None:
        """Return already-captured tool output, or None if the host captures none."""
        ...
