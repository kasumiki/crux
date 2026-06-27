"""Token accounting for budgeting and stats.

Uses a character-ratio heuristic by default (no model dependency). A real
tokenizer can be registered with ``set_counter`` for exact budgets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_counter: Callable[[str], int] | None = None


def set_counter(fn: Callable[[str], int] | None) -> None:
    """Register a tokenizer (e.g. a model's). Pass None to revert to the heuristic."""
    global _counter  # noqa: PLW0603
    _counter = fn


def estimate_tokens(text: str, chars_per_token: float | None = None) -> int:
    """Estimate the token count of ``text``.

    Prefers a registered tokenizer; otherwise falls back to ``len / chars_per_token``
    (``chars_per_token`` defaults to the configured value).
    """
    if not text:
        return 0
    if _counter is not None:
        try:
            return _counter(text)
        except Exception:  # noqa: S110 — a bad tokenizer must never break compression
            pass
    if chars_per_token is None:
        from . import config  # noqa: PLC0415

        chars_per_token = config.get("chars_per_token")
    return max(1, round(len(text) / chars_per_token))
