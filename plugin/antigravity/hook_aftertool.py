#!/usr/bin/env python3
"""AfterTool hook entry point (Antigravity CLI). Delegates to crux.hooks.aftertool.

Invoked by the Antigravity plugin via ${extensionPath}/antigravity/hook_aftertool.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux.hooks.aftertool import main

if __name__ == "__main__":
    main()
