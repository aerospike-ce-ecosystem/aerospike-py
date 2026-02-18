# sample-fastapi

FastAPI + `aerospike-py` AsyncClient를 사용한 예제 프로젝트입니다. aerospike-py의 모든 주요 기능(CRUD, Batch, NumPy, Query, UDF, Admin 등)을 REST API로 제공합니다.

## 구조

```
sample-fastapi/
├── app/
│   ├── main.py              # FastAPI 앱, AsyncClient lifespan 관리
│   ├── config.py            # pydantic-settings 기반 설정
│   ├── models.py            # Pydantic 요청/응답 모델
│   ├── dependencies.py      # FastAPI 의존성 주입 (get_client)
│   └── routers/
│       ├── users.py         # User CRUD
│       ├── records.py       # Record 개별 조작 (select, exists, touch, append, increment 등)
│       ├── operations.py    # Multi-operation (operate, operate_ordered)
│       ├── batch.py         # Batch read/operate/remove
│       ├── numpy_batch.py   # NumPy columnar batch read, 벡터 유사도 검색
│       ├── indexes.py       # Secondary index 생성/삭제
│       ├── truncate.py      # Set truncate
│       ├── udf.py           # UDF 등록/삭제/실행
│       ├── admin_users.py   # Admin 유저 관리
│       ├── admin_roles.py   # Admin 역할 관리
│       └── cluster.py       # 클러스터 연결 상태/노드 조회
├── tests/
│   ├── conftest.py          # testcontainers 기반 Aerospike 컨테이너 픽스처
│   ├── fixtures/
│   │   └── test_udf.lua     # UDF 테스트용 Lua 스크립트
│   ├── test_health.py
│   ├── test_users.py
│   ├── test_records.py
│   ├── test_operations.py
│   ├── test_batch.py
│   ├── test_numpy_batch.py
│   ├── test_indexes.py
│   ├── test_truncate.py
│   ├── test_udf.py
│   ├── test_cluster.py
│   ├── test_admin_users.py  # CE에서는 skip
│   └── test_admin_roles.py  # CE에서는 skip
└── pyproject.toml
```

## 실행 방법

### 1. Aerospike 서버 시작

```bash
# 프로젝트 루트에서
podman compose -f compose.sample-fastapi.yaml up -d
```

### 2. 의존성 설치 및 서버 실행

```bash
uv sync --extra dev
uvicorn app.main:app --reload
```

http://localhost:8000/docs 에서 Swagger UI를 확인할 수 있습니다.

## 테스트

`testcontainers`로 Aerospike 컨테이너를 자동으로 띄우므로, Docker가 실행 중이어야 합니다.

```bash
# sample-fastapi 디렉터리에서
uv run pytest

# 저장소 루트에서
uv run --project examples/sample-fastapi pytest
```

> Admin 관련 테스트(16건)는 Aerospike CE에서 보안 기능을 지원하지 않아 자동 skip됩니다.

## API 엔드포인트

### Health & Cluster

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스 체크 |
| `GET` | `/cluster/connected` | 클라이언트 연결 상태 |
| `GET` | `/cluster/nodes` | 클러스터 노드 목록 |

### Users (CRUD)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/users` | 유저 생성 |
| `GET` | `/users` | 전체 유저 조회 |
| `GET` | `/users/{user_id}` | 유저 단건 조회 |
| `PUT` | `/users/{user_id}` | 유저 수정 (partial update) |
| `DELETE` | `/users/{user_id}` | 유저 삭제 |

### Records (개별 레코드 조작)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/records/select` | 특정 bin만 조회 |
| `POST` | `/records/exists` | 레코드 존재 여부 확인 |
| `POST` | `/records/touch` | TTL 갱신 |
| `POST` | `/records/append` | 문자열 bin에 append |
| `POST` | `/records/prepend` | 문자열 bin에 prepend |
| `POST` | `/records/increment` | 숫자 bin increment |
| `POST` | `/records/remove-bin` | 특정 bin 삭제 |

