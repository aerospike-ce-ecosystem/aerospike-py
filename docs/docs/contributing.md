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

# Install dependencies (requires uv)
make install          # uv sync --all-groups

# Build native module
make build            # uv run maturin develop --release
```

:::tip[Alternative: manual setup]

If you prefer not to use `uv` and `make`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install maturin pytest pytest-asyncio
maturin develop
```

:::

## Start Aerospike Server

```bash
make run-aerospike-ce   # starts Aerospike CE on port 18710
```

Or manually with Docker/Podman:

```bash
docker run -d --name aerospike \
  -p 18710:3000 -p 3001:3001 -p 3002:3002 \
  -e "NAMESPACE=test" \
  -e "CLUSTER_NAME=docker" \
  aerospike/aerospike-server
```

## Project Structure

```
aerospike-py/
├── rust/src/               # PyO3 Rust bindings
│   ├── lib.rs              # Module entry point
│   ├── client.rs           # Sync Client
│   ├── async_client.rs     # Async Client
│   ├── query.rs            # Query
│   ├── operations.rs       # Operation mapping
│   ├── errors.rs           # Error → Exception
│   ├── constants.rs        # 130+ constants
│   ├── expressions.rs      # Expression filter parsing
│   ├── metrics.rs          # Prometheus metrics
│   ├── tracing.rs          # OpenTelemetry tracing
│   ├── types/              # Type converters
│   └── policy/             # Policy parsers
├── src/aerospike_py/       # Python package
├── tests/                  # Test suite
│   ├── unit/               # Unit tests (no server needed)
│   ├── integration/        # Integration tests (server needed)
│   ├── concurrency/        # Thread safety tests
│   └── compatibility/      # Official C client compat tests
├── docs/                   # Documentation (Docusaurus)
└── benchmark/              # Benchmark scripts
```

## Building

```bash
# Recommended: use make
make build              # uv run maturin develop --release

# Or manually:
maturin develop         # Development build (debug, fast compile)
maturin develop --release  # Release build (optimized)
maturin build --release    # Build wheel
```

## Running Tests

```bash
# Using make (recommended)
make test-unit          # Unit tests (no server needed)
make test-integration   # Integration tests (server needed)
make test-all           # All tests

# Or manually with pytest
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/integration/test_crud.py -v
```

## Code Style

```bash
make lint     # ruff check + cargo clippy
make fmt      # ruff format + cargo fmt
```

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
4. **Docs**: Edit files in `docs/docs/`, preview with `cd docs && npm start`.

## Architecture Notes

- **Sync Client**: Uses a global Tokio runtime. All async Rust calls are wrapped with `py.allow_threads(|| RUNTIME.block_on(...))` to release the GIL.
- **Async Client**: Uses `pyo3_async_runtimes::tokio::future_into_py()` to return Python coroutines.
- **Type conversion**: Python types are converted to/from Rust `Value` enum in `types/value.rs`.
- **Error mapping**: Rust `aerospike_core::Error` variants are mapped to Python exceptions in `errors.rs`.
