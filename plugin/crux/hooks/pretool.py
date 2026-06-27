#!/usr/bin/env python3
"""PreToolUse hook for Claude Code.

Reads JSON from stdin and, for compressible Bash commands, rewrites the command
to run through wrap.py. The compressibility decision lives in ``crux.gate``;
this file only does hook I/O. shlex.quote() guards against shell injection.
"""

import json
import logging
import os
import shlex
import sys

# Make the plugin root importable (scripts/ -> plugin root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.gate import is_compressible

_log = logging.getLogger("crux.hook_pretool")
_log.setLevel(logging.DEBUG)
if os.environ.get("CRUX_DEBUG", "").lower() in (
    "1",
    "true",
    "yes",
):
    from crux import data_dir as _data_dir

    _log_dir = _data_dir()
    os.makedirs(_log_dir, exist_ok=True)
    _handler = logging.FileHandler(os.path.join(_log_dir, "hook.log"))
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    _log.addHandler(_handler)
else:
    _log.addHandler(logging.NullHandler())


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as exc:
        _log.debug("Invalid JSON input: %s", exc)
        sys.exit(0)

    if input_data.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    if not command or not is_compressible(command):
        _log.debug("Not compressible: %r", command[:200])
        sys.exit(0)

    # crux/hooks/pretool.py -> plugin root (crux/ and scripts/ are siblings there)
    plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    wrap_py = os.path.join(plugin_root, "scripts", "wrap.py")
    if not os.path.isfile(wrap_py):
        _log.warning("wrap.py not found at %s", wrap_py)
        sys.exit(0)  # Fail open — don't break the command.

    # Propagate Claude Code's session_id so every compression in the session
    # shares one tracker session; embed it as an env prefix on the rewrite.
    cc_session = input_data.get("session_id", "")
    python = "python" if os.name == "nt" else "python3"
    session_prefix = f"CRUX_SESSION={shlex.quote(cc_session)} " if cc_session else ""
    new_command = f"{session_prefix}{python} {shlex.quote(wrap_py)} {shlex.quote(command)}"
    _log.debug("Rewriting: %r -> %r", command, new_command)

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": {"command": new_command},
            },
        },
        sys.stdout,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
