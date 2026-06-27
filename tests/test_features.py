"""Tests for v3.0 features: profiles, bypass, and the new CLI subcommands."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crux import cli, config
from crux.gate import explain_decision, is_compressible


class TestProfiles:
    def teardown_method(self):
        for k in ("CRUX_PROFILE", "CRUX_MAX_DIFF_HUNK_LINES"):
            os.environ.pop(k, None)
        config.reload()

    def test_aggressive_applies(self):
        os.environ["CRUX_PROFILE"] = "aggressive"
        config.reload()
        assert config.get("max_diff_hunk_lines") == 30
        assert config.get("generic_truncate_threshold") == 100

    def test_conservative_applies(self):
        os.environ["CRUX_PROFILE"] = "conservative"
        config.reload()
        assert config.get("min_input_length") == 500
        assert config.get("max_log_entries") == 25

    def test_explicit_setting_beats_profile(self):
        os.environ["CRUX_PROFILE"] = "aggressive"
        os.environ["CRUX_MAX_DIFF_HUNK_LINES"] = "999"
        config.reload()
        assert config.get("max_diff_hunk_lines") == 999

    def test_balanced_keeps_defaults(self):
        os.environ["CRUX_PROFILE"] = "balanced"
        config.reload()
        assert config.get("max_diff_hunk_lines") == 50


class TestBypass:
    def test_raw_marker_bypasses(self):
        assert is_compressible("git status") is True
        assert is_compressible("git status # crux:raw") is False

    def test_env_bypasses(self, monkeypatch):
        monkeypatch.setenv("CRUX_BYPASS", "1")
        assert is_compressible("git status") is False

    def test_explain_reports_bypass(self):
        decision = explain_decision("git diff # crux:raw")
        assert decision["compressible"] is False
        assert decision["excluded_by"] == "bypass"


class TestCliFeatures:
    def test_config_set_then_get(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        config.reload()
        cli.cmd_config(types.SimpleNamespace(action="set", key="max_log_entries", value="3"))
        config.reload()
        assert config.get("max_log_entries") == 3
        assert (tmp_path / ".crux" / "config.json").exists()

    def test_config_set_rejects_unknown_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(SystemExit):
            cli.cmd_config(types.SimpleNamespace(action="set", key="nope", value="1"))

    def test_doctor_runs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        config.reload()
        cli.cmd_doctor(types.SimpleNamespace())
        out = capsys.readouterr().out
        assert "Crux Doctor" in out
        assert "Processors discovered" in out

    def test_init_processor_scaffolds(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        config.reload()
        cli.cmd_init_processor(types.SimpleNamespace(name="My Tool"))
        created = tmp_path / ".crux" / "processors" / "my_tool.py"
        assert created.exists()
        body = created.read_text()
        assert "class MyToolProcessor(Processor)" in body
        assert 'return "my_tool"' in body
