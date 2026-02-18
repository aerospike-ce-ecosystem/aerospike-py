# aerospike-py

Aerospike NoSQL 데이터베이스를 위한 Python 클라이언트 라이브러리.
**Rust(PyO3)로 작성**되어 네이티브 바이너리로 컴파일되며, Python에서 sync/async 양쪽 API를 제공한다.

## 설치

```bash
pip install aerospike-py
```

> Python 3.10~3.14 (3.14t free-threaded 포함), CPython 전용. macOS(arm64, x86_64) 및 Linux(x86_64, aarch64) 지원.

## 프로젝트 구조

```
aerospike-py/
├── rust/src/               # Rust 네이티브 모듈 (PyO3 바인딩)
│   ├── client.rs           # Sync Client 구현
│   ├── async_client.rs     # Async Client 구현
│   ├── errors.rs           # 에러 매핑 (Aerospike → Python 예외)
│   ├── operations.rs       # operate/operate_ordered 연산 변환
│   ├── query.rs            # Query, Scan 객체
│   ├── constants.rs        # 상수 정의
│   ├── expressions.rs      # Expression 필터 파싱
│   ├── metrics.rs          # Prometheus 메트릭 수집
│   ├── tracing.rs          # OpenTelemetry 트레이싱
│   ├── policy/             # 정책 파싱 (read, write, admin, batch, query, client)
│   └── types/              # 타입 변환 (key, value, record, bin, host)
├── src/aerospike_py/       # Python 패키지
│   ├── __init__.py         # Client/AsyncClient 래퍼, 팩토리 함수, 상수 re-export
│   ├── __init__.pyi        # Type stubs
│   ├── exception.py        # 예외 클래스 re-export
│   ├── predicates.py       # 쿼리 프레디케이트 헬퍼
│   ├── list_operations.py  # List CDT 연산 헬퍼
│   ├── map_operations.py   # Map CDT 연산 헬퍼
│   ├── exp.py              # Expression 필터 빌더
│   └── numpy_batch.py      # NumPy 기반 배치 결과
├── tests/
│   ├── unit/               # 유닛 테스트 (서버 불필요)
│   ├── integration/        # 통합 테스트 (Aerospike 서버 필요)
│   ├── concurrency/        # 스레드 안전성 테스트
│   ├── compatibility/      # 공식 C 클라이언트 호환성 테스트
│   └── feasibility/        # 프레임워크 통합 테스트 (FastAPI, Gunicorn)
└── pyproject.toml          # 빌드 설정 (maturin)
```

## 개발 환경

패키지 매니저로 **uv**를 사용한다. Makefile에 주요 명령어가 정의되어 있다.

```bash
# 의존성 설치
make install                        # uv sync --all-groups

# Rust 빌드
make build                          # uv run maturin develop --release
cargo check --manifest-path rust/Cargo.toml  # 컴파일 체크만 (빠름)

# 테스트
make test-unit                      # 유닛 테스트 (서버 불필요)
make test-integration               # 통합 테스트 (Aerospike 서버 필요)
make test-concurrency               # 스레드 안전성 테스트
make test-compat                    # 공식 클라이언트 호환성 테스트
make test-all                       # 전체 테스트
make test-matrix                    # Python 3.10~3.14 매트릭스 테스트 (tox)

# 린트 & 포맷
make lint                           # ruff check + clippy
make fmt                            # ruff format + cargo fmt

# 로컬 Aerospike 서버
make run-aerospike-ce               # Docker로 Aerospike CE 실행 (port 3000)

# 벤치마크
make run-benchmark                  # aerospike-py vs 공식 클라이언트 비교
make run-numpy-benchmark            # NumPy 배치 벤치마크
```

### Pre-commit Hooks

커밋 시 자동 실행: trailing-whitespace, ruff format/lint, pyright, cargo fmt, cargo clippy (-D warnings)

### 주의사항

- OpenTelemetry(`otel`)은 기본 빌드에 항상 포함됨 (별도 feature flag 불필요)
- 통합 테스트 실행 전 `make run-aerospike-ce`로 로컬 서버 필요
- maturin 버전 `>=1.9,<2.0`으로 고정
- `AEROSPIKE_HOST`, `AEROSPIKE_PORT` 환경변수로 서버 주소 변경 가능
- `RUNTIME` 환경변수로 docker/podman 선택 가능 (기본: docker)

