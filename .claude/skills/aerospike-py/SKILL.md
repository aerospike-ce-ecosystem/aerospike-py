---
name: aerospike-py
description: aerospike-py Python API usage guide for code generation
user-invocable: false
---

# aerospike-py API Quick Reference

Aerospike Python client (Rust/PyO3). Sync/Async API 제공. 기본 포트 18710.
전체 상수/타입 정의는 `src/aerospike_py/__init__.pyi` 참조.

## Client 생성

```python
import aerospike_py

# Sync - 메서드 체이닝
client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()

# Sync - context manager
with aerospike_py.client(config).connect() as client:
    record = client.get(("test", "demo", "key1"))

# Sync - 인증
client = aerospike_py.client(config).connect("admin", "admin")

# Async
client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 18710)]})
await client.connect()

# Async - context manager
async with aerospike_py.AsyncClient(config) as client:
    await client.connect()
    record = await client.get(("test", "demo", "key1"))
```

### ClientConfig

```python
config: dict = {
    "hosts": [("127.0.0.1", 18710)],  # 필수
    "cluster_name": "docker",           # 클러스터 이름 검증
    "auth_mode": aerospike_py.AUTH_INTERNAL,  # 인증 모드
    "user": "admin",                    # 사용자
    "password": "admin",               # 비밀번호
    "timeout": 30000,                   # 연결 타임아웃 (ms)
    "idle_timeout": 55000,             # 유휴 연결 타임아웃 (ms)
    "max_conns_per_node": 300,         # 노드당 최대 연결 수
    "min_conns_per_node": 0,           # 노드당 최소 연결 수
    "tend_interval": 1000,             # 클러스터 상태 확인 주기 (ms)
    "use_services_alternate": False,   # alternate 서비스 주소 사용
}
```

## 반환 타입 (NamedTuple)

```python
from aerospike_py.types import Record, AerospikeKey, RecordMetadata, ExistsResult, \
    OperateOrderedResult, BinTuple, InfoNodeResult

Record(key: AerospikeKey | None, meta: RecordMetadata | None, bins: dict[str, Any] | None)
AerospikeKey(namespace: str, set_name: str, user_key: str | int | bytes | None, digest: bytes)
RecordMetadata(gen: int, ttl: int)
ExistsResult(key: AerospikeKey | None, meta: RecordMetadata | None)  # meta is None if not found
OperateOrderedResult(key: AerospikeKey | None, meta: RecordMetadata | None, ordered_bins: list[BinTuple])
BinTuple(name: str, value: Any)
InfoNodeResult(node_name: str, error_code: int, response: str)
```

## Connection

```python
client.connect(username=None, password=None) -> Client   # 메서드 체이닝
client.is_connected() -> bool
client.close() -> None
client.get_node_names() -> list[str]

# Async 동일 (await 필요, is_connected 제외)
await client.connect()
await client.close()
await client.get_node_names()
```

## CRUD

```python
key: tuple[str, str, str | int | bytes] = ("test", "demo", "user1")

# Write
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"score": 100}, meta={"ttl": 300})  # TTL 설정
client.put(key, {"x": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
client.put(key, {"x": 1}, meta={"gen": 2}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

# Read -> Record
record: Record = client.get(key)
record.bins     # {"name": "Alice", "age": 30}
record.meta.gen # generation number
record.meta.ttl # TTL in seconds

# Select -> Record (특정 bin만 읽기)
record: Record = client.select(key, ["name"])  # record.bins = {"name": "Alice"}

# Exists -> ExistsResult
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"Found, gen={result.meta.gen}")

# Delete
client.remove(key)
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

# Touch (TTL 리셋)
client.touch(key, val=300)

# String 연산
client.append(key, "name", "_suffix")
client.prepend(key, "name", "prefix_")

# Numeric 연산
client.increment(key, "counter", 1)      # int 증가
client.increment(key, "score", 0.5)      # float 증가
client.increment(key, "counter", -1)     # 감소

# Bin 삭제
client.remove_bin(key, ["temp_bin", "debug_bin"])

# Async: 모든 메서드에 await 추가
record = await client.get(key)
await client.put(key, {"name": "Alice"})
```

