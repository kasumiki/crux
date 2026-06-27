# Examples

Runnable samples that show what Crux does and how to extend it.

## See it work

```bash
python3 examples/demo.py
```

Runs each sample below through the **real** compression pipeline (`crux.core.compress`
— the same path the Claude Code / Antigravity hooks use), prints before/after token
counts, shows what a token budget buys on diffs/plans, and prints one full `pytest`
before/after so you can see exactly what the model receives. No install required.

To measure your own commands instead: `crux benchmark "<command>"`.

## Fixtures

Realistic CLI output in `fixtures/`, used by the demo and by the README's savings
table (`tools/generate_demo.py`), which the test suite verifies against:

| File | What it is | Default savings |
|------|------------|-----------------|
| `pytest_output.txt` | `pytest -v`, 503 tests (501 pass, 2 fail, 1 warning) | ~96% |
| `npm_install.txt` | `npm install`, 847 packages with deprecation warnings | ~99% |
| `kubectl_pods.txt` | `kubectl get pods`, 49 pods across namespaces | ~94% |
| `large_git_diff.txt` | `git diff`, 5 files with adds/deletes/context | ~8% (→50% with a budget) |
| `terraform_plan.txt` | `terraform plan`, 15 resource changes | ~7% (→51% with a budget) |

Diffs and plans are mostly *signal*, so the processors keep them by default; set
`max_output_tokens` (or the `aggressive` profile) and the budget reducer compresses
those too, while errors are always preserved.

## Custom processors

See [`custom_processor/`](custom_processor/) for a complete, copy-pasteable example
of a user-defined processor (`ansible-playbook` output) and how to install it.
