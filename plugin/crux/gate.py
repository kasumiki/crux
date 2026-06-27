"""Compressibility gate: decide whether a command's output should be wrapped.

Pure decision logic shared by every integration (the Claude PreToolUse hook, the
Antigravity AfterTool hook, and ``crux explain``). It answers one question —
"is this command safe and worthwhile to compress?" — without doing any I/O.

Compressible-pattern compilation is lazy: the processor registry is consulted on
first use and cached, so ``import crux.gate`` stays cheap and free of import cycles.
"""

from __future__ import annotations

import os
import re

from .chain_utils import CHAIN_SPLIT_RE, split_chain

# Explicit opt-out: env CRUX_BYPASS=1 (session-wide) or a `# crux:raw` command marker.
_RAW_MARKER_RE = re.compile(r"#\s*crux:\s*raw\b")


def _is_bypassed(command: str) -> bool:
    """True if the user explicitly opted out of compression for this command."""
    if os.environ.get("CRUX_BYPASS", "").lower() in ("1", "true", "yes"):
        return True
    return bool(_RAW_MARKER_RE.search(command))


# --- Lazily-built compressible patterns (sourced from the processor registry) ---
_compressible_src: list[str] | None = None
_compressible_re: list[re.Pattern[str]] | None = None


def _patterns() -> tuple[list[str], list[re.Pattern[str]]]:
    """Return (source_patterns, compiled_patterns), building once on first call."""
    global _compressible_src, _compressible_re  # noqa: PLW0603
    if _compressible_src is None or _compressible_re is None:
        from .processors import collect_hook_patterns  # noqa: PLC0415

        _compressible_src = collect_hook_patterns()
        _compressible_re = [re.compile(p) for p in _compressible_src]
    return _compressible_src, _compressible_re


def reset_pattern_cache() -> None:
    """Drop the cached patterns so the next call rebuilds (used after config reload)."""
    global _compressible_src, _compressible_re  # noqa: PLW0603
    _compressible_src = None
    _compressible_re = None


# Trailing pipe stages that are safe to wrap. Stripped before exclusion checks so
# `git log | head -30` or `pip list | grep torch` still compress; the full original
# command (pipe included) is what actually runs.
_SAFE_TRAILING_PIPE_RE = re.compile(
    r"\s*\|\s*("
    r"head(\s+-[n]?\s*\d+|\s+-\d+)*"
    r"|tail(\s+[-+]?\d+|\s+-[nf]\s*\d+)*"
    r"|wc(\s+-[lwc])*"
    r"|grep(\s+-[viEcwnHr])*\s+\S+"
    r"|sort(\s+-[rnktu](\s+\d+)?)*"
    r"|uniq(\s+-[cd])*"
    r"|cut(\s+-[fd]\s*\S+)+"
    r")\s*$"
)

# Streaming / follow / watch commands never terminate on their own; wrapping them
# would buffer forever (wrap.py only flushes after the child exits).
_STREAMING_EXCLUDED_PATTERNS = [
    r"^\s*watch\b",
    r"\s--follow(=|\s|$)",
    r"^\s*tail\b[^|]*\s-[a-zA-Z]*[fF]\b",
    r"^\s*journalctl\b[^|]*\s-[a-zA-Z]*f\b",
    r"\b(kubectl|oc)\b[^|]*\blogs\b[^|]*\s-[a-zA-Z]*f\b",
    r"\bdocker\b[^|]*\blogs\b[^|]*\s-[a-zA-Z]*f\b",
    r"^\s*docker\s+stats\b(?![^|]*--no-stream)",
    r"^\s*docker(\s+compose|-compose)\s+up\b(?![^|]*\s-d\b)",
    r"\s--watch(=|\s|$)",
    r"\s--watchAll\b",
    r"^\s*(npx\s+)?vitest\b(?![^|]*\brun\b)",
]

# Commands that must never be wrapped (whole-command check for single commands;
# chains delegate to the per-segment list below).
EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",  # unquoted pipe (complex pipelines)
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*ssh\s+(?:-\S+\s+)*\S+\s*$",  # interactive ssh (no remote command)
    r"^\s*rsync\b.*\S+:\S+",  # remote rsync (host:path)
    r"(?:^|\s)crux\s",  # never wrap the crux CLI itself
    # Recursion guard: our rewrite is `python3 <…>wrap.py '<cmd>'`. Match wrap.py
    # only in script-execution position so `cat wrap.py` stays wrappable.
    r"(?:^|\s)(?:\S*/)?(?:python\d?(?:\.\d+)*|node|ruby|sh|bash|zsh|perl)\s+"
    r"(?:-\S+\s+)*\S*wrap\.py\b",
    r"^\s*\.?\S*/?wrap\.py\b",
    r"<\(",  # process substitution
    r"^\s*sudo\b",
    r"^\s*env\s+\S+=",  # env VAR=val prefix
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|ruby|perl|ghci|deno|php|lua|R|bash|sh|zsh)"
    r"\s+(?:-\S*i\S*|--interactive)(\s|$)",  # interactive REPLs even with args
    *_STREAMING_EXCLUDED_PATTERNS,
]

