#!/usr/bin/env python3
"""See Crux compress real command output — no LLM, no network, pure parsing.

Runs the sample fixtures in ``fixtures/`` through the *real* compression pipeline
(``crux.core.compress`` — the same path the Claude Code / Antigravity hooks use)
and prints before/after token counts, then shows one full before/after so you can
see exactly what the model would receive.

    python3 examples/demo.py

No install needed — this script adds the bundled ``plugin/`` package to its path.
To measure your own commands instead, use the CLI: ``crux benchmark "<command>"``.
"""

from __future__ import annotations

import os
import sys

# Make the bundled package importable straight from a fresh clone (no pip install).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugin"))

from crux import config, core  # noqa: E402
from crux.tokens import estimate_tokens  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# (label, command, fixture) — labels describe the real fixture contents.
CASES = [
    ("pytest (503 tests, 2 failures)", "pytest -v", "pytest_output.txt"),
    ("npm install (847 packages)", "npm install", "npm_install.txt"),
    ("kubectl get pods (49 pods)", "kubectl get pods", "kubectl_pods.txt"),
    ("git diff (5 files)", "git diff", "large_git_diff.txt"),
    ("terraform plan (15 changes)", "terraform plan", "terraform_plan.txt"),
]

RULE = "=" * 74


def _read(fixture: str) -> str:
    with open(os.path.join(FIXTURES, fixture)) as f:
        return f.read()


def _compress(command: str, raw: str, budget: int = 0) -> str:
    """Compress with an optional token budget, leaving global config untouched."""
    if budget:
        os.environ["CRUX_MAX_OUTPUT_TOKENS"] = str(budget)
        config.reload()
    try:
        return core.compress(command, raw).compressed
    finally:
        if budget:
            os.environ.pop("CRUX_MAX_OUTPUT_TOKENS", None)
            config.reload()


def main() -> None:
    print(f"\n{RULE}\n  Crux Compression Demo — real pipeline, deterministic, offline\n{RULE}\n")
    print(f"  {'Command':<34}{'Raw':>9}{'Crux':>9}{'Saved':>8}   Processor")
    print(f"  {'-' * 34}{'-' * 9:>9}{'-' * 9:>9}{'-' * 8:>8}   {'-' * 9}")

    total_raw = total_out = 0
    for label, command, fixture in CASES:
        raw = _read(fixture)
        result = core.compress(command, raw)
        rt, ot = estimate_tokens(raw), estimate_tokens(result.compressed)
        total_raw += rt
        total_out += ot
        saved = f"{round((1 - ot / rt) * 100)}%" if rt else "0%"
        print(f"  {label:<34}{rt:>9,}{ot:>9,}{saved:>8}   {result.processor}")

    saved_total = round((1 - total_out / total_raw) * 100) if total_raw else 0
    print(f"  {'-' * 34}{'-' * 9:>9}{'-' * 9:>9}{'-' * 8:>8}")
    print(f"  {'TOTAL':<34}{total_raw:>9,}{total_out:>9,}{str(saved_total) + '%':>8}\n")

    # Diffs/plans are mostly signal — show what a token budget buys on those two.
    print("  Diffs and plans are mostly signal, so they compress less by default.")
    print("  Set a budget (crux config set max_output_tokens 1500) and the reducer")
    print("  compresses those too, while errors always survive:\n")
    for label, command, fixture in CASES[3:]:
        raw = _read(fixture)
        rt = estimate_tokens(raw)
        ot = estimate_tokens(_compress(command, raw, budget=1500))
        print(f"    {label:<32}{rt:>7,} -> {ot:>5,} tokens   ({round((1 - ot / rt) * 100)}% saved)")

    # One full before/after so the numbers are concrete.
    pytest_raw = _read("pytest_output.txt")
    pytest_out = core.compress("pytest -v", pytest_raw).compressed
    raw_lines, out_lines = len(pytest_raw.splitlines()), len(pytest_out.splitlines())
    raw_tok, out_tok = estimate_tokens(pytest_raw), estimate_tokens(pytest_out)
    print(f"\n{RULE}\n  Live example — `pytest -v`, what the model actually receives\n{RULE}")
    print(f"\n  BEFORE: {raw_lines} lines, ~{raw_tok:,} tokens")
    print(f"  AFTER:  {out_lines} lines, ~{out_tok:,} tokens\n")
    for line in pytest_out.splitlines():
        print(f"  | {line}")

    print(f"\n{RULE}")
    print('  Measure your own commands:  crux benchmark "<command>"')
    print(f"{RULE}\n")


if __name__ == "__main__":
    main()
