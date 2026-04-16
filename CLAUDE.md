# aerospike-py

Python client library for the Aerospike NoSQL database.
**Written in Rust (PyO3)** and compiled to a native binary, providing both sync and async APIs from Python.

## Installation

```bash
pip install aerospike-py
```

> Python 3.10–3.14 (including 3.14t free-threaded), CPython only. Supports macOS (arm64, x86_64) and Linux (x86_64, aarch64).

## Project Structure

```
aerospike-py/
├── rust/src/               # Rust native module (PyO3 bindings)
│   ├── lib.rs              # Module entry point
│   ├── client.rs           # Sync Client implementation
│   ├── async_client.rs     # Async Client implementation
│   ├── errors.rs           # Error mapping (Aerospike → Python exceptions)
│   ├── operations.rs       # operate/operate_ordered operation translation
│   ├── query.rs            # Query object
│   ├── constants.rs        # Constant definitions
│   ├── expressions.rs      # Expression filter parsing
│   ├── batch_types.rs      # Batch operation type definitions
│   ├── numpy_support.rs    # NumPy array conversion support
│   ├── record_helpers.rs   # Record conversion helpers
│   ├── runtime.rs          # Tokio runtime management
│   ├── logging.rs          # Logging configuration
│   ├── metrics.rs          # Prometheus metrics collection
│   ├── tracing.rs          # OpenTelemetry tracing
│   ├── policy/             # Policy parsing (read, write, admin, batch, query, client)
│   └── types/              # Type conversions (key, value, record, bin, host)
├── src/aerospike_py/       # Python package
│   ├── __init__.py         # Client/AsyncClient wrappers, factory functions, constants re-export
│   ├── __init__.pyi        # Type stubs (main)
│   ├── _types.py           # Internal type definitions
│   ├── types.py            # Public type definitions
│   ├── exception.py        # Exception class re-exports
│   ├── exception.pyi       # Exception type stubs
│   ├── predicates.py       # Query predicate helpers
│   ├── predicates.pyi      # Predicate type stubs
│   ├── list_operations.py  # List CDT operation helpers
│   ├── list_operations.pyi # List operation type stubs
│   ├── map_operations.py   # Map CDT operation helpers
│   ├── map_operations.pyi  # Map operation type stubs
│   ├── exp.py              # Expression filter builder
│   ├── exp.pyi             # Expression type stubs
│   ├── numpy_batch.py      # NumPy-based batch results
│   └── py.typed            # PEP 561 type marker
├── tests/
│   ├── unit/               # Unit tests (no server required)
│   ├── integration/        # Integration tests (requires Aerospike server)
│   ├── concurrency/        # Thread safety tests
│   ├── compatibility/      # Official C client compatibility tests
│   └── feasibility/        # Framework integration tests (FastAPI, Gunicorn)
└── pyproject.toml          # Build configuration (maturin)
```

## Development Environment

**uv** is used as the package manager. Key commands are defined in the Makefile.

```bash
# Install dependencies
make install                        # uv sync --group dev

# Rust build
make build                          # uv run maturin develop --release
cargo check --manifest-path rust/Cargo.toml  # Compilation check only (fast)

# Tests
make test-unit                      # Unit tests (no server required)
make test-integration               # Integration tests (requires Aerospike server)
make test-concurrency               # Thread safety tests
make test-compat                    # Official client compatibility tests
make test-all                       # Full test suite
make test-matrix                    # Python 3.10–3.14 matrix tests (tox)

# Lint & format
make lint                           # ruff check + clippy
make fmt                            # ruff format + cargo fmt

# Local Aerospike server
make run-aerospike-ce               # Start Aerospike CE via compose.local.yaml (port 18710)
make stop-aerospike-ce              # Stop Aerospike CE server

# Type checking & validation
make typecheck                      # pyright type check
make validate                       # fmt + lint + typecheck + unit — full validation

# Documentation
make docs-start                     # Docusaurus dev server (hot reload)
make docs-build                     # Docusaurus production build

# Miscellaneous
make dev-build                      # Debug build (without --release, faster)
make coverage                       # Generate test coverage report
make clean                          # Remove all build artifacts
make pre-commit-install             # Install pre-commit hooks
```

### Pre-commit Hooks

Runs automatically on commit: trailing-whitespace, ruff format/lint, pyright, cargo fmt, cargo clippy (-D warnings)

### Notes

- OpenTelemetry (`otel`) is always included in the default build — no separate feature flag needed
- Run `make run-aerospike-ce` to start a local server before running integration tests
- maturin version is pinned to `>=1.9,<2.0`
- The `AEROSPIKE_HOST` and `AEROSPIKE_PORT` environment variables override the server address (default: `127.0.0.1:18710`)
- The `AEROSPIKE_RUNTIME_WORKERS` environment variable controls the number of internal Tokio worker threads (default: 2; since the workload is I/O-bound, 2 is sufficient in most cases)
- The `RUNTIME` environment variable selects the container runtime: docker or podman (default: podman)
- Container configuration is managed via compose files at the project root: `compose.local.yaml` (development) and `compose.sample-fastapi.yaml` (FastAPI sample)
- CI uses its own service container (port 3000), configured via `AEROSPIKE_PORT=3000`

## API Reference

API usage is automatically loaded from the `aerospike-py-api` skill in the ecosystem plugin.
For complete type and constant definitions, see `src/aerospike_py/__init__.pyi`.

---

## Test Configuration

Integration tests require a running Aerospike server. Default configuration in `tests/__init__.py`:

```python
AEROSPIKE_CONFIG = {"hosts": [("127.0.0.1", 18710)], "cluster_name": "docker"}
```

Key fixtures (`tests/conftest.py`):
- `client` — module-scoped sync client
- `async_client` — function-scoped async client
- `cleanup` / `async_cleanup` — automatic record cleanup after each test

pytest configuration: `asyncio_mode = "auto"` (async tests detected automatically)

## Planning

When entering plan mode, always read `.claude/skills/project-goals/SKILL.md` first.
