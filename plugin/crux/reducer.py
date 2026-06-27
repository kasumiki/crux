"""Budget-aware reduction: compress text to a token budget by importance.

The reducer is Crux's final compression authority. Per-tool processors shape
output first; the reducer then enforces a token budget on *any* output by
keeping the highest-importance lines, with two guarantees:

- CRITICAL lines (errors, tracebacks) are never dropped — even if that means
  exceeding the budget.
- The result records, in a one-line footer, how much was elided.
"""

from __future__ import annotations

from .importance import Importance, classify_line
from .tokens import estimate_tokens

# Token allowance reserved for the elision footer so it rarely tips us over budget.
_FOOTER_RESERVE = 24


def reduce_to_budget(
    text: str,
    max_tokens: int,
    *,
    chars_per_token: float | None = None,
    context: int = 1,
) -> str:
    """Reduce ``text`` to roughly ``max_tokens`` tokens, preserving CRITICAL lines.

    Returns ``text`` unchanged when the budget is non-positive or already met.
    """
    if max_tokens <= 0 or not text:
        return text
    if estimate_tokens(text, chars_per_token) <= max_tokens:
        return text

    lines = text.split("\n")
    n = len(lines)
    levels = [classify_line(line) for line in lines]
    costs = [estimate_tokens(line, chars_per_token) for line in lines]

    # Guaranteed set: every CRITICAL line plus a little surrounding context.
    keep: set[int] = set()
    for i, level in enumerate(levels):
        if level >= Importance.CRITICAL:
            keep.update(range(max(0, i - context), min(n, i + context + 1)))

    used = sum(costs[i] for i in keep) + _FOOTER_RESERVE

    # Fill the remaining budget by importance, biased toward the head and tail
    # (where the orienting and concluding context usually lives).
    candidates = sorted(
        (i for i in range(n) if i not in keep and levels[i] > Importance.NOISE),
        key=lambda i: (-int(levels[i]), min(i, n - 1 - i)),
    )
    for i in candidates:
        if used + costs[i] <= max_tokens:
            keep.add(i)
            used += costs[i]

    if len(keep) >= n:
        return text  # nothing was actually dropped

    return _render(lines, costs, keep, max_tokens)


def _render(lines: list[str], costs: list[int], keep: set[int], max_tokens: int) -> str:
    """Emit kept lines in original order with gap markers, plus an elision footer."""
    out: list[str] = []
    gap = 0
    elided_tokens = 0

    def flush_gap() -> None:
        nonlocal gap
        if gap:
            out.append(f"  … {gap} line{'s' if gap != 1 else ''} elided …")
            gap = 0

    for i in range(len(lines)):
        if i in keep:
            flush_gap()
            out.append(lines[i])
        else:
            gap += 1
            elided_tokens += costs[i]
    flush_gap()

    elided = len(lines) - len(keep)
    out.append(
        f"[crux] reduced to ~{max_tokens} token budget: "
        f"kept {len(keep)}/{len(lines)} lines, elided ~{elided_tokens} tokens "
        f"({elided} dropped, errors preserved)"
    )
    return "\n".join(out)
