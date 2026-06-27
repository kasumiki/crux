# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.
Use GitHub's [private vulnerability reporting](https://github.com/kasumiki/crux/security/advisories/new)
for the repository. We aim to acknowledge reports within a few days.

## Scope and design notes

Crux executes the commands you run and compresses their output. Relevant safeguards:

- **Command rewriting is injection-safe** — the original command is passed to the
  wrapper as a single `shlex.quote`-escaped argument.
- **Fail-open** — if compression errors for any reason, the original output is returned
  unchanged; Crux never blocks a command.
- **Secret redaction** — the `env` processor redacts values for keys matching
  `*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*`.
- **Local and offline** — compression is pure parsing/regex; no output leaves the machine.
- **Excluded commands** — `sudo`, interactive tools, output redirections, and complex
  pipelines are never wrapped.
