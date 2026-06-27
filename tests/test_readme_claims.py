"""Guards that the README's compression claims can never drift from reality.

The savings table and the "See it in action" example in README.md are not
hand-maintained numbers — they are generated from the shipped fixtures by
``tools/generate_demo.py`` running the *real* compression pipeline. These tests
fail if the README ever advertises a number the fixtures don't actually deliver,
which is exactly the failure mode that would burn trust at launch.

Regenerate after any change to the fixtures, processors, or reducer::

    python tools/generate_demo.py
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import generate_demo as gd  # noqa: E402
from crux import config, core  # noqa: E402

PYTEST_FIXTURE = os.path.join(gd.FIXTURES_DIR, "pytest_output.txt")


def _read_readme() -> str:
    with open(gd.README) as f:
        return f.read()


def test_savings_table_matches_fixtures() -> None:
    """The table in README.md must equal a fresh generation from the fixtures."""
    try:
        table = gd.render_table(gd.measure())
        assert gd.update_readme(table, check=True), (
            "README savings table is stale — run: python tools/generate_demo.py"
        )
    finally:
        os.environ.pop("CRUX_PROFILE", None)
        config.reload()


def test_readme_never_overclaims() -> None:
    """Every percentage printed in the table is one the fixtures actually hit."""
    try:
        rows = gd.measure()
        readme = _read_readme()
        for r in rows:
            # The generated table is the source of these, but assert explicitly
            # so a hand-edit that inflates a number is caught.
            assert f"{r['default_pct']}%" in readme
            assert f"{r['budget_pct']}%" in readme
            # Sanity: the budget profile is never worse than the default.
            assert r["budget_pct"] >= r["default_pct"]
    finally:
        os.environ.pop("CRUX_PROFILE", None)
        config.reload()


def test_hero_example_is_literal_output() -> None:
    """The "After" block in README.md is exactly what Crux produces for the fixture."""
    os.environ.pop("CRUX_PROFILE", None)
    config.reload()
    with open(PYTEST_FIXTURE) as f:
        raw = f.read()
    produced = core.compress("pytest -v", raw).compressed
    readme = _read_readme()
    assert produced in readme, (
        "README 'See it in action' block no longer matches real output — "
        "update it to the output of: "
        'crux benchmark "pytest -v" --stdin < examples/fixtures/pytest_output.txt'
    )
    # And the error guarantee the example is selling: both failures survive.
    assert "test_env_override" in produced
    assert "test_transaction_rollback" in produced
    assert "501 tests passed" in produced