## 핵심 타입

```python
# NamedTuple 반환 타입 (from aerospike_py.types)
AerospikeKey = NamedTuple(namespace, set_name, user_key, digest)
RecordMetadata = NamedTuple(gen, ttl)
Bins = dict[str, Any]
Record = NamedTuple(key: AerospikeKey | None, meta: RecordMetadata | None, bins: Bins | None)
ExistsResult = NamedTuple(key: AerospikeKey | None, meta: RecordMetadata | None)
InfoNodeResult = NamedTuple(node_name, error_code, response)
BinTuple = NamedTuple(name, value)
OperateOrderedResult = NamedTuple(key, meta, ordered_bins: list[BinTuple])

# TypedDict 입력 타입
ReadPolicy, WritePolicy, BatchPolicy, AdminPolicy, QueryPolicy  # 각 API별 정책
WriteMeta = TypedDict(gen: int, ttl: int)                       # put/remove 등의 meta 파라미터
ClientConfig = TypedDict(hosts, cluster_name, ...)              # client() 설정
Privilege = TypedDict(code, ns, set)                            # admin API 권한

# 기존 호환 alias
Key = tuple[str, str, str | int | bytes]       # 입력용 키 타입

# 속성 접근 예시
record = client.get(key)
record.meta.gen     # generation (NamedTuple 필드 접근)
record.meta.ttl     # TTL
record.key.namespace  # namespace
record.bins["name"]   # bin 값
```

---

## Client (Sync)

```python
import aerospike_py

client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
```

### Connection

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `connect` | `(username=None, password=None) -> Client` | 클러스터 연결. 메서드 체이닝 지원 |
| `is_connected` | `() -> bool` | 연결 상태 확인 |
| `close` | `() -> None` | 연결 종료 |
| `get_node_names` | `() -> list[str]` | 클러스터 노드 이름 목록 |

Context manager 지원: `with aerospike_py.client(config).connect() as c: ...`

### Info

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `info_all` | `(command, policy=None) -> list[InfoNodeResult]` | 모든 노드에 info 명령 전송. NamedTuple `(node_name, error_code, response)` 반환 |
| `info_random_node` | `(command, policy=None) -> str` | 랜덤 노드에 info 명령 전송. 응답 문자열 반환 |

### CRUD

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `put` | `(key, bins, meta=None, policy=None) -> None` | 레코드 쓰기 |
| `get` | `(key, policy=None) -> Record` | 레코드 읽기 (전체 bin) |
| `select` | `(key, bins, policy=None) -> Record` | 특정 bin만 읽기 |
| `exists` | `(key, policy=None) -> ExistsResult` | 레코드 존재 여부 확인 |
| `remove` | `(key, meta=None, policy=None) -> None` | 레코드 삭제 |
| `touch` | `(key, val=0, meta=None, policy=None) -> None` | TTL 갱신 |

### String / Numeric

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `append` | `(key, bin, val, meta=None, policy=None) -> None` | 문자열 append |
| `prepend` | `(key, bin, val, meta=None, policy=None) -> None` | 문자열 prepend |
| `increment` | `(key, bin, offset, meta=None, policy=None) -> None` | 정수/실수 증감 |
| `remove_bin` | `(key, bin_names, meta=None, policy=None) -> None` | bin 삭제 (nil 설정) |

### Multi-operation

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `operate` | `(key, ops, meta=None, policy=None) -> Record` | 단일 레코드에 복합 연산 |
| `operate_ordered` | `(key, ops, meta=None, policy=None) -> OperateOrderedResult` | 복합 연산 (순서 보존). NamedTuple `(key, meta, ordered_bins: list[BinTuple])` 반환 |

### Batch

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `batch_read` | `(keys, bins=None, policy=None, _dtype=None) -> BatchRecords \| NumpyBatchRecords` | 다중 레코드 읽기. `_dtype` 지정 시 NumPy 반환 |
| `batch_operate` | `(keys, ops, policy=None) -> list[Record]` | 다중 레코드 복합 연산 |
| `batch_remove` | `(keys, policy=None) -> list[Record]` | 다중 레코드 삭제 |

