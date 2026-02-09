# Contributing

## Setup

```bash
git clone https://github.com/KimSoungRyoul/aerospike-py.git
cd aerospike-py

python -m venv .venv && source .venv/bin/activate
pip install maturin pytest pytest-asyncio
maturin develop
```

## Running Tests

### Start Aerospike Server

Running integration and feasibility tests requires an Aerospike server (except unit tests).

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

## Making Changes

1. **Rust code** (`rust/src/`): Edit, then `maturin develop` to rebuild.
2. **Python code** (`src/aerospike_py/`): Changes apply immediately.
3. **Tests**: Add to `tests/unit/` or `tests/integration/` as appropriate.

> Architecture details: [docs/contributing.md](docs/contributing.md)
