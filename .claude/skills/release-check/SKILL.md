---
name: release-check
description: Run pre-release validation (lint, unit tests, type check, stub consistency)
disable-model-invocation: true
---

# Release Check

Performs full validation before a release. Execute the steps below in order.

## Validation Steps

### 1. Lint Check
```bash
make lint
```
Commands executed internally:
- `uv run ruff check src/ tests/ benchmark/` — Python lint
- `uv run ruff format --check src/ tests/ benchmark/` — Python format check
- `cargo clippy --manifest-path rust/Cargo.toml --features otel -- -D warnings` — Rust lint (with otel feature, warnings treated as errors)

All warnings/errors must be resolved.

### 2. Auto-fix Formatting (if needed)
```bash
make fmt
```
Commands executed internally:
- `uv run ruff format src/ tests/ benchmark/`
- `uv run ruff check --fix src/ tests/ benchmark/`
- `cargo fmt --manifest-path rust/Cargo.toml`

### 3. Unit Tests
```bash
make test-unit
```
Runs all unit tests that don't require a server. Includes build (`maturin develop --release`).

### 4. Pyright Type Check
```bash
uv run pyright src/
```
Verifies there are no Python type errors. Configuration (`pyproject.toml`):
- `pythonVersion = "3.10"` (based on minimum supported version)
- `typeCheckingMode = "basic"`
- `include = ["src/aerospike_py"]`

### 5. Type Stub Consistency Verification

Compares `src/aerospike_py/__init__.pyi` with the Rust implementation:

**Verification items:**

| Check | Comparison Target |
|-----------|-----------|
| Sync Client methods | `.pyi` `class Client` vs `rust/src/client.rs` `#[pymethods] impl PyClient` |
| Async Client methods | `.pyi` `class AsyncClient` vs `rust/src/async_client.rs` `#[pymethods] impl PyAsyncClient` |
| Python wrapper methods | `.pyi` vs `src/aerospike_py/__init__.py` `class Client` / `class AsyncClient` |
| Signature match | Parameter names, types, defaults, return types |
| Constant completeness | `.pyi` constants vs `rust/src/constants.rs` + `__init__.py` re-exports |
| Exception classes | `.pyi` / `exception.pyi` vs `rust/src/errors.rs` |
| NamedTuple definitions | `.pyi` types vs `src/aerospike_py/types.py` |

**Quick check method:**
```bash
# List methods with #[pyo3(signature in Rust
grep -n '#\[pyo3(signature' rust/src/client.rs rust/src/async_client.rs

# List methods defined in .pyi
grep -n 'def ' src/aerospike_py/__init__.pyi | head -60
```

### 6. Version Check

Verify that the `version` field in `pyproject.toml` is correctly updated:
```bash
grep 'version' pyproject.toml
```
Note: This project uses `dynamic = ["version"]` and maturin pulls the version from `Cargo.toml`.
```bash
grep '^version' rust/Cargo.toml
```

Also verify it matches the git tag:
```bash
git tag --sort=-version:refname | head -5
```

### 7. Run Full Pre-commit Hooks
```bash
uvx pre-commit run --all-files
```
The CI lint job also runs this command. Includes:
- trailing-whitespace
- ruff format / ruff lint
- pyright
- cargo fmt
- cargo clippy (-D warnings)

### 8. Python Version Matrix Tests (optional)
```bash
make test-matrix
```
Runs unit tests across Python 3.10, 3.11, 3.12, 3.13, 3.14, 3.14t (free-threaded).
Uses tox-uv to automatically create virtual environments for each Python version.

### 9. Integration Tests (requires server, optional)
```bash
make test-all
```
An Aerospike server must be running (`make run-aerospike-ce`).
Runs all test suites (unit + integration + concurrency + feasibility + compat).

## Result Report

Summarize the success/failure of each step and suggest fixes for any failed items.

**Release readiness criteria:**
1. `make lint` passes (0 ruff + clippy warnings)
2. `make test-unit` passes
3. `uv run pyright src/` — 0 errors
4. Type stub consistency verified
5. Version number is correct
6. (Recommended) `make test-matrix` all pass
7. (Recommended) `make test-all` all pass (requires server)
