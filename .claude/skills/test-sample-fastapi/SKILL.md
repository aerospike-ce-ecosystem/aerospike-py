---
name: test-sample-fastapi
description: Build aerospike-py and run sample-fastapi integration tests to verify changes work in a real FastAPI application
disable-model-invocation: true
---

# Test Sample FastAPI

aerospike-py에 변경사항이 생겼을 때, 로컬에서 빌드 후 sample-fastapi 앱이 정상 동작하는지 검증합니다.

## 프로젝트 구조

```
examples/sample-fastapi/
├── app/
│   ├── main.py              # FastAPI 앱 (lifespan으로 AsyncClient 관리)
│   ├── config.py             # 설정
│   ├── dependencies.py       # FastAPI 의존성 (Request.app.state.aerospike)
│   ├── models.py             # Pydantic 모델
│   └── routers/
│       ├── records.py        # CRUD 엔드포인트
│       ├── batch.py          # 배치 연산
│       ├── operations.py     # operate 연산
│       ├── indexes.py        # 인덱스 관리
│       ├── truncate.py       # truncate
│       ├── udf.py            # UDF 관리
│       ├── cluster.py        # 클러스터 정보
│       ├── admin_users.py    # 사용자 관리
│       ├── admin_roles.py    # 역할 관리
│       ├── users.py          # 사용자 CRUD
│       ├── numpy_batch.py    # NumPy 배치 엔드포인트
│       └── observability.py  # 메트릭/트레이싱 엔드포인트
├── tests/
│   ├── conftest.py           # TestContainers 기반 Aerospike 서버 + FastAPI TestClient
│   ├── test_records.py       # CRUD 테스트
│   ├── test_batch.py         # 배치 테스트
│   ├── test_operations.py    # operate 테스트
│   ├── test_indexes.py       # 인덱스 테스트
│   ├── test_truncate.py      # truncate 테스트
│   ├── test_udf.py           # UDF 테스트
│   ├── test_cluster.py       # 클러스터 정보 테스트
│   ├── test_health.py        # 헬스 체크 테스트
│   ├── test_admin_users.py   # 사용자 관리 테스트
│   ├── test_admin_roles.py   # 역할 관리 테스트
│   ├── test_users.py         # 사용자 CRUD 테스트
│   ├── test_numpy_batch.py   # NumPy 배치 테스트
│   └── test_observability.py # 메트릭/트레이싱 테스트
└── pyproject.toml            # uv.sources: aerospike-py = { path = "../.." }
```

## 실행 단계

### 1. aerospike-py 빌드
프로젝트 루트에서 Rust 네이티브 모듈을 빌드합니다:
```bash
cd /Users/ksr/github/aerospike-py && uv run maturin develop --release
```
빌드 실패 시 에러를 분석하고 수정 방향을 제안하세요.

### 2. sample-fastapi 의존성 동기화
빌드된 aerospike-py를 sample-fastapi에 반영합니다:
```bash
cd /Users/ksr/github/aerospike-py/examples/sample-fastapi && uv sync --extra dev
```
`pyproject.toml`의 `[tool.uv.sources]`에 `aerospike-py = { path = "../.." }`로 로컬 경로가 설정되어 있으므로, 방금 빌드한 패키지가 자동으로 사용됩니다.

### 3. Aerospike 서버 확인
로컬 Aerospike 서버가 실행 중인지 확인합니다:
```bash
docker ps | grep aerospike || podman ps | grep aerospike
```
- 실행 중이면 그대로 진행 (conftest.py가 `AEROSPIKE_HOST`/`AEROSPIKE_PORT` 환경변수 또는 기본 `127.0.0.1:3000`에 연결 시도)
- 실행 중이 아니면 TestContainers가 자동으로 컨테이너를 생성하므로 Docker/Podman 데몬이 실행 중인지만 확인

### 4. 테스트 실행
sample-fastapi 테스트를 실행합니다:
```bash
cd /Users/ksr/github/aerospike-py/examples/sample-fastapi && uv run pytest tests/ -v
```

### 5. 결과 보고
- 모든 테스트 통과 시: 변경사항이 FastAPI 앱에서 정상 동작함을 확인
- 실패한 테스트가 있으면:
  - 실패한 테스트 이름과 에러 메시지를 정리
  - aerospike-py 변경사항과의 관계 분석
  - 수정 방향 제안 (aerospike-py 쪽 문제인지, sample-fastapi 쪽 문제인지 구분)

## 테스트 인프라 상세

### conftest.py 주요 Fixture

| Fixture | Scope | 설명 |
|---------|-------|------|
| `aerospike_container` | session | TestContainers로 Aerospike CE 8.1 시작. 로컬 서버가 이미 가용하면 재사용. `(container, port)` 반환. |
| `jaeger_container` | session | Jaeger all-in-one 컨테이너. 트레이싱 테스트용. `(container, otlp_port, ui_port)` 반환. |
| `aerospike_client` | session | sync 클라이언트 (데이터 setup/teardown용). `POLICY_KEY_SEND` 설정. |
| `client` | session | FastAPI `TestClient`. lifespan에서 `AsyncClient` 생성. `OTEL_SDK_DISABLED=true` 기본 설정. |
| `cleanup` | function (autouse) | 테스트 후 레코드 자동 정리. `keys` 리스트에 append하면 자동 삭제. |

### TestContainers 동작

1. `AEROSPIKE_HOST`/`AEROSPIKE_PORT` 환경변수 또는 기본 `127.0.0.1:3000`에 TCP 연결 시도
2. 성공하면 기존 서버 재사용 (컨테이너 생성 안 함)
3. 실패하면 랜덤 포트로 Aerospike CE 컨테이너 자동 생성
4. `heartbeat-received` 로그를 기다린 후 2초 추가 대기
5. 커스텀 `aerospike.template.conf`를 마운트하여 access-port 설정

### FastAPI TestClient 동작

`conftest.py`의 `client` fixture가 FastAPI 앱의 lifespan을 오버라이드합니다:
1. `OTEL_SDK_DISABLED=true` 환경변수 설정 (Jaeger 없이 테스트)
2. `aerospike_py.set_log_level(LOG_LEVEL_INFO)` 로그 레벨 설정
3. `aerospike_py.init_tracing()` 트레이싱 초기화
4. `AsyncClient` 생성 후 `app.state.aerospike`에 저장
5. 테스트 후 `AsyncClient.close()` + `shutdown_tracing()`

## CI에서의 실행

CI의 `feasibility` job에서 `tox -e fastapi`로 실행됩니다:
- Python 3.13, Aerospike latest 서비스 컨테이너 사용
- `AEROSPIKE_PORT=3000` 환경변수
- 의존성 그룹: `test-fastapi` (pytest, pytest-asyncio, fastapi, httpx)
