# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] — Initial release

Crux is a context compiler for AI coding assistants: it compresses the verbose CLI output
your agent reads, so you spend fewer tokens while every error, diff, and stack trace survives.

### Core

- **Budget-aware compression with an importance model.** A tool-agnostic importance ranking
  (`crux/importance.py`, CRITICAL → NOISE) and a token-budget reducer (`crux/reducer.py`)
  compress *any* output — even from unknown tools — to fit `max_output_tokens`, dropping
  noise first and **guaranteeing errors/tracebacks are never dropped**, with a transparent
  elision footer. Pluggable token accounting (`crux/tokens.py`).
- **30+ specialized processors** for tool-aware shaping (git, docker, kubectl, terraform,
  helm, ansible, cargo, go, npm/pip, test runners, linters, cloud CLIs, and more), behind a
  priority-ordered engine with a generic fallback.
- **Two integrations** sharing one engine: a Claude Code PreToolUse hook (rewrites the
  command through a wrapper) and an Antigravity AfterTool hook (replaces output). A small
  `crux/platforms/` adapter layer makes a third host one module.

### CLI

- `crux stats` — token savings, per session and lifetime.
- `crux benchmark` / `crux explain` — measure compression / show routing.
- `crux doctor` — diagnose install, hooks, data dir, and config.
- `crux config` — `show` (with sources), `get`, `set`, `path`.
- `crux init-processor <name>` — scaffold a custom processor.
- `crux update` — check for and apply updates.

### Configuration

- `~/.crux/config.json` global config; `.crux.json` per-project overrides; `CRUX_<KEY>`
  environment variables.
- **Profiles** — `conservative` / `balanced` / `aggressive` preset bundles.
- **Token budget** — `max_output_tokens` caps any command's output (the `aggressive`
  profile sets 1500).
- **Per-command opt-out** — `# crux:raw` marker or `CRUX_BYPASS=1`.

### Packaging & quality

- pip-installable (`crux` console script) and installable as a Claude Code / Antigravity
  plugin; the shippable plugin is self-contained under `plugin/`.
- Apache-2.0. CI runs `ruff`, `mypy`, and the full test suite (880+ tests).
