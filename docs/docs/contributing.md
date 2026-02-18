---
title: Contributing
sidebar_label: Contributing
sidebar_position: 100
description: Development setup, build instructions, testing, and code style guidelines for contributors.
---

## Local Development Setup

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv
source .venv/bin/activate

pip install maturin pytest pytest-asyncio
maturin develop
```

## Start Aerospike Server

```bash
docker run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 \
  -e "NAMESPACE=test" \
  -e "CLUSTER_NAME=docker" \
  aerospike/aerospike-server
```

## Project Structure

```
aerospike-py/
├── rust/src/          # PyO3 Rust bindings
│   ├── lib.rs         # Module entry point
│   ├── client.rs      # Sync Client
│   ├── async_client.rs# Async Client
│   ├── query.rs       # Query
│   ├── operations.rs  # Operation mapping
│   ├── errors.rs      # Error → Exception
│   ├── constants.rs   # 130+ constants
│   ├── types/         # Type converters
│   └── policy/        # Policy parsers
├── src/aerospike_py/  # Python package
├── tests/             # Test suite
├── docs/              # Documentation (MkDocs)
└── benchmark/         # Benchmark scripts
```

## Building

```bash
# Development build (debug, fast compile)
maturin develop

# Release build (optimized)
maturin develop --release

# Build wheel
maturin build --release
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (no server needed)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Specific test file
pytest tests/integration/test_crud.py -v
```

## Code Style

### Python

- Formatter: [ruff](https://docs.astral.sh/ruff/)
- Linter: ruff

```bash
ruff check src/ tests/
ruff format src/ tests/
```

### Rust

- Formatter: `cargo fmt`
- Linter: `cargo clippy`

```bash
cd rust
cargo fmt --check
cargo clippy -- -D warnings
```

## Pre-commit Hooks

Install pre-commit hooks for automatic formatting:

```bash
pip install pre-commit
pre-commit install
```

## Making Changes

1. **Rust code** (`rust/src/`): Edit, then `maturin develop` to rebuild.
2. **Python code** (`src/aerospike_py/`): Changes apply immediately.
3. **Tests**: Add to `tests/unit/` or `tests/integration/`.
4. **Docs**: Edit files in `docs/`, preview with `mkdocs serve`.

## Architecture Notes

- **Sync Client**: Uses a global Tokio runtime. All async Rust calls are wrapped with `py.allow_threads(|| RUNTIME.block_on(...))` to release the GIL.
- **Async Client**: Uses `pyo3_async_runtimes::tokio::future_into_py()` to return Python coroutines.
- **Type conversion**: Python types are converted to/from Rust `Value` enum in `types/value.rs`.
- **Error mapping**: Rust `aerospike_core::Error` variants are mapped to Python exceptions in `errors.rs`.
