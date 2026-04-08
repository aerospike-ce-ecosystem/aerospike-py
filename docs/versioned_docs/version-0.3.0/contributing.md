---
title: Contributing
sidebar_label: Contributing
sidebar_position: 100
description: Development setup, build, test, and code style guidelines.
---

## Setup

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py
make install          # uv sync --all-groups
make build            # uv run maturin develop --release
```

## Start Aerospike

```bash
make run-aerospike-ce   # Aerospike CE on port 18710
```

## Build

```bash
make build                    # Release build (recommended)
maturin develop               # Debug build (faster compile)
maturin build --release       # Build wheel
```

## Test

```bash
make test-unit          # No server needed
make test-integration   # Server needed
make test-all           # All tests
```

## Lint & Format

```bash
make lint     # ruff check + cargo clippy
make fmt      # ruff format + cargo fmt
```

## Pre-commit

```bash
pip install pre-commit
pre-commit install
```

## Project Structure

```
aerospike-py/
├── rust/src/               # PyO3 Rust bindings
│   ├── client.rs           # Sync Client
│   ├── async_client.rs     # Async Client
│   ├── errors.rs           # Error → Exception
│   ├── types/              # Type converters
│   └── policy/             # Policy parsers
├── src/aerospike_py/       # Python package
├── tests/                  # unit/ integration/ concurrency/ compatibility/
├── docs/                   # Docusaurus
└── benchmark/              # Benchmarks
```

## Making Changes

1. **Rust** (`rust/src/`): Edit, then `maturin develop` to rebuild
2. **Python** (`src/aerospike_py/`): Changes apply immediately
3. **Tests**: Add to `tests/unit/` or `tests/integration/`
4. **Docs**: Edit `docs/docs/`, preview with `cd docs && npm start`

## Architecture Notes

- **Sync Client**: Global Tokio runtime, `py.allow_threads(|| RUNTIME.block_on(...))` releases GIL
- **Async Client**: `pyo3_async_runtimes::tokio::future_into_py()` returns Python coroutines
- **Type conversion**: Python ↔ Rust `Value` enum in `types/value.rs`
- **Error mapping**: `aerospike_core::Error` → Python exceptions in `errors.rs`
