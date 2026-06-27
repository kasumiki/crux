# Crux Plugin

Crux automatically compresses verbose CLI output to save tokens.

## How it works
- A PreToolUse hook intercepts Bash commands matching known patterns (git, docker, npm, terraform, kubectl, etc.)
- The command output is piped through specialized compression processors
- Compressed output is returned to Claude, saving tokens while preserving critical information (errors, diffs, stack traces)

## Important rules
- Never wrap `crux` CLI commands themselves (avoid infinite loops)
- Never wrap interactive commands (vim, nano, ssh, etc.)
- Never wrap commands with redirections (>) or complex pipes
- Never wrap sudo commands
- Debug mode: set `CRUX_DEBUG=true` environment variable