## Batch

```python
keys: list[tuple[str, str, str | int | bytes]] = [
    ("test", "demo", f"user_{i}") for i in range(10)
]

# batch_read -> BatchRecords (raw 튜플, NamedTuple 아님)
batch: BatchRecords = client.batch_read(keys)
for br in batch.batch_records:
    if br.result == 0 and br.record is not None:
        key_tuple, meta_dict, bins = br.record
        print(bins)

# 특정 bin만 읽기
batch = client.batch_read(keys, bins=["name", "age"])

# batch_operate -> list[Record] (NamedTuple)
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results: list[Record] = client.batch_operate(keys, ops)
for record in results:
    print(record.bins)

# batch_remove -> list[Record]
results: list[Record] = client.batch_remove(keys)

# Async: 동일하게 await
batch = await client.batch_read(keys, bins=["name", "age"])
results = await client.batch_operate(keys, ops)
results = await client.batch_remove(keys)
```

### NumPy Batch

```python
import numpy as np

# dtype 정의 (int, float, fixed-length bytes만 가능)
dtype = np.dtype([("age", "i4"), ("score", "f8"), ("name", "S32")])

# batch_read + NumPy -> NumpyBatchRecords
result: NumpyBatchRecords = client.batch_read(keys, bins=["age", "score", "name"], _dtype=dtype)

# 결과 접근
result.batch_records   # np.ndarray (structured array)
result.meta            # np.ndarray, dtype=[("gen", "u4"), ("ttl", "u4")]
result.result_codes    # np.ndarray (int32), 0 = 성공

# 단일 레코드 조회 (primary key로)
row = result.get("user_0")  # np.void (scalar record)
row["age"]   # 30
row["score"] # 95.5

# 벡터 연산
ages = result.batch_records["age"]
mean_age = ages[result.result_codes == 0].mean()
```

## Operate (Multi-op)

```python
# 단일 레코드에 대한 원자적 다중 연산
ops: list[dict[str, Any]] = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record: Record = client.operate(key, ops)

# 순서 보존 결과
result: OperateOrderedResult = client.operate_ordered(key, ops)
for bt in result.ordered_bins:
    print(f"{bt.name} = {bt.value}")
```

### List CDT

```python
from aerospike_py import list_operations as lop

client.operate(key, [
    lop.list_append("mylist", "val"),
    lop.list_get("mylist", 0),
    lop.list_size("mylist"),
])

# 주요 함수 (모두 Operation dict를 반환):
# 쓰기: list_append, list_append_items, list_insert, list_insert_items
# 읽기: list_get, list_get_range, list_get_by_value, list_get_by_index,
#        list_get_by_index_range, list_get_by_rank, list_get_by_rank_range,
#        list_get_by_value_list, list_get_by_value_range
# 삭제: list_pop, list_pop_range, list_remove, list_remove_range,
#        list_remove_by_value, list_remove_by_value_list, list_remove_by_value_range,
#        list_remove_by_index, list_remove_by_index_range,
#        list_remove_by_rank, list_remove_by_rank_range
# 수정: list_set, list_trim, list_clear, list_increment, list_sort, list_set_order
# 정보: list_size
#
# return_type: LIST_RETURN_NONE, LIST_RETURN_VALUE, LIST_RETURN_COUNT,
#              LIST_RETURN_INDEX, LIST_RETURN_RANK 등
# policy (선택): {"list_order": LIST_ORDERED, "write_flags": LIST_WRITE_ADD_UNIQUE}
```

### Map CDT

