"""Claude Code installer: registers Crux as a native plugin.

Registers the GitHub repo as a known marketplace and writes installed_plugins.json
in the format Claude Code expects.
"""

import json
import os

from .common import (
    HOOK_MARKER,
    IS_WINDOWS,
    SHARED_FILES,
    home,
    install_files,
    stamp_version,
    uninstall_dir,
)

CLAUDE_FILES = [
    *SHARED_FILES,
    # Plugin metadata
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    # Hooks (native plugin format — Claude Code reads these automatically)
    "hooks/hooks.json",
    # Scripts
    "scripts/__init__.py",
    "scripts/hook_pretool.py",
    "scripts/wrap.py",
    "scripts/hook_session.py",
    # Skills and commands
    "skills/crux-config/SKILL.md",
    "commands/crux-stats.md",
    # Plugin instructions
    "CLAUDE.md",
]

_MARKETPLACE_NAME = "crux-marketplace"
_PLUGIN_KEY = f"crux@{_MARKETPLACE_NAME}"
_GITHUB_REPO = "kasumiki/crux"


def _settings_dir():
    """Return Claude Code settings directory."""
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        return os.path.join(appdata, "claude")
    return os.path.join(home(), ".claude")


def _plugin_cache_dir(version):
    """Return the Claude Code plugin cache directory for crux.

    Claude Code stores plugins at .../cache/<marketplace>/<plugin>/<version>/.
    """
    return os.path.join(
        _settings_dir(),
        "plugins",
        "cache",
        _MARKETPLACE_NAME,
        "crux",
        version,
    )


def _marketplace_dir():
    """Return the marketplace directory for crux.

    Claude Code reads .claude-plugin/marketplace.json from this path to
    discover available plugins.  This mirrors the layout produced by
    ``/plugin marketplace add``.
    """
    return os.path.join(_settings_dir(), "plugins", "marketplaces", _MARKETPLACE_NAME)


def _settings_path():
    """Return path to Claude Code settings.json."""
    return os.path.join(_settings_dir(), "settings.json")


def _installed_plugins_path():
    """Return path to Claude Code's installed plugins registry."""
    return os.path.join(_settings_dir(), "plugins", "installed_plugins.json")


def _known_marketplaces_path():
    """Return path to Claude Code's known marketplaces registry."""
    return os.path.join(_settings_dir(), "plugins", "known_marketplaces.json")


def _hook_belongs_to_us(hook_entry):
    """Check if a hook entry (new format) belongs to crux."""
    for h in hook_entry.get("hooks", []):
        cmd = h.get("command", "")
        if HOOK_MARKER in cmd or "hook_pretool" in cmd or "hook_session" in cmd:
            return True
    return False


def _read_version():
    """Read the current crux version from crux/__init__.py."""
    from .common import _read_version as _rv  # noqa: PLC0415

    return _rv()