### Operations (단일 레코드 다중 연산)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/operations/operate` | 여러 연산을 원자적으로 실행 |
| `POST` | `/operations/operate-ordered` | 연산 순서대로 결과 반환 |

### Batch (다중 레코드 일괄 처리)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/batch/read` | 다수 레코드 일괄 조회 |
| `POST` | `/batch/operate` | 다수 레코드에 연산 일괄 실행 |
| `POST` | `/batch/remove` | 다수 레코드 일괄 삭제 |

### NumPy Batch (columnar 조회 & 벡터 검색)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/numpy-batch/read` | NumPy structured array 기반 columnar 조회 |
| `POST` | `/numpy-batch/vector-search` | 코사인 유사도 벡터 검색 (top-k) |

### Index

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/indexes/integer` | 정수 secondary index 생성 |
| `POST` | `/indexes/string` | 문자열 secondary index 생성 |
| `POST` | `/indexes/geo2dsphere` | 지리공간 index 생성 |
| `DELETE` | `/indexes/{ns}/{name}` | Index 삭제 |

### Truncate & UDF

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/truncate` | Set truncate |
| `POST` | `/udf/modules` | UDF 모듈 등록 |
| `DELETE` | `/udf/modules/{name}` | UDF 모듈 삭제 |
| `POST` | `/udf/apply` | UDF 함수 실행 |

### Admin (Enterprise Edition 전용)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/admin/users` | 관리자 유저 생성 |
| `DELETE` | `/admin/users/{username}` | 관리자 유저 삭제 |
| `PUT` | `/admin/users/{username}/password` | 비밀번호 변경 |
| `POST` | `/admin/users/{username}/grant-roles` | 역할 부여 |
| `POST` | `/admin/users/{username}/revoke-roles` | 역할 회수 |
| `GET` | `/admin/users/{username}` | 유저 정보 조회 |
| `GET` | `/admin/users` | 전체 유저 정보 조회 |
| `POST` | `/admin/roles` | 역할 생성 |
| `DELETE` | `/admin/roles/{role}` | 역할 삭제 |
| `POST` | `/admin/roles/{role}/grant-privileges` | 권한 부여 |
| `POST` | `/admin/roles/{role}/revoke-privileges` | 권한 회수 |
| `GET` | `/admin/roles/{role}` | 역할 정보 조회 |
| `GET` | `/admin/roles` | 전체 역할 조회 |
| `PUT` | `/admin/roles/{role}/whitelist` | IP 화이트리스트 설정 |
| `PUT` | `/admin/roles/{role}/quotas` | 읽기/쓰기 쿼터 설정 |

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `APP_AEROSPIKE_HOST` | `127.0.0.1` | Aerospike 호스트 |
| `APP_AEROSPIKE_PORT` | `3000` | Aerospike 포트 |
| `APP_AEROSPIKE_NAMESPACE` | `test` | 사용할 namespace |
| `APP_AEROSPIKE_SET` | `users` | 사용할 set 이름 |

## 사용 예시

```bash
# 유저 생성
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "age": 30}'

# 전체 유저 조회
curl http://localhost:8000/users

# Batch read
curl -X POST http://localhost:8000/batch/read \
  -H "Content-Type: application/json" \
  -d '{"keys": [
    {"namespace": "test", "set_name": "users", "key": "user1"},
    {"namespace": "test", "set_name": "users", "key": "user2"}
  ]}'

# Operate (increment + read)
curl -X POST http://localhost:8000/operations/operate \
  -H "Content-Type: application/json" \
  -d '{"key": {"namespace": "test", "set_name": "users", "key": "user1"},
       "ops": [{"op": 2, "bin": "age", "val": 1}, {"op": 1, "bin": "age"}]}'

# 클러스터 노드 조회
curl http://localhost:8000/cluster/nodes
```
