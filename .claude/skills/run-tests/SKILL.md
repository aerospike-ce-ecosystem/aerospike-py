---
name: run-tests
description: Build, ensure Aerospike server is healthy, and run tests
disable-model-invocation: true
args: "[test-type]"
---

# Run Tests

Runs aerospike-py tests. Tests that require an Aerospike server automatically start a container and wait for the health check to pass before executing.

## Arguments

Invoke with `/run-tests [test-type]`.

| test-type | Server Required | Description | Makefile Target |
|-----------|----------|------|--------------|
| `unit` | No | Unit tests (default) | `make test-unit` |
| `integration` | Yes | Integration tests | `make test-integration` |
| `concurrency` | Yes | Thread/async safety tests | `make test-concurrency` |
| `compat` | Yes | Official C client compatibility tests | `make test-compat` |
| `all` | Yes | Full test suite | `make test-all` |
| `matrix` | No | Python 3.10~3.14 + 3.14t matrix tests | `make test-matrix` |

If no argument is provided, `unit` is run.

## Steps

### 1. Build
```bash
make build
```
Internally runs `uv sync --group dev --group bench && uv run maturin develop --release`.

### 2. Ensure Aerospike Server (except unit, matrix)

`unit` and `matrix` don't require a server, so this step is skipped.
For all other test types, ensure the server is available in this order:

#### 2-1. Check Container Status
```bash
podman compose -f compose.local.yaml up -d
```

Container runtime is specified via the `RUNTIME` environment variable (default: `podman`, `docker` also supported).
`compose.local.yaml`: Aerospike CE 8.1, host port `18710` -> container port `3000`.

#### 2-2. Health Check (wait up to 30 seconds)
```bash
for i in $(seq 1 30); do
  if podman exec aerospike asinfo -v status 2>/dev/null | grep -q 'ok'; then
    echo "Aerospike is ready"
    break
  fi
  echo "Waiting for Aerospike... ($i/30)"
  sleep 1
done
```

If the health check doesn't pass within 30 seconds, check the logs with `podman logs aerospike` and report the cause.

### 3. Run Tests

Execute the corresponding command based on the argument:

| Argument | Command | tox Environment |
|------|--------|----------|
| `unit` | `uv run pytest tests/unit/ -v` | - |
| `integration` | `uvx --with tox-uv tox -e integration` | `test-integration` dependency group |
| `concurrency` | `uvx --with tox-uv tox -e concurrency` | default `test` dependency group |
| `compat` | `uvx --with tox-uv tox -e compat` | `test-compat` dependency group (includes official `aerospike`) |
| `all` | `uvx --with tox-uv tox -e all` | `test-all` dependency group |
| `matrix` | `uvx --with tox-uv tox` | py310~py314 + py314t full matrix |

### 4. Report Results
- Summary of passed/failed test counts
- If any tests failed, provide error messages and root cause analysis

## Environment Variables

| Variable | Default | Description |
|------|--------|------|
| `AEROSPIKE_HOST` | `127.0.0.1` | Aerospike server host |
| `AEROSPIKE_PORT` | `18710` | Aerospike server port (for local development) |
| `RUNTIME` | `podman` | Container runtime (`docker` or `podman`) |

**CI environment**: GitHub Actions uses service containers with `AEROSPIKE_PORT=3000`.

## Test Infrastructure

### Test Configuration (`tests/__init__.py`)

```python
AEROSPIKE_CONFIG = {
    "hosts": [(os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
               int(os.environ.get("AEROSPIKE_PORT", "18710")))],
    "cluster_name": "docker",
}
```

### Shared Fixtures (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|------|
| `client` | module | Sync client. Auto-skips via `pytest.skip()` if server unavailable |
| `async_client` | function | Async client. Auto-skips via `pytest.skip()` if server unavailable |
| `cleanup` | function | Append keys to the `keys` list -> automatic `client.remove()` after test |
| `async_cleanup` | function | Async version of cleanup. Uses `async_client.remove()` |

### pytest Configuration (`pyproject.toml`)

- `asyncio_mode = "auto"` -> no `@pytest.mark.asyncio` decorator needed for async tests.
- `pass_env = ["AEROSPIKE_HOST", "AEROSPIKE_PORT"]` configured in tox environments for env variable passthrough.

### Test Directory Structure

```
tests/
├── __init__.py           # AEROSPIKE_CONFIG definition
├── conftest.py           # Shared fixtures (client, async_client, cleanup)
├── unit/                 # No server required. Argument validation, type errors, disconnected error tests
├── integration/          # Server required. Actual CRUD, batch, query, etc. tests
│   └── conftest.py       # Integration-specific fixtures (autouse cleanup, etc.)
├── concurrency/          # Thread safety, async concurrency tests
│   └── test_freethreading.py  # Python 3.14t only (excluded from concurrency tox env)
├── compatibility/        # Behavior comparison with official C client (`aerospike` PyPI)
└── feasibility/          # Framework integration tests
    ├── test_fastapi.py   # AsyncClient usage in a FastAPI app
    └── test_gunicorn.py  # Client usage in Gunicorn multi-worker
```

## CI Workflow (`ci.yaml`) Mapping

| CI Job | Test Type | Python | Server |
|--------|------------|--------|------|
| lint | pre-commit (ruff, clippy, fmt) | 3.13 | No |
| build | unit (matrix) | 3.10~3.14 | No |
| build-freethreaded | unit | 3.14t | No |
| integration | all | 3.13 | AS 7.2 + latest |
| test-concurrency | concurrency | 3.13 | AS latest |
| test-concurrency-freethreaded | freethreading | 3.14t | AS latest |
| feasibility | fastapi, gunicorn | 3.13 | AS latest |
| compatibility | compat | 3.13 | AS latest |