### Query / Scan

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `query` | `(namespace, set_name) -> Query` | Secondary Index 쿼리 객체 생성 |
| `scan` | `(namespace, set_name) -> Scan` | 전체 스캔 객체 생성 |

**Query 객체:**
- `select(*bins)` — 조회할 bin 지정
- `where(predicate)` — 프레디케이트 필터 설정
- `results(policy=None) -> list[Record]` — 결과 반환
- `foreach(callback, policy=None)` — 콜백으로 결과 순회

**Scan 객체:**
- `select(*bins)` — 조회할 bin 지정
- `results(policy=None) -> list[Record]` — 결과 반환
- `foreach(callback, policy=None)` — 콜백으로 결과 순회

### Secondary Index

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `index_integer_create` | `(namespace, set_name, bin_name, index_name, policy=None) -> None` | 정수 인덱스 생성 |
| `index_string_create` | `(namespace, set_name, bin_name, index_name, policy=None) -> None` | 문자열 인덱스 생성 |
| `index_geo2dsphere_create` | `(namespace, set_name, bin_name, index_name, policy=None) -> None` | GeoJSON 인덱스 생성 |
| `index_remove` | `(namespace, index_name, policy=None) -> None` | 인덱스 삭제 |

### Truncate

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `truncate` | `(namespace, set_name, nanos=0, policy=None) -> None` | namespace/set 레코드 일괄 삭제 |

### UDF (User-Defined Functions)

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `udf_put` | `(filename, udf_type=0, policy=None) -> None` | UDF 모듈 등록 (Lua만 지원) |
| `udf_remove` | `(module, policy=None) -> None` | UDF 모듈 제거 |
| `apply` | `(key, module, function, args=None, policy=None) -> Any` | 단일 레코드에 UDF 실행 |

### Admin: User

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `admin_create_user` | `(username, password, roles, policy=None) -> None` | 사용자 생성 |
| `admin_drop_user` | `(username, policy=None) -> None` | 사용자 삭제 |
| `admin_change_password` | `(username, password, policy=None) -> None` | 비밀번호 변경 |
| `admin_grant_roles` | `(username, roles, policy=None) -> None` | 역할 부여 |
| `admin_revoke_roles` | `(username, roles, policy=None) -> None` | 역할 회수 |
| `admin_query_user_info` | `(username, policy=None) -> dict` | 사용자 정보 조회 |
| `admin_query_users_info` | `(policy=None) -> list[dict]` | 전체 사용자 정보 조회 |

### Admin: Role

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| `admin_create_role` | `(role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0) -> None` | 역할 생성 |
| `admin_drop_role` | `(role, policy=None) -> None` | 역할 삭제 |
| `admin_grant_privileges` | `(role, privileges, policy=None) -> None` | 권한 부여 |
| `admin_revoke_privileges` | `(role, privileges, policy=None) -> None` | 권한 회수 |
| `admin_query_role` | `(role, policy=None) -> dict` | 역할 정보 조회 |
| `admin_query_roles` | `(policy=None) -> list[dict]` | 전체 역할 정보 조회 |
| `admin_set_whitelist` | `(role, whitelist, policy=None) -> None` | IP 화이트리스트 설정 |
| `admin_set_quotas` | `(role, read_quota=0, write_quota=0, policy=None) -> None` | 쿼터 설정 |

---

## AsyncClient

`Client`와 동일한 API를 `async/await`로 제공한다. 모든 I/O 메서드가 코루틴을 반환한다.

```python
import aerospike_py

async def main():
    client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()

    await client.put(("test", "demo", "key1"), {"name": "Alice"})
    record = await client.get(("test", "demo", "key1"))
    print(record.bins)       # {"name": "Alice"}
    print(record.meta.gen)   # generation number

    await client.close()
```

`async with` context manager 지원:
```python
async with aerospike_py.AsyncClient(config) as client:
    await client.connect()
    ...
```

> `query()` 메서드는 Sync Client 전용. AsyncClient에서는 `scan(namespace, set_name)` 사용.

---

## 서브모듈

### `aerospike_py.predicates` — 쿼리 프레디케이트

```python
from aerospike_py import predicates as p

query.where(p.equals("age", 30))
query.where(p.between("age", 20, 40))
query.where(p.contains("tags", aerospike_py.INDEX_TYPE_LIST, "python"))
```