def _iso_now():
    """Return current UTC time in ISO 8601 format."""
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _register_plugin(marketplace_dir, cache_dir, version):
    """Register crux as a native Claude Code plugin.

    Registers the GitHub repo as a known marketplace (pointing
    ``installLocation`` at *marketplace_dir* so Claude Code can find
    ``.claude-plugin/marketplace.json``), writes the plugin entry in
    installed_plugins.json (v2 format, ``installPath`` → *cache_dir*),
    and enables it in settings.json.
    """
    plugins_dir = os.path.join(_settings_dir(), "plugins")
    os.makedirs(plugins_dir, exist_ok=True)
    now = _iso_now()

    # --- 1. Register marketplace in known_marketplaces.json ---
    km_path = _known_marketplaces_path()
    known = {}
    if os.path.exists(km_path):
        try:
            with open(km_path) as f:
                known = json.load(f)
        except (json.JSONDecodeError, ValueError):
            known = {}

    known[_MARKETPLACE_NAME] = {
        "source": {
            "source": "github",
            "repo": _GITHUB_REPO,
            "ref": "production",
        },
        "installLocation": marketplace_dir,
        "lastUpdated": now,
    }

    with open(km_path, "w") as f:
        json.dump(known, f, indent=2)
        f.write("\n")
    print("  REGISTERED marketplace in known_marketplaces.json")

    # --- 2. Update installed_plugins.json (v2 format) ---
    plugins_path = _installed_plugins_path()

    registry = {"version": 2, "plugins": {}}
    if os.path.exists(plugins_path):
        try:
            with open(plugins_path) as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("version") == 2:
                registry = data
        except (json.JSONDecodeError, ValueError):
            pass

    registry["plugins"][_PLUGIN_KEY] = [
        {
            "scope": "user",
            "installPath": cache_dir,
            "version": version,
            "installedAt": now,
            "lastUpdated": now,
        },
    ]

    with open(plugins_path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")
    print("  REGISTERED in installed_plugins.json")

    # --- 3. Enable in settings.json ---
    settings_path = _settings_path()
    settings = {}
    if os.path.exists(settings_path):
        # A corrupt/hand-edited settings.json must not abort installation —
        # fall back to an empty object (matching the unregister path's leniency).
        try:
            with open(settings_path) as f:
                settings = json.load(f)
            if not isinstance(settings, dict):
                settings = {}
        except (json.JSONDecodeError, ValueError, OSError):
            print("  WARNING: settings.json unreadable — recreating enabledPlugins")
            settings = {}

    enabled = settings.setdefault("enabledPlugins", {})
    enabled[_PLUGIN_KEY] = True

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("  ENABLED in settings.json (enabledPlugins)")


def _unregister_plugin():
    """Unregister crux from Claude Code's plugin system.

    Removes from known_marketplaces.json, installed_plugins.json,
    disables in enabledPlugins, and removes its hooks.
    """
    # --- 1. Remove from known_marketplaces.json ---
    km_path = _known_marketplaces_path()
    if os.path.exists(km_path):
        try:
            with open(km_path) as f:
                known = json.load(f)
            if _MARKETPLACE_NAME in known:
                del known[_MARKETPLACE_NAME]
                with open(km_path, "w") as f:
                    json.dump(known, f, indent=2)
                    f.write("\n")
                print("  REMOVED from known_marketplaces.json")
        except (json.JSONDecodeError, ValueError):
            pass

    # --- 2. Remove from installed_plugins.json ---
    plugins_path = _installed_plugins_path()
    if os.path.exists(plugins_path):
        try:
            with open(plugins_path) as f:
                data = json.load(f)

            changed = False
            if isinstance(data, dict) and isinstance(data.get("plugins"), dict):
                plugins = data["plugins"]
                for key in list(plugins):
                    if "crux" in key:
                        del plugins[key]
                        changed = True

            if changed:
                with open(plugins_path, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                print("  REMOVED from installed_plugins.json")
        except (json.JSONDecodeError, ValueError):
            pass

    # --- 3. Remove from enabledPlugins + clean legacy hooks from settings.json ---
    settings_path = _settings_path()
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)

        changed = False

        # Remove from enabledPlugins
        enabled = settings.get("enabledPlugins", {})
        for key in list(enabled):
            if "crux" in key:
                del enabled[key]
                changed = True
        if not enabled and "enabledPlugins" in settings:
            del settings["enabledPlugins"]

        # Remove our hooks from settings.json
        hooks = settings.get("hooks", {})
        for event in list(hooks):
            if not isinstance(hooks[event], list):
                continue
            original_len = len(hooks[event])
            hooks[event] = [entry for entry in hooks[event] if not _hook_belongs_to_us(entry)]
            if len(hooks[event]) != original_len:
                changed = True
            if not hooks[event]:
                del hooks[event]
        if not hooks and "hooks" in settings:
            del settings["hooks"]

        if changed:
            with open(settings_path, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")
            print("  REMOVED from settings.json")


def install(use_symlink=False):
    """Install Crux for Claude Code as a native plugin.

    This produces the same result as:
      /plugin marketplace add kasumiki/crux
      /plugin install crux

    Files are installed to the plugin cache directory (with version in the
    path), the GitHub repo is registered as a known marketplace, and the
    plugin is added to installed_plugins.json (v2 format) and enabledPlugins.
    """
    # Install files to the versioned plugin cache directory
    version = _read_version()
    cache_dir = _plugin_cache_dir(version)
    print(f"\n--- Claude Code (cache: {cache_dir}) ---")
    install_files(cache_dir, CLAUDE_FILES, use_symlink)

    # 3. Install files to the marketplace directory (for plugin discovery)
    mkt_dir = _marketplace_dir()
    print(f"--- Claude Code (marketplace: {mkt_dir}) ---")
    install_files(mkt_dir, CLAUDE_FILES, use_symlink)

    # 4. Stamp version in BOTH plugin.json and marketplace.json (in both dirs)
    version_files = [
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    ]
    stamp_version(cache_dir, version_files)
    stamp_version(mkt_dir, version_files)

    # 5. Register marketplace + plugin (marketplace dir for discovery, cache for runtime)
    _register_plugin(mkt_dir, cache_dir, version)

    print("  Plugin registered. Restart Claude Code, then /plugin to manage.")


def uninstall():
    """Uninstall Crux from Claude Code."""
    print("\n--- Claude Code ---")
    _unregister_plugin()

    # Remove entire marketplace cache directory (all versions)
    cache_root = os.path.join(
        _settings_dir(),
        "plugins",
        "cache",
        _MARKETPLACE_NAME,
    )
    if os.path.isdir(cache_root):
        uninstall_dir(cache_root)

    # Remove marketplace discovery directory
    mkt_dir = _marketplace_dir()
    if os.path.isdir(mkt_dir):
        uninstall_dir(mkt_dir)
