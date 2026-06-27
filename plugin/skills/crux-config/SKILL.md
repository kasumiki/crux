---
name: crux-config
description: "Configure and diagnose Crux compression settings. Use when the user asks about adjusting compression levels, checking processor status, debugging hook issues, or reviewing savings statistics."
---

# Crux Configuration & Diagnostics

## Check Status
Run `crux stats` to see compression statistics for the current and all sessions.
Run `crux doctor` to verify the install, hooks, data directory, and effective config.

## Configuration
Crux config lives in `~/.crux/config.json`, with per-project overrides in `.crux.json`.
Inspect and change it without hand-editing JSON:

```bash
crux config show            # effective values + where each came from
crux config get min_input_length
crux config set profile aggressive
```

Common settings (full list via `crux config show`):
- `min_input_length`: minimum output chars before compression kicks in
- `min_compression_ratio`: minimum fraction saved to keep the compressed output
- `chars_per_token`: ratio for token estimation (default: 4)
- `wrap_timeout`: max seconds for command execution (default: 300)
- `profile`: `conservative` | `balanced` | `aggressive` preset bundle
- `disabled_processors`: list of processors to turn off

## Debug Mode
Set `CRUX_DEBUG=true` to enable debug logging to `~/.crux/hook.log`.

## Supported Processors
Crux ships 30+ processors covering: git, gh (GitHub CLI), docker, kubectl, helm, terraform,
pulumi, ansible, npm/pip/cargo/go, test runners (pytest, jest, go test), linters
(eslint, ruff, pylint, clippy, mypy), build tools, cloud CLIs (aws, gcloud, az), database
queries, file listings, file content, environment/system info, network tools, and search.

## Troubleshooting
If compression isn't working:
1. Run `crux doctor` and address anything it flags.
2. Check that `python3` is available in your PATH.
3. Set `CRUX_DEBUG=true`, trigger a compressible command, then read `~/.crux/hook.log`.
4. Verify routing: `crux explain "git diff"`.
