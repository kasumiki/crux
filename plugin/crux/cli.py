"""CLI entry point for crux: version, stats, update, benchmark."""

import argparse
import json as json_mod
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

from crux import __version__
from crux.version_check import _fetch_latest_version, _parse_version


def _repo_dir():
    """Return the repository root directory (parent of crux/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_marketplace_managed(repo_dir: str) -> bool:
    """True if this install lives under a Claude Code plugin marketplace cache.

    Marketplace-managed installs live at
    ``~/.claude/plugins/cache/<marketplace>/crux`` (or the Windows
    %APPDATA% equivalent).  Self-updating those via git/tarball fights the
    marketplace, so ``crux update`` should defer to ``/plugin update``.
    """
    parts = [p.lower() for p in os.path.normpath(os.path.abspath(repo_dir)).split(os.sep)]
    return any(parts[i] == "plugins" and parts[i + 1] == "cache" for i in range(len(parts) - 1))


def _is_within_directory(directory: str, target: str) -> bool:
    """True if ``target`` resolves to a path inside ``directory``."""
    abs_dir = os.path.abspath(directory)
    abs_target = os.path.abspath(target)
    return os.path.commonpath([abs_dir]) == os.path.commonpath([abs_dir, abs_target])


def _safe_extractall(tar: "tarfile.TarFile", dest: str) -> None:
    """Extract a tarball, rejecting members that escape ``dest``.

    Prefers the stdlib ``data`` filter (Python 3.12+), which blocks path
    traversal, absolute paths, and special files.  Falls back to manual member
    validation on older interpreters.
    """
    try:
        tar.extractall(dest, filter="data")
        return
    except TypeError:
        pass  # `filter` kwarg unavailable (< 3.12) — validate manually

    for member in tar.getmembers():
        member_path = os.path.join(dest, member.name)
        if not _is_within_directory(dest, member_path):
            raise RuntimeError(f"Unsafe path in release tarball: {member.name!r}")
        if member.issym() or member.islnk():
            link_target = os.path.join(dest, os.path.dirname(member.name), member.linkname)
            if not _is_within_directory(dest, link_target):
                raise RuntimeError(f"Unsafe link in release tarball: {member.name!r}")
    tar.extractall(dest)  # noqa: S202


def cmd_version(_args):
    """Print current version."""
    print(f"crux v{__version__}")


def cmd_stats(args):
    """Display savings statistics, delegating to crux/stats.py."""
    from crux.stats import main as stats_main  # noqa: PLC0415

    # Patch sys.argv so stats.main() sees --json if passed
    original_argv = sys.argv
    sys.argv = ["stats"]
    if args.json:
        sys.argv.append("--json")
    try:
        stats_main()
    finally:
        sys.argv = original_argv


def cmd_update(_args):
    """Check for updates, then always refresh the local install.

    Remote fetch is best-effort: if it fails or matches the local version,
    we still re-run the installer so the Claude/Antigravity plugin caches stay
    in sync with the source files on disk.
    """
    repo_dir = _repo_dir()
    print(f"crux v{__version__}")

    if _is_marketplace_managed(repo_dir):
        print(
            "This install is managed by the Claude Code plugin marketplace.\n"
            "Run '/plugin update crux' from within Claude Code to update."
        )
        return

    print("Checking for updates...")
    latest = None
    try:
        latest = _fetch_latest_version(timeout=10)
    except urllib.error.HTTPError as e:
        print(f"Could not check remote: HTTP {e.code} (continuing with local refresh)")
    except Exception as e:
        print(f"Could not check remote: {e} (continuing with local refresh)")

    is_newer = False
    if latest is not None:
        try:
            is_newer = _parse_version(latest) > _parse_version(__version__)
        except (ValueError, TypeError):
            print(f"Could not compare versions: local={__version__}, remote={latest}")

    if is_newer:
        print(f"Update available: v{__version__} -> v{latest}")
        git_dir = os.path.join(repo_dir, ".git")
        if os.path.isdir(git_dir):
            _update_via_git(repo_dir, latest)
        else:
            _update_via_tarball(repo_dir, latest)
    elif latest is not None:
        print(f"Already on v{__version__} (no remote update).")

    targets = _detect_installed_targets()
    print(f"Refreshing plugin install for: {targets}...")
    install_script = os.path.join(repo_dir, "install.py")
    subprocess.run(  # noqa: S603
        [sys.executable, install_script, "--target", targets],
        check=True,
    )

    final_version = latest if is_newer else __version__
    print(f"Done. Running v{final_version}.")


def _detect_installed_targets():
    """Detect which platforms are currently installed and return the --target value."""
    h = os.path.expanduser("~")
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.join(h, "AppData", "Roaming"))
        claude_old = os.path.join(appdata, "claude", "plugins", "crux")
        claude_cache = os.path.join(
            appdata, "claude", "plugins", "cache", "crux-marketplace", "crux"
        )
        antigravity_dir = os.path.join(appdata, "gemini", "antigravity-cli", "plugins", "crux")
    else:
        claude_old = os.path.join(h, ".claude", "plugins", "crux")
        claude_cache = os.path.join(h, ".claude", "plugins", "cache", "crux-marketplace", "crux")
        antigravity_dir = os.path.join(h, ".gemini", "antigravity-cli", "plugins", "crux")

    claude_installed = os.path.isdir(claude_old) or os.path.isdir(claude_cache)
    antigravity_installed = os.path.isdir(antigravity_dir)

    if claude_installed and antigravity_installed:
        return "both"
    if antigravity_installed:
        return "antigravity"
    # Default to claude (most common, and safe even if dir was just cleaned)
    return "claude"


def _update_via_git(repo_dir, version):
    """Update using git fetch + merge tag into current branch."""
    print("Updating via git...")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "fetch", "--tags", "origin"],  # noqa: S607
        check=True,
    )
    # Try to merge the tag into the current branch (avoids detached HEAD)
    for tag in (f"v{version}", version):
        result = subprocess.run(  # noqa: S603
            ["git", "-C", repo_dir, "merge", tag, "--ff-only"],  # noqa: S607
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            print(f"Merged {tag} into current branch.")
            return
    # Fallback: pull latest main
    print(f"Warning: could not fast-forward to v{version}, pulling latest main")
    subprocess.run(  # noqa: S603
        ["git", "-C", repo_dir, "pull", "origin", "main"],  # noqa: S607
        check=True,
    )


def _update_via_tarball(repo_dir, version):
    """Update by downloading and extracting release tarball."""
    print("Downloading update...")

    # Try both tag formats: v1.2.0 and 1.2.0 (mirrors _update_via_git behavior)
    urls = [
        f"https://github.com/kasumiki/crux/archive/refs/tags/v{version}.tar.gz",
        f"https://github.com/kasumiki/crux/archive/refs/tags/{version}.tar.gz",
    ]

    tarball_data = None
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "crux"})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                tarball_data = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise

    if tarball_data is None:
        print(f"Error: could not download release v{version} from GitHub")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball_path = os.path.join(tmpdir, "release.tar.gz")
        with open(tarball_path, "wb") as f:
            f.write(tarball_data)

        with tarfile.open(tarball_path, "r:gz") as tar:
            _safe_extractall(tar, tmpdir)

        # Find the extracted directory (e.g., crux-1.2.0/)
        extracted = [
            d
            for d in os.listdir(tmpdir)
            if os.path.isdir(os.path.join(tmpdir, d)) and d != "release.tar.gz"
        ]
        if not extracted:
            print("Error: could not find extracted release directory")
            sys.exit(1)

        src_dir = os.path.join(tmpdir, extracted[0])

        # Overlay known source directories only (preserve .git, local config, etc.)
        overlay_items = (
            "crux",
            "installers",
            "scripts",
            ".claude-plugin",
            "hooks",
            "skills",
            "commands",
            "antigravity",
            "bin",
            "install.py",
            "pyproject.toml",
            "CLAUDE.md",
        )
        for item in overlay_items:
            s = os.path.join(src_dir, item)
            if not os.path.exists(s):
                continue
            d = os.path.join(repo_dir, item)
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        # Clean up legacy claude/ directory from v1.x
        legacy_claude = os.path.join(repo_dir, "claude")
        if os.path.isdir(legacy_claude):
            shutil.rmtree(legacy_claude)
            print("Removed legacy claude/ directory.")

        print("Files updated from tarball.")


def cmd_benchmark(args):
    """Benchmark compression on a real or dry-run command."""
    from crux import config  # noqa: PLC0415
    from crux.diffstat import format_summary, summarize  # noqa: PLC0415
    from crux.engine import CompressionEngine  # noqa: PLC0415

    command = args.command_str
    chars_per_token = config.get("chars_per_token")
    engine = CompressionEngine()

    if args.dry_run:
        # Dry-run: show which processor would handle it, without executing
        processor_name = "none"
        for p in engine.processors:
            if p.can_handle(command):
                processor_name = p.name
                break

        if args.format == "json":
            print(
                json_mod.dumps(
                    {
                        "command": command,
                        "processor": processor_name,
                        "dry_run": True,
                    }
                )
            )
        else:
            print()
            print("Crux Benchmark (dry-run)")
            print("=" * 40)
            print(f"Command:     {command}")
            print(f"Processor:   {processor_name}")
            print("(no execution — use without --dry-run to measure compression)")
        return

    if getattr(args, "stdin", False):
        # Compress pre-captured output piped on stdin; command is used only for
        # processor routing, not executed.
        raw_output = sys.stdin.read()
        exec_elapsed = 0.0
    else:
        # Execute the command and measure
        exec_start = time.monotonic()
        result = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=config.get("wrap_timeout"),
            check=False,
        )
        exec_elapsed = time.monotonic() - exec_start

        raw_output = result.stdout
        if result.stderr:
            raw_output += result.stderr

    from crux import core  # noqa: PLC0415

    compress_start = time.monotonic()
    compressed, processor_name, was_compressed = engine.compress(command, raw_output)
    compressed = core.apply_budget(compressed)  # reflect the token budget, if set
    compress_elapsed = time.monotonic() - compress_start

    orig_chars = len(raw_output)
    comp_chars = len(compressed)
    orig_tokens = max(1, round(orig_chars / chars_per_token)) if orig_chars > 0 else 0
    comp_tokens = max(1, round(comp_chars / chars_per_token)) if comp_chars > 0 else 0
    savings_pct = (orig_chars - comp_chars) / orig_chars * 100 if orig_chars > 0 else 0

    show_removed = getattr(args, "show_removed", False)
    diff_summary = summarize(raw_output, compressed) if show_removed else None

    if args.format == "json":
        payload = {
            "command": command,
            "processor": processor_name,
            "was_compressed": was_compressed,
            "original_chars": orig_chars,
            "compressed_chars": comp_chars,
            "original_tokens": orig_tokens,
            "compressed_tokens": comp_tokens,
            "savings_percent": round(savings_pct, 1),
            "exec_time_s": round(exec_elapsed, 3),
            "compress_time_s": round(compress_elapsed, 3),
        }
        if diff_summary is not None:
            payload["removed"] = diff_summary
        print(json_mod.dumps(payload))
    else:
        print()
        print("Crux Benchmark")
        print("=" * 40)
        print(f"Command:     {command}")
        print(f"Processor:   {processor_name}")
        print(f"Original:    {orig_chars:,} chars (~{orig_tokens:,} tokens)")
        print(f"Compressed:  {comp_chars:,} chars (~{comp_tokens:,} tokens)")
        print(f"Savings:     {savings_pct:.1f}%")
        print(f"Time:        {exec_elapsed:.2f}s (exec) + {compress_elapsed:.3f}s (compress)")
        if diff_summary is not None:
            print(format_summary(diff_summary))


def cmd_explain(args):
    """Explain how a command would be routed: processor, regex, exclusion."""
    from crux.chain_utils import extract_primary_command  # noqa: PLC0415
    from crux.engine import CompressionEngine  # noqa: PLC0415
    from crux.gate import explain_decision  # noqa: PLC0415

    command = args.command_str
    decision = explain_decision(command)

    # Which processor would handle the primary command (first match wins).
    primary = extract_primary_command(command)
    engine = CompressionEngine()
    processor_name = "none"
    processor_patterns: list[str] = []
    for p in engine.processors:
        if p.can_handle(primary):
            processor_name = p.name
            processor_patterns = list(p.hook_patterns)
            break

    if args.format == "json":
        print(
            json_mod.dumps(
                {
                    "command": command,
                    "primary_command": primary,
                    "compressible": decision["compressible"],
                    "reason": decision["reason"],
                    "excluded_by": decision["excluded_by"],
                    "matched_patterns": decision["matched_patterns"],
                    "is_chain": decision["is_chain"],
                    "processor": processor_name,
                    "processor_hook_patterns": processor_patterns,
                }
            )
        )
        return

    print()
    print("Crux Explain")
    print("=" * 40)
    print(f"Command:      {command}")
    if primary != command:
        print(f"Primary:      {primary}")
    print(f"Compressible: {'yes' if decision['compressible'] else 'no'}")
    print(f"Reason:       {decision['reason']}")
    if decision["excluded_by"]:
        print(f"Excluded by:  {decision['excluded_by']}")
    print(f"Processor:    {processor_name}")
    if decision["matched_patterns"]:
        print("Matched patterns:")
        for pat in decision["matched_patterns"]:
            print(f"  - {pat}")
    if processor_patterns and not decision["matched_patterns"]:
        print("Processor hook patterns:")
        for pat in processor_patterns:
            print(f"  - {pat}")


def cmd_config(args):
    """View or change configuration: show / get <key> / set <key> <value> / path."""
    from crux import config as _config_mod  # noqa: PLC0415
    from crux import data_dir  # noqa: PLC0415

    config_path = os.path.join(data_dir(), "config.json")

    if args.action == "path":
        print(config_path)
        return

    if args.action == "show":
        loaded = _config_mod._load_config()
        sources = loaded.get("_config_source", {})
        for key in sorted(_config_mod._DEFAULTS):
            print(f"  {key} = {loaded.get(key)!r}  [{sources.get(key, 'default')}]")
        return

    if args.action == "get":
        if not args.key:
            print("Usage: crux config get <key>", file=sys.stderr)
            sys.exit(1)
        _config_mod.reload()
        print(_config_mod.get(args.key))
        return

    # set
    if not args.key or args.value is None:
        print("Usage: crux config set <key> <value>", file=sys.stderr)
        sys.exit(1)
    if args.key not in _config_mod._DEFAULTS:
        print(f"Unknown config key: {args.key}", file=sys.stderr)
        sys.exit(1)
    coerced = _config_mod._coerce_value(_config_mod._DEFAULTS[args.key], args.value)
    if coerced is None:
        print(f"Cannot interpret {args.value!r} as {args.key}", file=sys.stderr)
        sys.exit(1)

    data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                data = json_mod.load(f)
            if not isinstance(data, dict):
                data = {}
        except (json_mod.JSONDecodeError, OSError):
            data = {}
    data[args.key] = coerced
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json_mod.dump(data, f, indent=2)
        f.write("\n")
    _config_mod.reload()
    print(f"Set {args.key} = {coerced!r} in {config_path}")


def cmd_doctor(_args):
    """Diagnose the install: Python, data dir, CLI, processors, hooks, config."""
    from crux import __version__, config, data_dir  # noqa: PLC0415
    from crux.processors import discover_processors  # noqa: PLC0415

    print(f"\nCrux Doctor (v{__version__})")
    print("=" * 40)

    def check(label, ok, detail=""):
        mark = "OK  " if ok else "WARN"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))

    check("Python >= 3.10", sys.version_info >= (3, 10), f"{sys.version.split()[0]}")

    ddir = data_dir()
    writable = os.path.isdir(ddir) and os.access(ddir, os.W_OK)
    check("Data dir writable", writable, ddir)

    cli_path = shutil.which("crux")
    check("crux CLI on PATH", cli_path is not None, cli_path or "run install.py to add it")

    try:
        n = len(discover_processors())
        check("Processors discovered", n > 0, f"{n} processors")
    except Exception as exc:
        check("Processors discovered", False, str(exc))

    config.reload()
    check("Compression enabled", bool(config.get("enabled")), f"profile={config.get('profile')}")

    home = os.path.expanduser("~")
    settings = os.path.join(home, ".claude", "settings.json")
    registered = False
    if os.path.exists(settings):
        try:
            with open(settings) as f:
                enabled = json_mod.load(f).get("enabledPlugins", {})
            registered = any("crux" in k for k in enabled)
        except (json_mod.JSONDecodeError, OSError):
            pass
    check("Claude plugin enabled", registered, "" if registered else "not found in settings.json")

    antigravity_dir = os.path.join(home, ".gemini", "antigravity-cli", "plugins", "crux")
    check("Antigravity plugin installed", os.path.isdir(antigravity_dir), antigravity_dir)

    audit = os.path.join(ddir, "audit.log")
    if os.path.exists(audit):
        try:
            with open(audit) as f:
                last = f.readlines()[-1].strip()
            print(f"\n  Last audit: {last[:120]}")
        except (OSError, IndexError):
            pass
    print()


def cmd_init_processor(args):
    """Scaffold a custom processor into the user processors directory."""
    from crux import config, data_dir  # noqa: PLC0415

    raw = args.name.strip().lower()
    slug = "".join(c if c.isalnum() else "_" for c in raw).strip("_")
    if not slug:
        print("Invalid processor name", file=sys.stderr)
        sys.exit(1)
    class_name = "".join(part.capitalize() for part in slug.split("_")) + "Processor"

    target_dir = config.get("user_processors_dir") or os.path.join(data_dir(), "processors")
    target_dir = os.path.expanduser(str(target_dir))
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"{slug}.py")
    if os.path.exists(path):
        print(f"Refusing to overwrite existing {path}", file=sys.stderr)
        sys.exit(1)

    template = f'''"""Custom Crux processor: {slug}."""

import re

from crux.processors.base import Processor


class {class_name}(Processor):
    # 10-19 override · 20-29 core · 30-49 specialized · 50-69 content · 999 generic
    priority = 40
    hook_patterns = [r"^{slug}\\b"]

    @property
    def name(self) -> str:
        return "{slug}"

    def can_handle(self, command: str) -> bool:
        return bool(re.search(r"\\b{slug}\\b", command))

    def process(self, command: str, output: str) -> str:
        # Return compressed output. Return ``output`` unchanged to skip compression.
        return output
'''
    with open(path, "w") as f:
        f.write(template)
    print(f"Created {path}")
    print(
        f"Edit it, then it auto-loads on the next command. Verify with: crux explain '{slug} ...'"
    )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="crux",
        description="Crux: compress verbose tool outputs to save tokens",
    )
    subparsers = parser.add_subparsers(dest="command")

    # version
    subparsers.add_parser("version", help="Show current version")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show savings statistics")
    stats_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # update
    subparsers.add_parser("update", help="Check for and apply updates")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark compression on a command")
    bench_parser.add_argument("command_str", help="Command to benchmark (quote if needed)")
    bench_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    bench_parser.add_argument(
        "--dry-run", action="store_true", help="Show processor match without executing"
    )
    bench_parser.add_argument(
        "--show-removed",
        action="store_true",
        help="Show a line/byte breakdown of what compression removed",
    )
    bench_parser.add_argument(
        "--stdin",
        action="store_true",
        help="Compress output piped on stdin instead of executing the command",
    )

    # explain
    explain_parser = subparsers.add_parser(
        "explain", help="Explain how a command would be routed/excluded"
    )
    explain_parser.add_argument("command_str", help="Command to explain (quote if needed)")
    explain_parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # doctor
    subparsers.add_parser("doctor", help="Diagnose the install, hooks, and config")

    # config
    config_parser = subparsers.add_parser("config", help="View or change configuration")
    config_parser.add_argument("action", choices=["show", "get", "set", "path"], help="What to do")
    config_parser.add_argument("key", nargs="?", help="Config key (for get/set)")
    config_parser.add_argument("value", nargs="?", help="New value (for set)")

    # init-processor
    init_parser = subparsers.add_parser(
        "init-processor", help="Scaffold a custom processor from a template"
    )
    init_parser.add_argument("name", help="Processor name (e.g. 'mytool')")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "version": cmd_version,
        "stats": cmd_stats,
        "update": cmd_update,
        "benchmark": cmd_benchmark,
        "explain": cmd_explain,
        "doctor": cmd_doctor,
        "config": cmd_config,
        "init-processor": cmd_init_processor,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
