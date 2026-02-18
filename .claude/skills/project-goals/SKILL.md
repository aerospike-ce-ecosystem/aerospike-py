# Project Goals

## 핵심 목표

Aerospike Rust Client(`aerospike` crate + `aerospike-core`)를 PyO3로 래핑하여, Python에서 Aerospike를 고성능으로 사용할 수 있는 클라이언트 라이브러리를 만든다.

## 주요 기능 축

### 1. Sync / Async Client

- Rust 네이티브 클라이언트를 기반으로 **동기(`Client`) + 비동기(`AsyncClient`)** 양쪽 API를 제공한다.
- 공식 C 클라이언트(`aerospike` PyPI 패키지)와 **API 호환성**을 유지하면 좋지만 Rust 네이티브 클라이언트 API 스펙을 더 우선한다.
- Python 3.10~3.14 (3.14t free-threaded 포함) 지원.
- Sync Client: `py.detach()`로 GIL 해제 후 `RUNTIME.block_on()`으로 async 호출.
- Async Client: `future_into_py()`로 Python awaitable 반환, `Python::attach()`로 GIL 재획득.

### 2. NumPy 통합

- `batch_read` 등 배치 연산에서 **NumPy structured array**를 입출력으로 지원한다.
- 대량 레코드를 Python dict 변환 없이 zero-copy에 가깝게 처리하여 성능을 높인다.
- optional dependency (`pip install aerospike-py[numpy]`)로 제공.
- `NumpyBatchRecords` 클래스: 배치 결과를 NumPy structured array로 래핑.

### 3. Observability (OpenTelemetry + Prometheus)

- **Tracing**: 각 DB 연산을 OTel span으로 자동 계측. W3C TraceContext 전파 지원. `traced_op!` / `traced_exists_op!` 매크로 사용.
- **Metrics**: Prometheus 형식의 연산별 지연시간 히스토그램. 내장 metrics HTTP 서버 제공 (`start_metrics_server(port)`).
- **Logging**: Rust 내부 로그를 Python 로그 레벨과 연동 (`set_log_level()`).
- `otel` feature는 `pyproject.toml`의 `[tool.maturin] features`에서 기본 활성화. Python optional dependency (`pip install aerospike-py[otel]`)로 `opentelemetry-api` 설치.

### 4. Expression 필터

- Aerospike 서버 사이드 필터를 Python에서 빌더 패턴으로 구성.
- `aerospike_py.exp` 모듈에 60+ 빌더 함수 제공 (values, bins, metadata, comparison, logical, numeric, pattern, control flow).

### 5. CDT (Collection Data Types) 연산

- `list_operations` / `map_operations` 모듈로 List/Map CDT 연산을 `operate()` API에서 사용.
- List: 37개 연산 (append, insert, get_by_index, remove_by_rank_range 등).
- Map: 33개 연산 (put, get_by_key, remove_by_rank_range 등).

## 설계 원칙

- **Rust 우선**: 핵심 로직은 Rust에서 구현하고, Python 레이어는 얇은 래퍼로 유지한다.
- **공식 클라이언트 호환**: 메서드 시그니처, 상수, 예외를 공식 C 클라이언트와 가능한 동일하게 맞춘다.
- **Type-safe**: `.pyi` 스텁을 제공하여 IDE 자동완성과 타입 체커를 완벽히 지원한다.
- **Zero Python dependency**: 기본 설치 시 외부 Python 의존성 없음. NumPy, OTel은 optional.
- **NamedTuple 반환**: `get`, `select`, `exists` 등 복합 반환값은 Python `NamedTuple`로 래핑하여 `record.key`, `record.bins` 등 이름 접근 제공.

## 기술 스택

| 레이어        | 기술                                                 | 버전        |
| ------------- | ---------------------------------------------------- | ----------- |
| Core          | `aerospike` + `aerospike-core` crate                 | 2.0.0-alpha.9 |
| Binding       | PyO3 + maturin                                       | PyO3 0.28, maturin >=1.9,<2.0 |
| Async Runtime | Tokio (multi-thread) + pyo3-async-runtimes           | tokio 1.x   |
| Metrics       | prometheus-client (Rust)                              | 0.23        |
| Tracing       | opentelemetry + opentelemetry-otlp (gRPC/Tonic)       | 0.28 (optional `otel` feature) |
| NumPy         | 직접 buffer 조작 (numpy C API via PyO3)                | numpy >=2.0 |
| Build         | uv (패키지 매니저) + tox-uv (테스트 매트릭스)            | -           |
| CI/CD         | GitHub Actions (lint, build 3.10-3.14+3.14t, integration, concurrency, feasibility, compat) | - |

## 현재 구현 상태

### 완료

- **Sync/Async Client**: CRUD (`put`, `get`, `select`, `exists`, `remove`, `append`, `prepend`, `increment`, `touch`)
- **Batch 연산**: `batch_read`, `batch_operate`, `batch_remove`, `batch_read_numpy` (NumPy structured array 반환)
- **Operate**: `operate()` (반환값 dict), `operate_ordered()` (반환값 순서 보존 list[BinTuple])
- **Query**: `query()` (sync) / `query()` (async) - predicate 필터, expression 필터, `foreach()` 콜백, `results()` 일괄 수집
- **Index**: `index_create()` / `index_remove()` - `INDEX_STRING`, `INDEX_NUMERIC`, `INDEX_GEO2DSPHERE`, `INDEX_BLOB`
- **Truncate**: `truncate()`
- **UDF**: `udf_put()` / `udf_remove()` / `udf_list()` / `udf_get()`
- **Admin**: `admin_create_user()` / `admin_drop_user()` / `admin_set_password()` / `admin_change_password()` / `admin_grant_roles()` / `admin_revoke_roles()` / `admin_query_user()` / `admin_query_users()` / `admin_create_role()` / `admin_drop_role()` / `admin_grant_privileges()` / `admin_revoke_privileges()` / `admin_query_role()` / `admin_query_roles()`
- **Info**: `info_all()` / `info_single_node()`
- **Prometheus metrics**: 히스토그램, 내장 HTTP 서버 (`start_metrics_server()` / `stop_metrics_server()`)
- **OTel tracing**: span 생성, W3C TraceContext 전파 (`init_tracing()` / `shutdown_tracing()`)
- **Logging**: Rust -> Python 레벨 연동 (`set_log_level()`)
- **Expression 필터**: 60+ 빌더 함수
- **List/Map CDT 연산 헬퍼**: `list_operations` (37), `map_operations` (33)
- **NumPy batch_read**: `batch_read_numpy()` + `NumpyBatchRecords` 클래스
- **공식 C 클라이언트 호환성 테스트** (완벽하게 호환할 필요 없음)
- **Python 3.14t free-threaded 지원**: CI에서 빌드 + 유닛 + 동시성 테스트

### 미구현 / 향후 과제

- scan 함수는 deprecated 되었으므로 구현하지 않음
- Batch write (batch_operate로 대체 가능하나 별도 API 검토)
- batch write numpy (numpy structured array로 주어진 데이터를 records list로 batch_write하는 API 스펙)
- HyperLogLog 연산 헬퍼
- Bitwise 연산 헬퍼
- Connection pool 세부 설정 노출
- Rack-aware 읽기 최적화
- Query Pagination (파티션 필터 기반)
- Aggregate (UDF 기반 MapReduce)
