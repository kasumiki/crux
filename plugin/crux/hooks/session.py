#!/usr/bin/env python3
"""SessionStart hook: display crux stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.tracker import SavingsTracker


def main():
    # Read Claude Code's session_id from the stdin JSON payload.
    cc_session = None
    try:
        raw = sys.stdin.read()
        if raw.strip():
            cc_session = json.loads(raw).get("session_id")
    except (json.JSONDecodeError, ValueError):
        pass

    message = None
    try:
        tracker = SavingsTracker(session_id=cc_session)
        message = tracker.format_stats_message()
        tracker.close()
    except Exception:  # noqa: S110
        pass

    if message is None:
        sys.exit(0)

    # Best-effort update check (1s HTTP timeout keeps us under Claude's 3s budget).
    try:
        from crux.version_check import check_for_update  # noqa: PLC0415

        update_msg = check_for_update()
        if update_msg:
            message = f"{message} | {update_msg}"
    except Exception:  # noqa: S110
        pass

    json.dump({"systemMessage": message}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
