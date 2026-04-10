# aerospike-py

[![PyPI](https://img.shields.io/pypi/v/aerospike-py.svg)](https://pypi.org/project/aerospike-py/)
[![Downloads](https://img.shields.io/pypi/dm/aerospike-py.svg)](https://pypi.org/project/aerospike-py/)
[![CI](https://github.com/aerospike-ce-ecosystem/aerospike-py/actions/workflows/ci.yaml/badge.svg)](https://github.com/aerospike-ce-ecosystem/aerospike-py/actions/workflows/ci.yaml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Rust](https://img.shields.io/badge/rust-stable-orange.svg)](https://www.rust-lang.org/)
[![PyO3](https://img.shields.io/badge/PyO3-0.28-green.svg)](https://pyo3.rs/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Aerospike Python Client built with PyO3 + Rust. Drop-in replacement for [aerospike-client-python](https://github.com/aerospike/aerospike-client-python) powered by the [Aerospike Rust Client v2](https://github.com/aerospike/aerospike-client-rust).

## Features

- Sync and Async (`AsyncClient`) API
- CRUD, Batch, Query, UDF, Admin, Index, Truncate
- CDT List/Map Operations, Expression Filters
- Full type stubs (`.pyi`) for IDE autocompletion

> API details: [Docs](https://aerospike-ce-ecosystem.github.io/aerospike-py/api/client) | Usage guides: [Guides](https://aerospike-ce-ecosystem.github.io/aerospike-py/guides/crud/read)

## Drop-in Replacement

Just change the import — your existing code works as-is:

```diff
- import aerospike
+ import aerospike_py as aerospike

config = {'hosts': [('localhost', 3000)]}
client = aerospike.client(config).connect()

key = ('test', 'demo', 'key1')
client.put(key, {'name': 'Alice', 'age': 30})
_, _, bins = client.get(key)
client.close()
```

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

> **Sync** performance is on par with the official C client.
> **Async** throughput is **2.2-2.4x faster** — the official C client has no Python async/await support ([attempted and removed](https://github.com/aerospike/aerospike-client-python/pull/462)).

### Why async matters

The official C client supports async I/O internally (libev/libuv/libevent), but its Python bindings **cannot expose `async/await`** — the attempt was abandoned and removed in [PR #462](https://github.com/aerospike/aerospike-client-python/pull/462). The only concurrency option with the C client is `asyncio.run_in_executor()` (thread pool, not true async).

aerospike-py provides **native `async/await`** via Tokio + PyO3, enabling `asyncio.gather()` for true concurrent I/O — critical for modern Python web frameworks (FastAPI, Starlette, etc).

> Full benchmark details: [benchmark/](benchmark/) | Run: `make run-benchmark`

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

### Skills

Invoke with `/skill-name`.

| Skill | Command | Description |
|-------|---------|-------------|
| **run-tests** | `/run-tests [type]` | Build → ensure Aerospike server is running → run tests (unit/integration/concurrency/compat/all/matrix) |
| **release-check** | `/release-check` | Pre-release validation (lint, unit tests, pyright, type stub consistency, version check) |
| **bench-compare** | `/bench-compare` | Benchmark comparison: aerospike-py vs the official C client |
| **test-sample-fastapi** | `/test-sample-fastapi` | Build aerospike-py → install sample-fastapi → run integration tests |
| **new-api** | `/new-api [method] [desc]` | Guide for adding a new Client/AsyncClient API method (Rust → Python wrapper → type stubs → tests) |

### Subagents

Invoked automatically during code review and analysis.

| Agent | Description |
|-------|-------------|
| **pyo3-reviewer** | Reviews PyO3 bindings (GIL management, type conversions, async safety, memory safety) |
| **type-stub-sync** | Validates consistency between `__init__.pyi` stubs and Rust source |

### Hooks

Run automatically when files are edited.

| Hook | Trigger | Action |
|------|---------|--------|
| Python auto-format | After editing `.py` | `ruff format` + `ruff check --fix` |
| Rust auto-format | After editing `.rs` | `cargo fmt` |
| Binary/lock protection | On editing `.so`, `.dylib`, `.whl`, `uv.lock` | Blocks the edit |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running tests, and making changes.

## Code stats

Powered by [tokei](https://github.com/XAMPPRocky/tokei). Configuration: `tokei.toml` + `.tokeignore`

### Code Size

| Layer | Files | Code Lines | Role |
|--------|--------:|----------:|------|
| **aerospike-core** (Rust) | 100 | 19,635 | Aerospike protocol, cluster management, command execution |
| **rust/src** (PyO3 bindings) | 35 | 9,681 | Python ↔ Rust conversion, async/sync client, policy parsing |
| **src/aerospike_py** (Python) | 25 | 7,217 | Type stubs (.pyi), NamedTuple wrappers, helpers |
| **Total** | **160** | **36,533** | Rust 80% · Python 20% |

### Compared to Other DB Clients

| Client | Implementation Code | Notes |
|-----------|----------:|------|
| **aerospike-py** (Rust+Python) | ~36K | Protocol implemented from scratch |
| aerospike-client-python (official) | ~15K | Wraps C client (100K+), C code separate |
| redis-rs (Rust) | ~15K | Much simpler protocol (text-based) |
| pymongo (Python) | ~40-50K | Pure Python, protocol implemented from scratch |
| psycopg3 (Python) | ~25-30K | Wraps libpq (C) |

```bash
# Implementation code only (excludes tests, examples, benchmark)
tokei

# Including aerospike-core
tokei rust/src/ src/aerospike_py/

# Include tests, benchmarks, and samples
tokei src rust/src tests benchmark examples
```

Implementation code only (excludes tests, examples, benchmark):
```
$ tokei -C
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Language                                 Files        Lines         Code     Comments       Blanks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Rust                                        35        11019         9681          330         1008
 Python                                      25         8664         7217          260         1187
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Total                                       60        20521        16898         1301         2322
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