| 함수 | 설명 |
|------|------|
| `equals(bin_name, val)` | 등호 비교 |
| `between(bin_name, min_val, max_val)` | 범위 비교 |
| `contains(bin_name, index_type, val)` | 컬렉션 포함 여부 (LIST/MAPKEYS/MAPVALUES) |
| `geo_within_geojson_region(bin_name, geojson)` | GeoJSON 영역 내 포함 |
| `geo_within_radius(bin_name, lat, lng, radius)` | 반경 내 포함 |
| `geo_contains_geojson_point(bin_name, geojson)` | GeoJSON 포인트 포함 |

### `aerospike_py.list_operations` — List CDT 연산

`client.operate()` / `client.operate_ordered()`에서 사용하는 List CDT 연산 딕셔너리를 생성한다.

```python
from aerospike_py import list_operations as lop

client.operate(key, [
    lop.list_append("mylist", "new_value"),
    lop.list_size("mylist"),
])
```

주요 함수: `list_append`, `list_append_items`, `list_insert`, `list_insert_items`, `list_pop`, `list_pop_range`, `list_remove`, `list_remove_range`, `list_set`, `list_trim`, `list_clear`, `list_size`, `list_get`, `list_get_range`, `list_get_by_value`, `list_get_by_value_list`, `list_get_by_value_range`, `list_get_by_index`, `list_get_by_index_range`, `list_get_by_rank`, `list_get_by_rank_range`, `list_remove_by_value`, `list_remove_by_value_list`, `list_remove_by_value_range`, `list_remove_by_index`, `list_remove_by_index_range`, `list_remove_by_rank`, `list_remove_by_rank_range`, `list_increment`, `list_sort`, `list_set_order`

### `aerospike_py.map_operations` — Map CDT 연산

```python
from aerospike_py import map_operations as mop

client.operate(key, [
    mop.map_put("mymap", "key1", "val1"),
    mop.map_size("mymap"),
])
```

주요 함수: `map_set_order`, `map_put`, `map_put_items`, `map_increment`, `map_decrement`, `map_clear`, `map_size`, `map_remove_by_key`, `map_remove_by_key_list`, `map_remove_by_key_range`, `map_remove_by_value`, `map_remove_by_value_list`, `map_remove_by_value_range`, `map_remove_by_index`, `map_remove_by_index_range`, `map_remove_by_rank`, `map_remove_by_rank_range`, `map_get_by_key`, `map_get_by_key_range`, `map_get_by_key_list`, `map_get_by_value`, `map_get_by_value_list`, `map_get_by_value_range`, `map_get_by_index`, `map_get_by_index_range`, `map_get_by_rank`, `map_get_by_rank_range`

### `aerospike_py.exp` — Expression 필터

서버 사이드 필터링을 위한 Expression 빌더 (Aerospike Server >= 5.2).

```python
from aerospike_py import exp

# age > 21인 레코드만 조회
expr = exp.gt(exp.int_bin("age"), exp.int_val(21))
record = client.get(key, policy={"expressions": expr})
```

주요 카테고리:
- **값 생성**: `int_val`, `float_val`, `string_val`, `bool_val`, `blob_val`, `list_val`, `map_val`, `nil`, `infinity`, `wildcard`
- **Bin 접근**: `int_bin`, `float_bin`, `string_bin`, `list_bin`, `map_bin`, `bin_exists`, `bin_type`
- **메타데이터**: `key`, `key_exists`, `set_name`, `record_size`, `ttl`, `last_update`, `void_time`, `is_tombstone`, `digest_modulo`
- **비교**: `eq`, `ne`, `gt`, `ge`, `lt`, `le`
- **논리**: `and_`, `or_`, `not_`, `xor_`
- **수치**: `num_add`, `num_sub`, `num_mul`, `num_div`, `num_mod`, `num_pow`, `num_log`, `num_abs`, `num_floor`, `num_ceil`, `min_`, `max_`, `to_int`, `to_float`
- **비트**: `int_and`, `int_or`, `int_xor`, `int_not`, `int_lshift`, `int_rshift`
- **패턴**: `regex_compare`, `geo_compare`
- **제어**: `cond`, `var`, `def_`, `let_`

