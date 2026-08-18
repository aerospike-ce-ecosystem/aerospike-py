# Contributing

## Setup

```bash
git clone https://github.com/aerospike-ce-ecosystem/aerospike-py.git
cd aerospike-py

# Install uv (if not already installed)
# https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies and build the Rust extension
make build

# Or manually:
uv sync --group dev
uv run maturin develop --release
```

## Running Tests

### Start Aerospike Server

Running integration and feasibility tests requires an Aerospike server (except unit tests).
The default local path is:

```bash
make run-aerospike-ce  # starts Aerospike CE on 127.0.0.1:18710
```

If you start the container manually on Aerospike's default port, set
`AEROSPIKE_PORT=3000` when running integration-style tests:

```bash
podman run -d --name aerospike \
  -p 3000:3000 -p 3001:3001 -p 3002:3002 \
  --shm-size=1g \
  -e "NAMESPACE=test" \
  -e "DEFAULT_TTL=2592000" \
  -v ./scripts/aerospike.template.conf:/etc/aerospike/aerospike.template.conf \
  aerospike:ce-8.1.0.3_1
```

> `scripts/aerospike.template.conf` has `access-address 127.0.0.1` configured.
> The Rust-based client attempts to reconnect using the container's internal IP reported by the server, so this setting is required.

### Run Tests

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

### Requiring a server

Server-dependent suites skip themselves when no Aerospike server is reachable,
so a local run without a container stays green. CI must not have that latitude —
a suite that skips its way to zero passes would report a connect-path regression
as a pass. The CI jobs that provision a server therefore set:

```bash
AEROSPIKE_REQUIRE_SERVER=1 uvx --with tox-uv tox -e all
```

With it set, an unreachable server is an error rather than a skip, and a run
that collects tests but passes none of them fails the job. Set it locally to
reproduce a CI failure; leave it unset for the usual skip-when-absent
convenience.

Note that the skip also requires the service port to be genuinely closed. If the
port accepts connections but `connect()` still fails, that is a client-side bug,
and the suite reports it instead of skipping — regardless of this variable.

## Pre-commit hooks

This project uses [pre-commit](https://pre-commit.com/) for linting and formatting:

```bash
uvx pre-commit install
uvx pre-commit run --all-files
```

## Making Changes

1. **Rust code** (`rust/src/`): Edit, then `uv run maturin develop --release` to rebuild.
2. **Python code** (`src/aerospike_py/`): Changes apply immediately.
3. **Tests**: Add to `tests/unit/` or `tests/integration/` as appropriate.

> Architecture details: [docs/contributing.md](docs/contributing.md)
