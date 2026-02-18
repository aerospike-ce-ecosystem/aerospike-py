---
name: run-tests
description: Build, ensure Aerospike server is healthy, and run tests
disable-model-invocation: true
args: "[test-type]"
---

# Run Tests

aerospike-py 테스트를 실행합니다. Aerospike 서버가 필요한 테스트는 자동으로 컨테이너를 시작하고 health check를 통과한 후 실행합니다.

## 인자

`/run-tests [test-type]` 형식으로 호출합니다.

| test-type | 서버 필요 | 설명 | Makefile 타겟 |
|-----------|----------|------|--------------|
| `unit` | No | 유닛 테스트 (기본값) | `make test-unit` |
| `integration` | Yes | 통합 테스트 | `make test-integration` |
| `concurrency` | Yes | 스레드/async 안전성 테스트 | `make test-concurrency` |
| `compat` | Yes | 공식 C 클라이언트 호환성 테스트 | `make test-compat` |
| `all` | Yes | 전체 테스트 | `make test-all` |
| `matrix` | No | Python 3.10~3.14 + 3.14t 매트릭스 테스트 | `make test-matrix` |

인자가 없으면 `unit`을 실행합니다.

## 실행 단계

### 1. 빌드
```bash
make build
```
내부적으로 `uv sync --group dev --group bench && uv run maturin develop --release` 실행.

### 2. Aerospike 서버 보장 (unit, matrix 제외)

`unit`과 `matrix`는 서버가 필요 없으므로 이 단계를 건너뜁니다.
나머지 테스트 타입은 아래 순서로 서버를 보장합니다:

#### 2-1. 컨테이너 실행 확인
```bash
podman compose -f compose.local.yaml up -d
```

컨테이너 런타임은 `RUNTIME` 환경변수로 지정 (기본: `podman`, `docker` 가능).
`compose.local.yaml`: Aerospike CE 8.1, 호스트 포트 `18710` -> 컨테이너 포트 `3000`.

#### 2-2. Health check (최대 30초 대기)
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

health check가 30초 안에 통과하지 못하면 `podman logs aerospike`로 로그를 확인하고 원인을 보고합니다.

### 3. 테스트 실행

인자에 따라 해당 명령어를 실행합니다:

| 인자 | 명령어 | tox 환경 |
|------|--------|----------|
| `unit` | `uv run pytest tests/unit/ -v` | - |
| `integration` | `uvx --with tox-uv tox -e integration` | `test-integration` 의존성 그룹 |
| `concurrency` | `uvx --with tox-uv tox -e concurrency` | 기본 `test` 의존성 그룹 |
| `compat` | `uvx --with tox-uv tox -e compat` | `test-compat` 의존성 그룹 (공식 `aerospike` 포함) |
| `all` | `uvx --with tox-uv tox -e all` | `test-all` 의존성 그룹 |
| `matrix` | `uvx --with tox-uv tox` | py310~py314 + py314t 전체 |

### 4. 결과 보고
- 통과한 테스트 수 / 실패한 테스트 수 요약
- 실패한 테스트가 있으면 에러 메시지와 원인 분석

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AEROSPIKE_HOST` | `127.0.0.1` | Aerospike 서버 호스트 |
| `AEROSPIKE_PORT` | `18710` | Aerospike 서버 포트 (로컬 개발용) |
| `RUNTIME` | `podman` | 컨테이너 런타임 (`docker` or `podman`) |

**CI 환경**: GitHub Actions에서는 서비스 컨테이너를 사용하며 `AEROSPIKE_PORT=3000`.

## 테스트 인프라

### 테스트 설정 (`tests/__init__.py`)

```python
AEROSPIKE_CONFIG = {
    "hosts": [(os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
               int(os.environ.get("AEROSPIKE_PORT", "18710")))],
    "cluster_name": "docker",
}
```

### 공유 Fixture (`tests/conftest.py`)

| Fixture | Scope | 설명 |
|---------|-------|------|
| `client` | module | Sync 클라이언트. 서버 미가용 시 `pytest.skip()` |
| `async_client` | function | Async 클라이언트. 서버 미가용 시 `pytest.skip()` |
| `cleanup` | function | `keys` 리스트에 append -> 테스트 후 자동 `client.remove()` |
| `async_cleanup` | function | async 버전의 cleanup. `async_client.remove()` |

### pytest 설정 (`pyproject.toml`)

- `asyncio_mode = "auto"` -> async 테스트에 `@pytest.mark.asyncio` 데코레이터 불필요.
- `tox` 환경에 `pass_env = ["AEROSPIKE_HOST", "AEROSPIKE_PORT"]` 설정으로 환경변수 전달.

### 테스트 디렉토리 구조

```
tests/
├── __init__.py           # AEROSPIKE_CONFIG 정의
├── conftest.py           # 공유 fixture (client, async_client, cleanup)
├── unit/                 # 서버 불필요. 인자 검증, 타입 에러, 미연결 에러 테스트
├── integration/          # 서버 필요. 실제 CRUD, batch, query 등 테스트
│   └── conftest.py       # integration 전용 fixture (autouse cleanup 등)
├── concurrency/          # 스레드 안전성, async 동시성 테스트
│   └── test_freethreading.py  # Python 3.14t 전용 (concurrency tox 환경에서 제외)
├── compatibility/        # 공식 C 클라이언트(`aerospike` PyPI)와 동작 비교
└── feasibility/          # 프레임워크 통합 테스트
    ├── test_fastapi.py   # FastAPI 앱에서 AsyncClient 사용
    └── test_gunicorn.py  # Gunicorn multi-worker에서 Client 사용
```

## CI 워크플로우 (`ci.yaml`) 대응

| CI Job | 테스트 타입 | Python | 서버 |
|--------|------------|--------|------|
| lint | pre-commit (ruff, clippy, fmt) | 3.13 | No |
| build | unit (매트릭스) | 3.10~3.14 | No |
| build-freethreaded | unit | 3.14t | No |
| integration | all | 3.13 | AS 7.2 + latest |
| test-concurrency | concurrency | 3.13 | AS latest |
| test-concurrency-freethreaded | freethreading | 3.14t | AS latest |
| feasibility | fastapi, gunicorn | 3.13 | AS latest |
| compatibility | compat | 3.13 | AS latest |
