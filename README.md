# aerospike-py

[![PyPI](https://img.shields.io/pypi/v/aerospike-py.svg)](https://pypi.org/project/aerospike-py/)
[![Downloads](https://img.shields.io/pypi/dm/aerospike-py.svg)](https://pypistats.org/packages/aerospike-py)
[![CI](https://github.com/aerospike-ce-ecosystem/aerospike-py/actions/workflows/ci.yaml/badge.svg)](https://github.com/aerospike-ce-ecosystem/aerospike-py/actions/workflows/ci.yaml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

High-performance Aerospike Python Client built with PyO3 + Rust, powered by the [Aerospike Rust Client v2](https://github.com/aerospike/aerospike-client-rust).

## Features

- Sync and Async (`AsyncClient`) API
- CRUD, Batch, Query, UDF, Admin, Index, Truncate
- CDT List/Map Operations, Expression Filters
- NumPy v2 structured-array results for batch reads (skips Python-object overhead for analytical pipelines)
- Full type stubs (`.pyi`) for IDE autocompletion

> [Documentation](https://aerospike-ce-ecosystem.github.io/aerospike-py/) — API reference, usage guides, integration examples

## Quickstart

```bash
pip install aerospike-py
```

### Sync Client

```python
import aerospike_py as aerospike

with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:

    key = ("test", "demo", "user1")
    client.put(key, {"name": "Alice", "age": 30})

    record = client.get(key)
    print(record.bins)      # {'name': 'Alice', 'age': 30}
    print(record.meta.gen)  # 1

    client.increment(key, "age", 1)
    client.remove(key)
```

### Async Client

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    async with AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    }) as client:
        await client.connect()

        key = ("test", "demo", "user1")
        await client.put(key, {"name": "Bob", "age": 25})
        record = await client.get(key)
        print(record.bins)  # {'name': 'Bob', 'age': 25}

        # Concurrent operations
        tasks = [client.put(("test", "demo", f"item_{i}"), {"idx": i}) for i in range(10)]
        await asyncio.gather(*tasks)

asyncio.run(main())
```

## Performance

Benchmark: **5,000 ops x 100 rounds**, Aerospike CE (Docker), Apple M4 Pro

| Operation | aerospike-py sync | official C client | aerospike-py async | Async vs C |
| --------- | ----------------: | ----------------: | -----------------: | ---------: |
| put (ms)  |             0.140 |             0.139 |              0.058 | **2.4x faster** |
| get (ms)  |             0.141 |             0.141 |              0.063 | **2.2x faster** |

> **Sync** is on par with the official C client. **Async** is **2.2-2.4x faster** via native Tokio async/await.

## Claude Code Skills & Agents

This project has [Claude Code](https://docs.anthropic.com/en/docs/claude-code) automation configured.

### Ecosystem Plugin Installation

Install [aerospike-ce-ecosystem-plugins](https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins) to access the full ecosystem skill set, including the aerospike-py API reference and deployment guides.

**From GitHub (recommended)**

Add the repository as a marketplace, then install:

```bash
# Step 1: Add as marketplace
claude plugin marketplace add aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins

# Step 2: Install the plugin
claude plugin install aerospike-ce-ecosystem
```

**Project-scoped install**

To install only for the current project:

```bash
claude plugin marketplace add aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins
claude plugin install aerospike-ce-ecosystem -s project
```

**Verify installation**

```bash
claude plugin list
# Should show: aerospike-ce-ecosystem@aerospike-ce-ecosystem ✔ enabled
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running tests, and making changes.

## Repository Automation

This repo wires several automations that fire on commit, PR, push, and schedule. Knowing they exist helps you understand why a check ran (or refused to).

### Pre-commit hooks — `.pre-commit-config.yaml`

Run on every `git commit`. Install once with `make pre-commit-install`.

| Hook | Source | Purpose |
|---|---|---|
| `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `detect-private-key` | `pre-commit/pre-commit-hooks` v5 | basic file hygiene |
| `ruff` (with `--fix`), `ruff-format` | `astral-sh/ruff-pre-commit` | Python lint + format |
| `cargo fmt --check` | local | Rust format check |
| `cargo clippy -D warnings` (`--features otel`) | local | Rust lint, zero-warning gate |

### Claude Code hook — `.claude/hooks/`

Active when developing through [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with the project plugin enabled.

- **`pr-perf-gate.sh`** — `PreToolUse` hook on `gh pr create`. If the PR diff touches any path in [`.claude/perf-hot-paths.txt`](.claude/perf-hot-paths.txt) and the conversation transcript has no `perf-impact:` verdict (from the `perf-impact-reviewer` agent) or benchmark run, the PR creation is blocked. Forces measurement on hot-path changes.

### GitHub Actions — `.github/workflows/`

**Build · release · docs**

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yaml` | `push` / `pull_request` to `main` | full validate (fmt + lint + typecheck + unit + integration matrix). |
| `publish.yaml` | `release: published` / manual | build wheels + sdist, publish to PyPI. |
| `daily-release.yml` | nightly cron / manual | nightly release pipeline. |
| `docs.yaml` | PR touching `docs/` | Docusaurus build check. |
| `docs-publish.yaml` | `push` to `main` | publish Docusaurus site to GitHub Pages. |
| `docs-version.yaml` | manual | freeze a versioned docs snapshot. |

**PR & issue automation (Claude-driven)**

| Workflow | Trigger | Purpose |
|---|---|---|
| `pr-reviewer.yml` | PR opened / updated | automatic Claude review comment. |
| `issue-planner.yml` | issue opened / labeled | generate an implementation plan in the issue. |
| `agent-implement.yml` | issue labeled `plan-complete` | execute the plan, open a PR. |

**Skill & docs follow-up notifications**

| Workflow | Trigger | Purpose |
|---|---|---|
| `skill-impact-notify.yml` | `push` to `main`, on skill-relevant paths | open a routing issue in `aerospike-ce-ecosystem/project-hub`. |
| `ace-plugins-pr-notify.yml` | `pull_request` opened / reopened / ready_for_review / synchronize, on skill-relevant paths | open (or update) a follow-up issue in `aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins` so skill maintainers can mirror the API/docs change. Idempotent: re-pushes append a comment instead of opening a duplicate. |

> Both notify workflows reuse the `GH_AW_GITHUB_TOKEN` PAT for cross-repo writes — rotate together.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
