# aerospike-py

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

### Install (from source)

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv && source .venv/bin/activate
pip install maturin && maturin develop
```

### Start Aerospike Server

```bash
podman run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 \
  --shm-size=1g \
  -e "NAMESPACE=test" \
  -e "DEFAULT_TTL=2592000" \
  -v ./scripts/aerospike.template.conf:/etc/aerospike/aerospike.template.conf \
  aerospike:ce-8.1.0.3_1
```

> `scripts/aerospike.template.conf`에 `access-address 127.0.0.1`이 설정되어 있습니다.
> Rust 기반 client는 서버가 알려주는 컨테이너 내부 IP로 재연결을 시도하므로, 이 설정이 필수입니다.

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

| Operation | aerospike-py (Rust) | official (C) | async (Rust) | Async vs C |
| --------- | ------------------: | -----------: | -----------: | ---------: |
| put       |               0.140 |        0.139 |        0.058 | 2.4x faster |
| get       |               0.141 |        0.141 |        0.063 | 2.2x faster |

> Sync performance is on par with the official C client. `AsyncClient` + `asyncio.gather` improves throughput by **2.2-2.4x**.
> Full results: `bash benchmark/run_all.sh 5000 100`

## Contributing

### Setup

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv && source .venv/bin/activate
pip install maturin pytest pytest-asyncio
maturin develop
```

### Running Tests

Aerospike 서버가 필요합니다 (unit 테스트 제외). 위의 [Start Aerospike Server](#start-aerospike-server)를 참고하세요.

```bash
# Unit tests (no server needed)
uvx --with tox-uv tox -e py312

# Integration tests
uvx --with tox-uv tox -e integration

# Concurrency / Feasibility tests
uvx --with tox-uv tox -e concurrency
uvx --with tox-uv tox -e fastapi
uvx --with tox-uv tox -e gunicorn

# Official client compatibility tests
uvx --with tox-uv tox -e compat

# All tests
uvx --with tox-uv tox -e all
```

### Making Changes

1. **Rust code** (`rust/src/`): Edit, then `maturin develop` to rebuild.
2. **Python code** (`src/aerospike_py/`): Changes apply immediately.
3. **Tests**: Add to `tests/unit/` or `tests/integration/` as appropriate.

> Architecture details: [docs/contributing.md](docs/contributing.md)

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
