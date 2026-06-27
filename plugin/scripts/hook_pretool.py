#!/usr/bin/env python3
"""PreToolUse hook entry point (Claude Code). Delegates to crux.hooks.pretool.

Invoked by the Claude plugin via ${CLAUDE_PLUGIN_ROOT}/scripts/hook_pretool.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.hooks.pretool import main

if __name__ == "__main__":
    main()