### `aerospike_py.numpy_batch` — NumPy 배치 결과

`batch_read()`에 `_dtype` 파라미터를 전달하면 `NumpyBatchRecords`를 반환한다.

```python
import numpy as np

dtype = np.dtype([("age", "i4"), ("score", "f8")])
result = client.batch_read(keys, bins=["age", "score"], _dtype=dtype)
# result.records → np.ndarray (structured array)
# result.get(key) → np.void (단일 레코드)
```

---

## Observability

### Metrics (Prometheus)

```python
aerospike_py.start_metrics_server(port=9464)  # /metrics 엔드포인트 시작
aerospike_py.get_metrics()                     # Prometheus 텍스트 포맷 반환
aerospike_py.stop_metrics_server()             # 서버 중지
```

### Tracing (OpenTelemetry)

`otel` feature 활성화 시 사용 가능. `OTEL_*` 환경변수로 설정.

```python
aerospike_py.init_tracing()       # OTel 트레이서 초기화
# ... 작업 수행 ...
aerospike_py.shutdown_tracing()   # 스팬 플러시 및 종료
```

Span attributes: `db.system.name`, `db.namespace`, `db.collection.name`, `db.operation.name`, `server.address`, `server.port`, `db.aerospike.cluster_name`

### Logging

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

| 상수 | 값 | 설명 |
|------|-----|------|
| `LOG_LEVEL_OFF` | -1 | 로그 비활성화 |
| `LOG_LEVEL_ERROR` | 0 | 에러만 |
| `LOG_LEVEL_WARN` | 1 | 경고 이상 |
| `LOG_LEVEL_INFO` | 2 | 정보 이상 |
| `LOG_LEVEL_DEBUG` | 3 | 디버그 이상 |
| `LOG_LEVEL_TRACE` | 4 | 전체 트레이스 |

---

## 예외 계층

```
AerospikeError
├── ClientError
├── ClusterError
├── InvalidArgError
├── AerospikeTimeoutError (= TimeoutError)
├── RecordError
│   ├── RecordNotFound
│   ├── RecordExistsError
│   ├── RecordGenerationError
│   ├── RecordTooBig
│   ├── BinNameError
│   ├── BinExistsError
│   ├── BinNotFound
│   ├── BinTypeError
│   └── FilteredOut
└── ServerError
    ├── AerospikeIndexError (= IndexError)
    │   ├── IndexNotFound
    │   └── IndexFoundError
    ├── QueryError
    │   └── QueryAbortedError
    ├── AdminError
    └── UDFError
```

---

## 상수

### Policy

| 카테고리 | 상수 |
|----------|------|
| Key | `POLICY_KEY_DIGEST=0`, `POLICY_KEY_SEND=1` |
| Exists | `POLICY_EXISTS_IGNORE=0`, `POLICY_EXISTS_UPDATE=1`, `POLICY_EXISTS_UPDATE_ONLY=1`, `POLICY_EXISTS_REPLACE=2`, `POLICY_EXISTS_REPLACE_ONLY=3`, `POLICY_EXISTS_CREATE_ONLY=4` |
| Generation | `POLICY_GEN_IGNORE=0`, `POLICY_GEN_EQ=1`, `POLICY_GEN_GT=2` |
| Replica | `POLICY_REPLICA_MASTER=0`, `POLICY_REPLICA_SEQUENCE=1`, `POLICY_REPLICA_PREFER_RACK=2` |
| Commit Level | `POLICY_COMMIT_LEVEL_ALL=0`, `POLICY_COMMIT_LEVEL_MASTER=1` |
| Read Mode AP | `POLICY_READ_MODE_AP_ONE=0`, `POLICY_READ_MODE_AP_ALL=1` |

### TTL

| 상수 | 값 | 설명 |
|------|-----|------|
| `TTL_NAMESPACE_DEFAULT` | 0 | 네임스페이스 기본값 사용 |
| `TTL_NEVER_EXPIRE` | -1 | 만료 없음 |
| `TTL_DONT_UPDATE` | -2 | TTL 갱신 안 함 |
| `TTL_CLIENT_DEFAULT` | -3 | 클라이언트 기본값 |

### Auth Mode

`AUTH_INTERNAL=0`, `AUTH_EXTERNAL=1`, `AUTH_PKI=2`