COMPILED_EXCLUDED = [re.compile(p) for p in EXCLUDED_PATTERNS]

# Strip a leading path prefix so '/usr/bin/git status' matches as 'git status',
# './node_modules/.bin/jest' as 'jest', etc.
_PATH_PREFIX_RE = re.compile(r"^(\S*/)(?=\S)")

# Constructs that break naive chain splitting / per-segment execution.
_DANGEROUS_CONSTRUCTS = ("$(", "`", "<<")

# Per-segment checks applied inside a &&/; chain.
_SEGMENT_EXCLUDED_PATTERNS = [
    r"(?<!['\"])\|(?!['\"])",
    r"<\(",
    r"^\s*sudo\b",
    r"^\s*(vi|vim|nano|emacs|code)\b",
    r"^\s*ssh\s+(?:-\S+\s+)*\S+\s*$",
    r"^\s*rsync\b.*\S+:\S+",
    r"^\s*env\s+\S+=",
    r"(?:^|\s)crux\s",
    r"(?:^|\s)(?:\S*/)?(?:python\d?(?:\.\d+)*|node|ruby|sh|bash|zsh|perl)\s+"
    r"(?:-\S+\s+)*\S*wrap\.py\b",
    r"^\s*\.?\S*/?wrap\.py\b",
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|bash|sh|zsh|ruby|irb|pry|gdb|lldb"
    r"|mongo|mongosh|redis-cli|psql|mysql|sqlite3|php|perl|lua|R)\s*$",  # bare REPL
    r"^\s*(python\d?(?:\.\d+)*|ipython|node|ruby|perl|ghci|deno|php|lua|R|bash|sh|zsh)"
    r"\s+(?:-\S*i\S*|--interactive)(\s|$)",
    *_STREAMING_EXCLUDED_PATTERNS,
]

_COMPILED_SEGMENT_EXCLUDED = [re.compile(p) for p in _SEGMENT_EXCLUDED_PATTERNS]


def _normalize_cmd(cmd: str) -> str:
    """Strip a leading path prefix for pattern matching."""
    return _PATH_PREFIX_RE.sub("", cmd)


