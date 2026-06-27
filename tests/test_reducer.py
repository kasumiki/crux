"""Tests for the importance model, token accounting, and budget reducer."""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin")
)

from crux import tokens
from crux.importance import Importance, classify_line
from crux.reducer import reduce_to_budget
from crux.tokens import estimate_tokens


class TestImportance:
    def test_critical_errors(self):
        for line in (
            "error: cannot find symbol",
            '  File "app.py", line 42, in main',
            "ValueError: bad input",
            "FAILED tests/test_x.py::test_foo",
            "failed to connect to host",
            "error[E0382]: borrow of moved value",
            "src/app.c:10:5: error: expected ';'",
        ):
            assert classify_line(line) == Importance.CRITICAL, line

    def test_not_critical_summaries(self):
        # Summary counts must NOT be force-kept as CRITICAL.
        assert classify_line("3 passed, 0 failed") < Importance.CRITICAL
        assert classify_line("0 errors, 0 warnings") < Importance.CRITICAL

    def test_high(self):
        assert classify_line("warning: unused variable x") == Importance.HIGH
        assert classify_line("-    old_line()") == Importance.HIGH

    def test_noise(self):
        assert classify_line("  45%|=====>   | 12/27") == Importance.NOISE
        assert classify_line("") == Importance.NOISE
        assert classify_line("\x1b[2K\x1b[0m") == Importance.NOISE

    def test_low_and_medium(self):
        assert classify_line("Downloading torch (700 MB)") == Importance.LOW
        assert classify_line("just some ordinary output line") == Importance.MEDIUM


class TestTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_monotonic(self):
        assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)

    def test_pluggable_counter(self):
        tokens.set_counter(lambda _t: 7)
        try:
            assert estimate_tokens("anything") == 7
        finally:
            tokens.set_counter(None)

    def test_bad_counter_falls_back(self):
        tokens.set_counter(lambda _t: 1 / 0)
        try:
            assert estimate_tokens("x" * 40, chars_per_token=4) == 10
        finally:
            tokens.set_counter(None)


class TestReducer:
    def test_no_op_when_under_budget(self):
        text = "a\nb\nc"
        assert reduce_to_budget(text, 1000, chars_per_token=4) == text

    def test_no_op_when_budget_zero(self):
        text = "x" * 4000
        assert reduce_to_budget(text, 0) == text

    def test_preserves_errors_at_tiny_budget(self):
        lines = [f"Compiling module_{i:03d}" for i in range(300)]
        lines[150] = "error: undefined reference to `frobnicate`"
        reduced = reduce_to_budget("\n".join(lines), 50, chars_per_token=4)
        assert "frobnicate" in reduced
        assert estimate_tokens(reduced, 4) < estimate_tokens("\n".join(lines), 4)

    def test_drops_noise_keeps_order_and_footer(self):
        lines = []
        for i in range(120):
            lines.append(f"  {i}%|===>  | step {i}" if i % 2 else f"result item {i}")
        reduced = reduce_to_budget("\n".join(lines), 80, chars_per_token=4)
        assert "[crux] reduced to ~80 token budget" in reduced
        assert "elided" in reduced
        # Kept lines stay in original order.
        kept = [ln for ln in reduced.split("\n") if ln.startswith("result item")]
        nums = [int(ln.split()[-1]) for ln in kept]
        assert nums == sorted(nums)

    def test_all_critical_exceeds_budget_but_keeps_all(self):
        lines = [f"error: failure number {i}" for i in range(50)]
        reduced = reduce_to_budget("\n".join(lines), 10, chars_per_token=4)
        # Every error survives even though that exceeds the budget.
        for i in range(50):
            assert f"failure number {i}" in reduced


class TestBudgetIntegration:
    def teardown_method(self):
        os.environ.pop("CRUX_MAX_OUTPUT_TOKENS", None)
        from crux import config

        config.reload()

    def test_apply_budget_reduces_when_set(self):
        from crux import config, core

        os.environ["CRUX_MAX_OUTPUT_TOKENS"] = "100"
        config.reload()
        text = "\n".join(f"info: record {i}" for i in range(500))
        out = core.apply_budget(text)
        assert "[crux] reduced to ~100 token budget" in out
        assert len(out) < len(text)

    def test_apply_budget_noop_by_default(self):
        from crux import config, core

        config.reload()
        text = "\n".join(f"line {i}" for i in range(50))
        assert core.apply_budget(text) == text

    def test_compress_applies_budget_and_keeps_errors(self):
        from crux import config, core

        os.environ["CRUX_MAX_OUTPUT_TOKENS"] = "120"
        config.reload()
        lines = [f"processing item {i} of 600 ok" for i in range(600)]
        lines[590] = "error: fatal disk failure"
        result = core.compress("./run.sh", "\n".join(lines))
        assert result.compressed_len < result.original_len
        assert "fatal disk failure" in result.compressed
        assert estimate_tokens(result.compressed) <= 220

    def test_aggressive_profile_enables_budget(self):
        from crux import config

        os.environ["CRUX_PROFILE"] = "aggressive"
        config.reload()
        try:
            assert config.get("max_output_tokens") == 1500
        finally:
            os.environ.pop("CRUX_PROFILE", None)
            config.reload()