```python
from aerospike_py import map_operations as mop

client.operate(key, [
    mop.map_put("mymap", "k1", "v1"),
    mop.map_get_by_key("mymap", "k1", aerospike_py.MAP_RETURN_VALUE),
    mop.map_size("mymap"),
])

# 주요 함수:
# 쓰기: map_put, map_put_items, map_increment, map_decrement
# 읽기: map_get_by_key, map_get_by_key_range, map_get_by_key_list,
#        map_get_by_value, map_get_by_value_range, map_get_by_value_list,
#        map_get_by_index, map_get_by_index_range,
#        map_get_by_rank, map_get_by_rank_range
# 삭제: map_remove_by_key, map_remove_by_key_list, map_remove_by_key_range,
#        map_remove_by_value, map_remove_by_value_list, map_remove_by_value_range,
#        map_remove_by_index, map_remove_by_index_range,
#        map_remove_by_rank, map_remove_by_rank_range
# 기타: map_clear, map_size, map_set_order
#
# return_type: MAP_RETURN_NONE, MAP_RETURN_VALUE, MAP_RETURN_KEY,
#              MAP_RETURN_KEY_VALUE, MAP_RETURN_COUNT 등
# policy (선택): {"map_order": MAP_KEY_ORDERED, "write_flags": MAP_WRITE_FLAGS_CREATE_ONLY}
```

## Query (Sync/Async 모두 지원)

```python
from aerospike_py import predicates as p

# 인덱스 먼저 생성
client.index_integer_create("test", "demo", "age", "age_idx")

# Sync
query: Query = client.query("test", "demo")
query.select("name", "age")             # 특정 bin 선택
query.where(p.between("age", 20, 40))   # 필터 설정
records: list[Record] = query.results()  # 실행

# foreach (콜백, return False로 조기 중단)
def process(record: Record) -> bool | None:
    print(record.bins)
    return None  # continue (return False to stop)
query.foreach(process)

# Async
query: AsyncQuery = client.query("test", "demo")
query.select("name", "age")
query.where(p.between("age", 20, 40))
records: list[Record] = await query.results()
await query.foreach(process)

# Predicates:
# p.equals(bin_name, val)
# p.between(bin_name, min_val, max_val)
# p.contains(bin_name, index_type, val)  # collection index
# p.geo_within_geojson_region(bin_name, geojson)  # 미지원
# p.geo_within_radius(bin_name, lat, lng, radius)  # 미지원
# p.geo_contains_geojson_point(bin_name, geojson)  # 미지원
```

## Expression 필터

서버 사이드 필터링 (Aerospike 5.2+). 인덱스 불필요.

```python
from aerospike_py import exp

# 단순 비교
expr = exp.gt(exp.int_bin("age"), exp.int_val(21))
record = client.get(key, policy={"expressions": expr})

# 복합 조건 (AND/OR)
expr = exp.and_(
    exp.gt(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.string_bin("status"), exp.string_val("active")),
)

# 레코드 메타데이터
expr = exp.gt(exp.ttl(), exp.int_val(3600))  # TTL > 1시간
expr = exp.eq(exp.set_name(), exp.string_val("demo"))

# bin 존재 여부
expr = exp.bin_exists("optional_field")

# 정규식
expr = exp.regex_compare("^user_", 0, exp.string_bin("name"))

# 변수 바인딩
expr = exp.let_(
    exp.def_("x", exp.int_bin("a")),
    exp.gt(exp.var("x"), exp.int_val(10)),
)

# 조건 분기
expr = exp.cond(
    exp.gt(exp.int_bin("score"), exp.int_val(90)), exp.string_val("A"),
    exp.gt(exp.int_bin("score"), exp.int_val(80)), exp.string_val("B"),
    exp.string_val("C"),  # default
)

# policy에서 사용
record = client.get(key, policy={"expressions": expr})
batch = client.batch_read(keys, policy={"filter_expression": expr})
query.results(policy={"expressions": expr})
```

### Expression 빌더 함수 목록