def _has_unquoted_construct(cmd: str, constructs: tuple[str, ...]) -> bool:
    """True if any of ``constructs`` appears outside single/double quotes.

    Rejects top-level $(), backticks, or heredocs that break chain splitting;
    occurrences inside quoted strings (e.g. a commit message) are tolerated.
    """
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n and cmd[i] != quote:
                if cmd[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            if i < n:
                i += 1
            continue
        for c in constructs:
            if cmd.startswith(c, i):
                return True
        i += 1
    return False


def _has_output_redirection(cmd: str) -> bool:
    """True if an unquoted output redirection (>, >>, 2>, &>) is present.

    Quote-aware; ignores ``->`` and ``=>`` and any ``>`` inside quotes.
    """
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n and cmd[i] != quote:
                if cmd[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            if i < n:
                i += 1
            continue
        if ch == ">":
            prev = cmd[i - 1] if i > 0 else ""
            if prev not in ("-", "="):
                return True
        i += 1
    return False


def _is_segment_safe(segment: str) -> bool:
    """True if a single chain segment has no dangerous constructs.

    Checks the raw segment and its path-stripped form so /usr/bin/vim,
    ./python, .venv/bin/sudo, etc. are still caught.
    """
    if _has_output_redirection(segment):
        return False
    norm = _normalize_cmd(segment)
    return not any(p.search(segment) or p.search(norm) for p in _COMPILED_SEGMENT_EXCLUDED)


def _is_chain_compressible(command: str) -> bool:
    """Whether a &&/; chain is compressible.

    Every segment must be safe; at least one must be compressible. A safe
    trailing pipe is only stripped from the last segment.
    """
    segments = split_chain(command)
    if not segments:
        return False

    _, compiled = _patterns()
    has_compressible = False
    for i, seg in enumerate(segments):
        check_seg = _SAFE_TRAILING_PIPE_RE.sub("", seg) if i == len(segments) - 1 else seg
        if not _is_segment_safe(check_seg):
            return False
        norm_seg = _normalize_cmd(check_seg)
        if any(p.search(check_seg) or p.search(norm_seg) for p in compiled):
            has_compressible = True
    return has_compressible


def is_compressible(command: str) -> bool:
    """Whether ``command``'s output should be compressed.

    Safe trailing pipes are stripped before exclusion checks; chains (&&, ;) are
    validated per-segment; ``||`` chains are always rejected.
    """
    cmd = command.strip()
    if not cmd:
        return False

    if _is_bypassed(cmd):
        return False

    if re.search(r"(?<!['\"])\|\|(?!['\"])", cmd):
        return False

    if _has_unquoted_construct(cmd, _DANGEROUS_CONSTRUCTS):
        return False

    # Detect chains before stripping pipes so mid-chain pipes aren't lost.
    if CHAIN_SPLIT_RE.search(cmd):
        return _is_chain_compressible(cmd)

    if _has_output_redirection(cmd):
        return False

    check_cmd = _SAFE_TRAILING_PIPE_RE.sub("", cmd)
    norm_cmd = _normalize_cmd(check_cmd)
    if any(p.search(check_cmd) or p.search(norm_cmd) for p in COMPILED_EXCLUDED):
        return False
    _, compiled = _patterns()
    return any(p.search(check_cmd) or p.search(norm_cmd) for p in compiled)


def _matched_exclusion(check_cmd: str, norm_cmd: str) -> str | None:
    """Return the source regex of the first matching exclusion, if any."""
    for src, pattern in zip(EXCLUDED_PATTERNS, COMPILED_EXCLUDED, strict=False):
        if pattern.search(check_cmd) or pattern.search(norm_cmd):
            return src
    return None


def _matched_compressible(check_cmd: str, norm_cmd: str) -> list[str]:
    """Return source regexes of all compressible patterns that match."""
    sources, compiled = _patterns()
    return [
        src
        for src, pattern in zip(sources, compiled, strict=False)
        if pattern.search(check_cmd) or pattern.search(norm_cmd)
    ]


def explain_decision(command: str) -> dict:
    """Explain whether ``command`` would be wrapped, and why.

    Mirrors ``is_compressible`` step-for-step but returns a structured record for
    ``crux explain``. Keys: command, compressible, reason, excluded_by,
    matched_patterns, is_chain.
    """
    result = {
        "command": command,
        "compressible": False,
        "reason": "",
        "excluded_by": None,
        "matched_patterns": [],
        "is_chain": False,
    }
    cmd = command.strip()
    if not cmd:
        result["reason"] = "empty command"
        return result

    if _is_bypassed(cmd):
        result["reason"] = "bypassed (CRUX_BYPASS env or '# crux:raw' marker)"
        result["excluded_by"] = "bypass"
        return result

    if re.search(r"(?<!['\"])\|\|(?!['\"])", cmd):
        result["reason"] = "contains '||' (error-recovery chains are not wrapped)"
        result["excluded_by"] = r"||"
        return result

    if _has_unquoted_construct(cmd, _DANGEROUS_CONSTRUCTS):
        result["reason"] = "contains unquoted $(), backtick, or heredoc"
        result["excluded_by"] = "dangerous shell construct"
        return result

    if CHAIN_SPLIT_RE.search(cmd):
        result["is_chain"] = True
        compressible = _is_chain_compressible(cmd)
        result["compressible"] = compressible
        seen: list[str] = []
        for seg in split_chain(cmd):
            check_seg = _SAFE_TRAILING_PIPE_RE.sub("", seg)
            norm_seg = _normalize_cmd(check_seg)
            for p in _matched_compressible(check_seg, norm_seg):
                if p not in seen:
                    seen.append(p)
        result["matched_patterns"] = seen
        result["reason"] = (
            "chain with at least one compressible, all-safe segment"
            if compressible
            else "chain has an unsafe segment or no compressible segment"
        )
        return result

    if _has_output_redirection(cmd):
        result["reason"] = "contains output redirection (>, >>, 2>, &>)"
        result["excluded_by"] = "output redirection"
        return result

    check_cmd = _SAFE_TRAILING_PIPE_RE.sub("", cmd)
    norm_cmd = _normalize_cmd(check_cmd)
    excl = _matched_exclusion(check_cmd, norm_cmd)
    if excl is not None:
        result["reason"] = "matched an exclusion pattern"
        result["excluded_by"] = excl
        return result

    matched = _matched_compressible(check_cmd, norm_cmd)
    result["matched_patterns"] = matched
    result["compressible"] = bool(matched)
    result["reason"] = (
        "matched a compressible processor pattern"
        if matched
        else "no processor pattern matched (not wrapped)"
    )
    return result