### Operator

`OPERATOR_READ=1`, `OPERATOR_WRITE=2`, `OPERATOR_INCR=5`, `OPERATOR_APPEND=9`, `OPERATOR_PREPEND=10`, `OPERATOR_TOUCH=11`, `OPERATOR_DELETE=12`

### Index Type / Collection Type

- Type: `INDEX_NUMERIC`, `INDEX_STRING`, `INDEX_BLOB`, `INDEX_GEO2DSPHERE`
- Collection: `INDEX_TYPE_DEFAULT`, `INDEX_TYPE_LIST`, `INDEX_TYPE_MAPKEYS`, `INDEX_TYPE_MAPVALUES`

### List / Map 상수

- List Return: `LIST_RETURN_NONE`, `LIST_RETURN_INDEX`, `LIST_RETURN_REVERSE_INDEX`, `LIST_RETURN_RANK`, `LIST_RETURN_REVERSE_RANK`, `LIST_RETURN_COUNT`, `LIST_RETURN_VALUE`, `LIST_RETURN_EXISTS`
- List Order: `LIST_UNORDERED`, `LIST_ORDERED`
- List Sort: `LIST_SORT_DEFAULT`, `LIST_SORT_DROP_DUPLICATES`
- List Write: `LIST_WRITE_DEFAULT`, `LIST_WRITE_ADD_UNIQUE`, `LIST_WRITE_INSERT_BOUNDED`, `LIST_WRITE_NO_FAIL`, `LIST_WRITE_PARTIAL`
- Map Return: `MAP_RETURN_NONE`, `MAP_RETURN_INDEX`, `MAP_RETURN_REVERSE_INDEX`, `MAP_RETURN_RANK`, `MAP_RETURN_REVERSE_RANK`, `MAP_RETURN_COUNT`, `MAP_RETURN_KEY`, `MAP_RETURN_VALUE`, `MAP_RETURN_KEY_VALUE`, `MAP_RETURN_EXISTS`
- Map Order: `MAP_UNORDERED`, `MAP_KEY_ORDERED`, `MAP_KEY_VALUE_ORDERED`
- Map Write: `MAP_WRITE_FLAGS_DEFAULT`, `MAP_WRITE_FLAGS_CREATE_ONLY`, `MAP_WRITE_FLAGS_UPDATE_ONLY`, `MAP_WRITE_FLAGS_NO_FAIL`, `MAP_WRITE_FLAGS_PARTIAL`, `MAP_UPDATE`, `MAP_UPDATE_ONLY`, `MAP_CREATE_ONLY`

### Privilege Codes

`PRIV_READ=10`, `PRIV_WRITE=13`, `PRIV_READ_WRITE=11`, `PRIV_READ_WRITE_UDF=12`, `PRIV_USER_ADMIN=0`, `PRIV_SYS_ADMIN=1`, `PRIV_DATA_ADMIN=2`, `PRIV_UDF_ADMIN=3`, `PRIV_SINDEX_ADMIN=4`, `PRIV_TRUNCATE=14`

### Status Codes

`AEROSPIKE_OK=0`, `AEROSPIKE_ERR_SERVER=1`, `AEROSPIKE_ERR_RECORD_NOT_FOUND=2`, `AEROSPIKE_ERR_RECORD_GENERATION=3`, `AEROSPIKE_ERR_PARAM=4`, `AEROSPIKE_ERR_RECORD_EXISTS=5`, `AEROSPIKE_ERR_TIMEOUT=9` 등. 전체 목록은 `__init__.pyi` 참조.

---

## 테스트 설정

통합 테스트에는 Aerospike 서버가 필요하다. `tests/__init__.py`에서 기본 설정:

```python
AEROSPIKE_CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
```

```bash
make run-aerospike-ce               # 로컬 Aerospike 서버 실행
make test-unit                      # 서버 없이 실행 가능
make test-integration               # 서버 필요
```

주요 fixture (`tests/conftest.py`):
- `client` — module-scoped sync 클라이언트
- `async_client` — function-scoped async 클라이언트
- `cleanup` / `async_cleanup` — 테스트 후 자동 레코드 정리

pytest 설정: `asyncio_mode = "auto"` (async 테스트 자동 감지)