| 카테고리 | 함수 |
|----------|------|
| 값 | `int_val`, `float_val`, `string_val`, `bool_val`, `blob_val`, `list_val`, `map_val`, `geo_val`, `nil`, `infinity`, `wildcard` |
| Bin | `int_bin`, `float_bin`, `string_bin`, `bool_bin`, `blob_bin`, `list_bin`, `map_bin`, `geo_bin`, `hll_bin`, `bin_exists`, `bin_type` |
| 비교 | `eq`, `ne`, `gt`, `ge`, `lt`, `le` |
| 논리 | `and_`, `or_`, `not_`, `xor_` |
| 메타 | `key`, `key_exists`, `set_name`, `record_size`, `last_update`, `since_update`, `void_time`, `ttl`, `is_tombstone`, `digest_modulo` |
| 수치 | `num_add`, `num_sub`, `num_mul`, `num_div`, `num_mod`, `num_pow`, `num_log`, `num_abs`, `num_floor`, `num_ceil`, `to_int`, `to_float`, `min_`, `max_` |
| 비트 | `int_and`, `int_or`, `int_xor`, `int_not`, `int_lshift`, `int_rshift`, `int_arshift`, `int_count`, `int_lscan`, `int_rscan` |
| 패턴 | `regex_compare`, `geo_compare` |
| 제어 | `cond`, `var`, `def_`, `let_` |

## Index

```python
client.index_integer_create("test", "demo", "age", "age_idx")
client.index_string_create("test", "demo", "name", "name_idx")
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
client.index_remove("test", "age_idx")

# Async
await client.index_integer_create("test", "demo", "age", "age_idx")
await client.index_remove("test", "age_idx")
```

## Admin

```python
# User 관리
client.admin_create_user("user1", "pass", ["read-write"])
client.admin_drop_user("user1")
client.admin_change_password("user1", "new_pass")
client.admin_grant_roles("user1", ["sys-admin"])
client.admin_revoke_roles("user1", ["read-write"])
client.admin_query_user_info("user1")  # -> dict (user, roles, conns_in_use)
client.admin_query_users_info()        # -> list[dict]

# Role 관리
client.admin_create_role("role1", [{"code": aerospike_py.PRIV_READ, "ns": "test", "set": ""}])
client.admin_drop_role("role1")
client.admin_grant_privileges("role1", [{"code": aerospike_py.PRIV_WRITE, "ns": "", "set": ""}])
client.admin_revoke_privileges("role1", [{"code": aerospike_py.PRIV_WRITE, "ns": "", "set": ""}])
client.admin_query_role("role1")    # -> dict (name, privileges, allowlist, read_quota, write_quota)
client.admin_query_roles()          # -> list[dict]
client.admin_set_whitelist("role1", ["10.0.0.0/8"])
client.admin_set_quotas("role1", read_quota=1000, write_quota=500)
```

## UDF (Lua only)

```python
client.udf_put("my_udf.lua")
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
client.udf_remove("my_udf")
```

## Info / Truncate

```python
results: list[InfoNodeResult] = client.info_all("namespaces")
for node_name, error_code, response in results:
    print(f"{node_name}: {response}")

response: str = client.info_random_node("build")
client.truncate("test", "demo")
client.truncate("test", "demo", nanos=1234567890)  # 특정 시점 이전 레코드만
```

## Observability

```python
# Prometheus Metrics
aerospike_py.start_metrics_server(port=9464)  # /metrics HTTP 엔드포인트
metrics_text: str = aerospike_py.get_metrics()  # Prometheus text format
aerospike_py.stop_metrics_server()

# OpenTelemetry Tracing (OTEL_* 환경변수로 설정)
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# OTEL_SERVICE_NAME=my-service
# OTEL_SDK_DISABLED=true (비활성화)
aerospike_py.init_tracing()
aerospike_py.shutdown_tracing()  # 프로세스 종료 전 호출

# Logging
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
# LOG_LEVEL_OFF=-1, LOG_LEVEL_ERROR=0, LOG_LEVEL_WARN=1,
# LOG_LEVEL_INFO=2, LOG_LEVEL_DEBUG=3, LOG_LEVEL_TRACE=4
```

