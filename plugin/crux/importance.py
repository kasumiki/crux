"""Tool-agnostic importance classification of output lines.

A single signal of "what matters" in command output, independent of which tool
produced it. The budget reducer keeps high-importance lines and drops noise
first, with the guarantee that CRITICAL lines (errors, tracebacks) are never
dropped.
"""

from __future__ import annotations

import re
from enum import IntEnum


class Importance(IntEnum):
    NOISE = 0  # blank, ANSI-only, progress bars, spinners
    LOW = 1  # info/debug/notes, build progress, version banners
    MEDIUM = 2  # summaries, counts, file paths, ordinary prose
    HIGH = 3  # warnings, diff +/- content, changed files
    CRITICAL = 4  # errors, tracebacks, failures — never dropped


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# CRITICAL — real errors and failures (kept even at a zero budget). Deliberately
# excludes summary counts like "0 failed" / "no errors".
_CRITICAL_RE = re.compile(
    r"(?:^|\s)(error|fatal|panic)\s*[:!\[]"  # error: / fatal: / panic! / error[
    r"|\btraceback\b|\bsegfault\b|\bcore dumped\b"
    r"|^\s*[\w.]*(Error|Exception)\b\s*:"  # TypeError: / app.FooException:
    r"|^\s*File \"[^\"]+\", line \d+"  # python stack frame
    r"|^\s+at \w"  # js/java stack frame
    r"|error\[[A-Za-z]?\d+\]"  # rustc/tsc: error[E0382]
    r"|:\d+:\d+:\s*(error|fatal)\b"  # gcc/clang: file:line:col: error
    r"|^\s*(FAILED|FAIL)\b|[✗✘×]",  # test status  # noqa: RUF001
    re.IGNORECASE,
)

# NOISE — progress and decoration (dropped first).
_NOISE_RE = re.compile(
    r"\d+%"
    r"|[█▓▒░⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣿]"  # progress/spinner glyphs
    r"|={3,}>|\[=+>?\s*\]"  # ascii progress bars
    r"|\b\d+(\.\d+)?\s?[KMG]i?B/s\b"  # transfer rates
    r"|^\s*(Receiving|Resolving|Counting|Compressing|Unpacking) objects",
)

# HIGH — warnings, diff content, changed files.
_HIGH_RE = re.compile(
    r"\bwarn(ing|ings)?\b|[⚠]"
    r"|^[+-](?![+-])"  # a diff add/remove line (not the +++/--- header)
    r"|^\s*[MADRCU]\s+\S"  # git status / name-status codes
    r"|\b\d+\s+(failed|errors?)\b",
    re.IGNORECASE,
)

# LOW — informational chatter.
_LOW_RE = re.compile(
    r"\b(info|debug|note|notice|hint|deprecated)\b"
    r"|^\s*(Compiling|Downloading|Installing|Building|Fetching|Resolving|Collecting|"
    r"Requirement already satisfied|Using cached|Preparing|Updating)\b",
    re.IGNORECASE,
)

# MEDIUM — summaries, counts, paths (the default for ordinary content).
_MEDIUM_RE = re.compile(
    r"\b\d+\s+(passed|tests?|files?|warnings?|insertions?|deletions?|packages?|added|removed)\b"
    r"|^\s*(Total|Summary|Finished|Done|Success)\b"
    r"|\S+\.\w+:\d+",  # file:line references
    re.IGNORECASE,
)


def classify_line(line: str) -> Importance:
    """Classify a single output line by importance."""
    stripped = _ANSI_RE.sub("", line).strip()
    if not stripped:
        return Importance.NOISE
    if _CRITICAL_RE.search(line):
        return Importance.CRITICAL
    if _NOISE_RE.search(stripped):
        return Importance.NOISE
    if _HIGH_RE.search(line):
        return Importance.HIGH
    if _LOW_RE.search(stripped):
        return Importance.LOW
    if _MEDIUM_RE.search(stripped):
        return Importance.MEDIUM
    return Importance.MEDIUM
