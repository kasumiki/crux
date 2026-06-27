#!/usr/bin/env python3
"""Installer / Uninstaller for Crux extension.

Cross-platform: macOS, Linux, Windows.

Usage:
    python3 install.py --target claude        # Install for Claude Code
    python3 install.py --target antigravity   # Install for Antigravity CLI
    python3 install.py --target both          # Install for both
    python3 install.py --link                 # Use symlinks (development mode)
    python3 install.py --uninstall            # Remove from both platforms
    python3 install.py --uninstall --target claude  # Remove from Claude Code only
"""

import argparse
import os
import platform
import sys

# Make `crux` importable: it lives under plugin/ in the repo, or alongside this
# file in a flattened ~/.crux core install.
_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, "plugin"), _here):
    if os.path.isdir(os.path.join(_p, "crux")):
        sys.path.insert(0, _p)
        break

from installers import antigravity, claude  # noqa: E402
from installers.common import (  # noqa: E402
    install_cli,
    install_core,
    uninstall_cli,
    uninstall_core,
    uninstall_data_dir,
)


def main():
    parser = argparse.ArgumentParser(
        description="Install or uninstall Crux extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 install.py --target claude          Install for Claude Code
  python3 install.py --target antigravity     Install for Antigravity CLI
  python3 install.py --target both            Install for both
  python3 install.py --link --target claude   Dev mode (symlinks)
  python3 install.py --uninstall              Uninstall from both (default)
  python3 install.py --uninstall --target claude  Uninstall from Claude only
  python3 install.py --uninstall --keep-data  Uninstall but keep stats DB
""",
    )
    parser.add_argument(
        "--target",
        choices=["claude", "antigravity", "both"],
        default=None,
        help="Target platform (default: claude for install, both for uninstall)",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Use symlinks instead of copies (development mode)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the extension completely",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="When uninstalling, keep the ~/.crux data directory (stats, config)",
    )
    args = parser.parse_args()

    if args.uninstall:
        # Default to 'both' for uninstall so nothing is left behind
        target = args.target or "both"
        print(f"Uninstalling crux from: {target}")

        print("\n--- CLI ---")
        uninstall_cli()

        if target in ("claude", "both"):
            claude.uninstall()
        if target in ("antigravity", "both"):
            antigravity.uninstall()

        print("\n--- Core ---")
        uninstall_core()

        if not args.keep_data:
            print("\n--- Data ---")
            uninstall_data_dir()

        print("\nUninstallation complete.")
        return

    # --- Install ---
    target = args.target or "claude"
    print(f"Installing crux for: {target}")
    print(f"Platform: {platform.system()}")
    print(f"Mode: {'symlink' if args.link else 'copy'}")

    if target in ("claude", "both"):
        claude.install(use_symlink=args.link)
    if target in ("antigravity", "both"):
        antigravity.install(use_symlink=args.link)

    install_core(use_symlink=args.link)

    print("\n--- CLI ---")
    install_cli(use_symlink=args.link)

    print("\nInstallation complete.")


if __name__ == "__main__":
    main()
