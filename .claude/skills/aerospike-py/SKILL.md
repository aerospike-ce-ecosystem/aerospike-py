---
name: aerospike-py
description: aerospike-py Python API usage guide for code generation
user-invocable: false
---

# aerospike-py API Quick Reference

Aerospike Python client (Rust/PyO3). Sync/Async API 제공. 기본 포트 18710.
전체 상수/타입 정의는 `src/aerospike_py/__init__.pyi` 참조.

## Client

```python
import aerospike_py

# Sync - 메서드 체이닝
client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()
with aerospike_py.client(config).connect() as client: ...

# Async
client = aerospike_py.AsyncClient({"hosts": [("127.0.0.1", 18710)]})
await client.connect()
async with aerospike_py.AsyncClient(config) as client: ...
```

## 반환 타입 (NamedTuple)

```python
Record(key: AerospikeKey | None, meta: RecordMetadata | None, bins: Bins | None)
AerospikeKey(namespace, set_name, user_key, digest)
RecordMetadata(gen, ttl)
ExistsResult(key, meta)  # meta is None if not found
OperateOrderedResult(key, meta, ordered_bins: list[BinTuple])
BinTuple(name, value)
InfoNodeResult(node_name, error_code, response)
```

## CRUD

```python
key = ("test", "demo", "user1")

# Write
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"score": 100}, meta={"ttl": 300})  # with TTL
client.put(key, {"x": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})

# Read -> Record
record = client.get(key)  # record.bins, record.meta.gen, record.meta.ttl
record = client.select(key, ["name"])  # specific bins only

# Exists -> ExistsResult
result = client.exists(key)  # result.meta is None if not found

# Delete
client.remove(key)
client.touch(key, val=300)  # reset TTL

# String/Numeric
client.append(key, "name", "_suffix")
client.prepend(key, "name", "prefix_")
client.increment(key, "counter", 1)  # negative to decrement
client.remove_bin(key, ["temp_bin"])

# Async: 모든 메서드에 await 추가
record = await client.get(key)
await client.put(key, {"name": "Alice"})
```

## Batch

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

batch = client.batch_read(keys, bins=["name", "age"])  # -> BatchRecords
results = client.batch_operate(keys, ops)  # -> list[Record]
results = client.batch_remove(keys)  # -> list[Record]

# NumPy batch
import numpy as np
dtype = np.dtype([("age", "i4"), ("score", "f8")])
result = client.batch_read(keys, bins=["age", "score"], _dtype=dtype)
```

## Operate (Multi-op)

```python
ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record = client.operate(key, ops)  # -> Record
result = client.operate_ordered(key, ops)  # -> OperateOrderedResult (순서 보존)
```

### List CDT

```python
from aerospike_py import list_operations as lop

