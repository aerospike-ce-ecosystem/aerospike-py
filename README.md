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

    _, meta, bins = client.get(key)
    print(bins)  # {'name': 'Alice', 'age': 30}

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
        _, _, bins = await client.get(key)
        print(bins)

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running tests, and making changes.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
