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

Integration 및 feasibility 테스트를 실행하려면 Aerospike 서버가 필요합니다 (unit 테스트 제외).

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
