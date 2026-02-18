# aerospike-py

[![PyPI](https://img.shields.io/pypi/v/aerospike-py.svg)](https://pypi.org/project/aerospike-py/)
[![CI](https://github.com/KimSoungRyoul/aerospike-py/actions/workflows/ci.yaml/badge.svg)](https://github.com/KimSoungRyoul/aerospike-py/actions/workflows/ci.yaml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Rust](https://img.shields.io/badge/rust-stable-orange.svg)](https://www.rust-lang.org/)
[![PyO3](https://img.shields.io/badge/PyO3-0.28-green.svg)](https://pyo3.rs/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Aerospike Python Client built with PyO3 + Rust. Drop-in replacement for [aerospike-client-python](https://github.com/aerospike/aerospike-client-python) powered by the [Aerospike Rust Client v2](https://github.com/aerospike/aerospike-client-rust).

## Features

- Sync and Async (`AsyncClient`) API
- CRUD, Batch, Query/Scan, UDF, Admin, Index, Truncate
- CDT List/Map Operations, Expression Filters
- Full type stubs (`.pyi`) for IDE autocompletion

> API details: [docs/api/](docs/api/) | Usage guides: [docs/guides/](docs/guides/)

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

## For AI Agents

This project supports the [llms.txt](https://llmstxt.org/) standard. Use the following prompt to give your AI agent full context about aerospike-py:

```
Fetch and read https://kimsoungryoul.github.io/aerospike-py/llms-full.txt to understand the aerospike-py Python client API, then write code based on that documentation.
```

- [`llms.txt`](https://kimsoungryoul.github.io/aerospike-py/llms.txt) — Documentation index for AI agents
- [`llms-full.txt`](https://kimsoungryoul.github.io/aerospike-py/llms-full.txt) — Complete documentation in a single file

## Claude Code Skills & Agents

이 프로젝트는 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 자동화가 설정되어 있습니다.

### Skills

`/skill-name`으로 호출합니다.

| Skill | 명령어 | 설명 |
|-------|--------|------|
| **run-tests** | `/run-tests [type]` | 빌드 → Aerospike 서버 보장 → 테스트 실행 (unit/integration/concurrency/compat/all/matrix) |
| **release-check** | `/release-check` | 릴리스 전 검증 (lint, unit test, pyright, type stub 일관성, 버전 확인) |
| **bench-compare** | `/bench-compare` | aerospike-py vs 공식 C 클라이언트 벤치마크 비교 |
| **test-sample-fastapi** | `/test-sample-fastapi` | aerospike-py 빌드 → sample-fastapi 설치 → 통합 테스트 실행 |

### Subagents

코드 리뷰/분석 시 자동으로 활용됩니다.

| Agent | 설명 |
|-------|------|
| **pyo3-reviewer** | PyO3 바인딩 리뷰 (GIL 관리, 타입 변환, async 안전성, 메모리 안전성) |
| **type-stub-sync** | `__init__.pyi` stub과 Rust 소스 간 일관성 검증 |

### Hooks

파일 편집 시 자동 실행됩니다.

| Hook | 트리거 | 동작 |
|------|--------|------|
| Python auto-format | `.py` 편집 후 | `ruff format` + `ruff check --fix` |
| Rust auto-format | `.rs` 편집 후 | `cargo fmt` |
| Binary/lock 보호 | `.so`, `.dylib`, `.whl`, `uv.lock` 편집 시 | 편집 차단 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running tests, and making changes.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