## Policy 타입

```python
# ReadPolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 2,
 "expressions": expr, "replica": POLICY_REPLICA_MASTER, "read_mode_ap": POLICY_READ_MODE_AP_ONE}

# WritePolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 0,
 "durable_delete": False, "key": POLICY_KEY_DIGEST, "exists": POLICY_EXISTS_IGNORE,
 "gen": POLICY_GEN_IGNORE, "commit_level": POLICY_COMMIT_LEVEL_ALL,
 "ttl": 0, "expressions": expr}

# WriteMeta
{"gen": 1, "ttl": 300}

# BatchPolicy
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 2, "filter_expression": expr}

# QueryPolicy
{"socket_timeout": 30000, "total_timeout": 0, "max_retries": 2,
 "max_records": 1000, "records_per_second": 0, "expressions": expr}

# AdminPolicy
{"timeout": 5000}
```

## 주요 상수

```python
# Policy Exists
POLICY_EXISTS_IGNORE = 0         # 있으면 덮어쓰기, 없으면 생성 (기본)
POLICY_EXISTS_CREATE_ONLY = 4    # 있으면 에러
POLICY_EXISTS_UPDATE = 6         # 있으면 업데이트, 없으면 생성 (IGNORE와 동일)
POLICY_EXISTS_UPDATE_ONLY = 1    # 없으면 에러
POLICY_EXISTS_REPLACE = 2        # 전체 교체 (다른 bin 삭제)
POLICY_EXISTS_REPLACE_ONLY = 5   # 전체 교체, 없으면 에러

# Policy Gen
POLICY_GEN_IGNORE = 0   # generation 무시 (기본)
POLICY_GEN_EQ = 1       # meta.gen과 서버 gen이 같을 때만 쓰기
POLICY_GEN_GT = 2       # meta.gen이 서버 gen보다 클 때만 쓰기

# Policy Key
POLICY_KEY_DIGEST = 0   # digest만 저장 (기본)
POLICY_KEY_SEND = 1     # 원본 키도 서버에 저장

# Policy Replica
POLICY_REPLICA_MASTER = 0       # master 노드에서만 읽기
POLICY_REPLICA_SEQUENCE = 1     # 순차 복제본 읽기
POLICY_REPLICA_PREFER_RACK = 2  # 같은 rack 우선

# Policy Commit Level
POLICY_COMMIT_LEVEL_ALL = 0     # 모든 복제본 커밋 (기본)
POLICY_COMMIT_LEVEL_MASTER = 1  # master만 커밋

# Policy Read Mode AP
POLICY_READ_MODE_AP_ONE = 0  # 하나의 노드에서 읽기 (기본)
POLICY_READ_MODE_AP_ALL = 1  # 모든 노드에서 읽기

# TTL
TTL_NAMESPACE_DEFAULT = 0   # namespace 기본값 사용
TTL_NEVER_EXPIRE = -1       # 만료 없음
TTL_DONT_UPDATE = -2        # TTL 변경하지 않음
TTL_CLIENT_DEFAULT = -3     # 클라이언트 정책 기본값

# Operator (operate용)
OPERATOR_READ = 1       # bin 읽기
OPERATOR_WRITE = 2      # bin 쓰기
OPERATOR_INCR = 5       # 숫자 증가
OPERATOR_APPEND = 9     # 문자열 뒤에 추가
OPERATOR_PREPEND = 10   # 문자열 앞에 추가
OPERATOR_TOUCH = 11     # TTL 리셋
OPERATOR_DELETE = 12    # 레코드 삭제

# Map/List Return Type
MAP_RETURN_NONE = 0           # 반환 없음
MAP_RETURN_INDEX = 1          # 인덱스 반환
MAP_RETURN_REVERSE_INDEX = 2  # 역순 인덱스
MAP_RETURN_RANK = 3           # 랭크 반환
MAP_RETURN_REVERSE_RANK = 4   # 역순 랭크
MAP_RETURN_COUNT = 5          # 개수 반환
MAP_RETURN_KEY = 6            # 키 반환
MAP_RETURN_VALUE = 7          # 값 반환
MAP_RETURN_KEY_VALUE = 8      # 키-값 쌍 반환
MAP_RETURN_EXISTS = 9         # 존재 여부

LIST_RETURN_NONE = 0          # 반환 없음
LIST_RETURN_VALUE = 7         # 값 반환
LIST_RETURN_COUNT = 5         # 개수 반환
LIST_RETURN_INDEX = 1         # 인덱스 반환
LIST_RETURN_RANK = 3          # 랭크 반환

# Index Type
INDEX_NUMERIC, INDEX_STRING, INDEX_BLOB, INDEX_GEO2DSPHERE
INDEX_TYPE_DEFAULT, INDEX_TYPE_LIST, INDEX_TYPE_MAPKEYS, INDEX_TYPE_MAPVALUES

# Privilege
PRIV_READ, PRIV_WRITE, PRIV_READ_WRITE, PRIV_READ_WRITE_UDF
PRIV_SYS_ADMIN, PRIV_USER_ADMIN, PRIV_DATA_ADMIN
PRIV_UDF_ADMIN, PRIV_SINDEX_ADMIN, PRIV_TRUNCATE

# Auth
AUTH_INTERNAL = 0, AUTH_EXTERNAL = 1, AUTH_PKI = 2

# Serializer
SERIALIZER_NONE, SERIALIZER_PYTHON, SERIALIZER_USER

# Map Order / Write Flags
MAP_UNORDERED, MAP_KEY_ORDERED, MAP_KEY_VALUE_ORDERED
MAP_WRITE_FLAGS_DEFAULT, MAP_WRITE_FLAGS_CREATE_ONLY, MAP_WRITE_FLAGS_UPDATE_ONLY
MAP_WRITE_FLAGS_NO_FAIL, MAP_WRITE_FLAGS_PARTIAL

# List Order / Sort / Write Flags
LIST_UNORDERED, LIST_ORDERED
LIST_SORT_DEFAULT, LIST_SORT_DROP_DUPLICATES
LIST_WRITE_DEFAULT, LIST_WRITE_ADD_UNIQUE, LIST_WRITE_INSERT_BOUNDED
LIST_WRITE_NO_FAIL, LIST_WRITE_PARTIAL

# Bit / HLL Write Flags
BIT_WRITE_DEFAULT, BIT_WRITE_CREATE_ONLY, BIT_WRITE_UPDATE_ONLY
HLL_WRITE_DEFAULT, HLL_WRITE_CREATE_ONLY, HLL_WRITE_UPDATE_ONLY, HLL_WRITE_ALLOW_FOLD
```

## 예외

```python
try:
    record = client.get(key)
except aerospike_py.RecordNotFound:
    print("Not found")
except aerospike_py.AerospikeTimeoutError:
    print("Timeout")
except aerospike_py.AerospikeError as e:
    print(f"Error: {e}")

# 예외 계층:
# AerospikeError (기본)
# +-- ClientError (클라이언트 에러, 연결 안됨 등)
# +-- ClusterError (클러스터 연결 실패)
# +-- InvalidArgError (잘못된 인자)
# +-- AerospikeTimeoutError (타임아웃)
# +-- TimeoutError (deprecated alias)
# +-- RecordError (레코드 관련)
# |   +-- RecordNotFound
# |   +-- RecordExistsError
# |   +-- RecordGenerationError
# |   +-- RecordTooBig
# |   +-- BinNameError
# |   +-- BinExistsError
# |   +-- BinNotFound
# |   +-- BinTypeError
# |   +-- FilteredOut
# +-- ServerError (서버 관련)
#     +-- AerospikeIndexError (IndexError는 deprecated alias)
#     |   +-- IndexNotFound
#     |   +-- IndexFoundError
#     +-- QueryError
#     |   +-- QueryAbortedError
#     +-- AdminError
#     +-- UDFError
```
