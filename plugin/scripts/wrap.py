#!/usr/bin/env python3
"""Command wrapper entry point. Delegates to crux.hooks.wrap.

Invoked by the PreToolUse rewrite as `python3 wrap.py '<command>'`. The filename
must stay `wrap.py` so the gate's recursion guard matches the rewritten command.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.hooks.wrap import main

if __name__ == "__main__":
    main()