client.operate(key, [
    lop.list_append("mylist", "val"),
    lop.list_get(("mylist", 0),
    lop.list_size("mylist"),
])
# 주요: list_append, list_insert, list_pop, list_remove, list_get, list_get_range,
# list_get_by_value, list_get_by_index, list_get_by_rank, list_set, list_trim,
# list_clear, list_size, list_increment, list_sort, list_set_order
```

### Map CDT

```python
from aerospike_py import map_operations as mop

client.operate(key, [
    mop.map_put("mymap", "k1", "v1"),
    mop.map_get_by_key("mymap", "k1", aerospike_py.MAP_RETURN_VALUE),
    mop.map_size("mymap"),
])
# 주요: map_put, map_put_items, map_increment, map_decrement, map_clear,
# map_remove_by_key, map_get_by_key, map_get_by_value, map_get_by_index,
# map_get_by_rank, map_size, map_set_order
```

## Query (Sync Client 전용)

```python
from aerospike_py import predicates as p

# 인덱스 먼저 생성
client.index_integer_create("test", "demo", "age", "age_idx")

query = client.query("test", "demo")
query.select("name", "age")
query.where(p.between("age", 20, 40))
records = query.results()  # -> list[Record]
query.foreach(callback)    # callback(record) -> return False to stop

# Predicates: equals, between, contains, geo_within_geojson_region,
# geo_within_radius, geo_contains_geojson_point
```

## Expression 필터

```python
from aerospike_py import exp

expr = exp.gt(exp.int_bin("age"), exp.int_val(21))
record = client.get(key, policy={"expressions": expr})

# 복합 조건
expr = exp.and_(
    exp.gt(exp.int_bin("age"), exp.int_val(18)),
    exp.eq(exp.string_bin("status"), exp.string_val("active")),
)
# 값: int_val, float_val, string_val, bool_val, blob_val, list_val, map_val
# Bin: int_bin, float_bin, string_bin, list_bin, map_bin, bin_exists
# 비교: eq, ne, gt, ge, lt, le | 논리: and_, or_, not_, xor_
# 메타: ttl, last_update, void_time, record_size, set_name, digest_modulo
```

## Index

```python
client.index_integer_create("test", "demo", "age", "age_idx")
client.index_string_create("test", "demo", "name", "name_idx")
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
client.index_remove("test", "age_idx")
```

## Admin

```python
# User
client.admin_create_user("user1", "pass", ["read-write"])
client.admin_drop_user("user1")
client.admin_change_password("user1", "new_pass")
client.admin_grant_roles("user1", ["sys-admin"])
client.admin_revoke_roles("user1", ["read-write"])
client.admin_query_user_info("user1")  # -> dict
client.admin_query_users_info()  # -> list[dict]

# Role
client.admin_create_role("role1", [{"code": aerospike_py.PRIV_READ, "ns": "test", "set": ""}])
client.admin_drop_role("role1")
client.admin_grant_privileges("role1", privileges)
client.admin_revoke_privileges("role1", privileges)
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
results = client.info_all("namespaces")  # -> list[InfoNodeResult]
response = client.info_random_node("build")  # -> str
client.truncate("test", "demo")
```

## Observability

```python
aerospike_py.start_metrics_server(port=9464)  # Prometheus /metrics
aerospike_py.get_metrics()  # Prometheus text format
aerospike_py.stop_metrics_server()

aerospike_py.init_tracing()     # OTel (OTEL_* env vars)
aerospike_py.shutdown_tracing()

aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)  # -1~4
```

## 주요 상수

```python
# Policy Exists
POLICY_EXISTS_IGNORE=0, POLICY_EXISTS_CREATE_ONLY=4, POLICY_EXISTS_UPDATE_ONLY=1, POLICY_EXISTS_REPLACE=2
# Policy Gen
POLICY_GEN_IGNORE=0, POLICY_GEN_EQ=1, POLICY_GEN_GT=2
# Policy Key
POLICY_KEY_DIGEST=0, POLICY_KEY_SEND=1

# TTL
TTL_NAMESPACE_DEFAULT=0, TTL_NEVER_EXPIRE=-1, TTL_DONT_UPDATE=-2

# Operator (operate용)
OPERATOR_READ=1, OPERATOR_WRITE=2, OPERATOR_INCR=5, OPERATOR_APPEND=9, OPERATOR_PREPEND=10, OPERATOR_TOUCH=11, OPERATOR_DELETE=12

# Map/List Return
MAP_RETURN_NONE=0, MAP_RETURN_VALUE=7, MAP_RETURN_KEY_VALUE=8, MAP_RETURN_COUNT=5
LIST_RETURN_NONE=0, LIST_RETURN_VALUE=7, LIST_RETURN_COUNT=5

# Index
INDEX_NUMERIC, INDEX_STRING, INDEX_GEO2DSPHERE
INDEX_TYPE_DEFAULT, INDEX_TYPE_LIST, INDEX_TYPE_MAPKEYS, INDEX_TYPE_MAPVALUES

# Privilege
PRIV_READ=10, PRIV_WRITE=13, PRIV_READ_WRITE=11, PRIV_SYS_ADMIN=1, PRIV_DATA_ADMIN=2

# Auth
AUTH_INTERNAL=0, AUTH_EXTERNAL=1, AUTH_PKI=2

# Log Level
LOG_LEVEL_OFF=-1, LOG_LEVEL_ERROR=0, LOG_LEVEL_WARN=1, LOG_LEVEL_INFO=2, LOG_LEVEL_DEBUG=3, LOG_LEVEL_TRACE=4
```

## 예외

```python
try:
    record = client.get(key)
except aerospike_py.RecordNotFound: ...
except aerospike_py.AerospikeTimeoutError: ...
except aerospike_py.AerospikeError: ...
# 계층: AerospikeError > {ClientError, ClusterError, InvalidArgError,
# AerospikeTimeoutError, RecordError > {RecordNotFound, RecordExistsError, ...},
# ServerError > {AerospikeIndexError, QueryError, AdminError, UDFError}}
```
