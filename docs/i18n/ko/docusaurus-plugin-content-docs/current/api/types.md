---
title: Types
sidebar_label: Types
sidebar_position: 2
description: NamedTuple return types and TypedDict input types.
---

모든 타입은 `aerospike_py` 또는 `aerospike_py.types` 에서 import 가능.

```python
from aerospike_py import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
```

## Return Type (NamedTuple)

모든 return type 이 attribute access 와 tuple unpacking 둘 다 지원.

### `Record`

반환자: `get()`, `select()`, `operate()`, `Query.results()`

| Field | Type | 설명 |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | record key |
| `meta` | `RecordMetadata \| None` | generation 과 TTL |
| `bins` | `dict[str, Any] \| None` | bin value |

```python
record: Record = client.get(key)
print(record.bins)         # attribute access
_, meta, bins = record     # tuple unpacking
```

### `RecordMetadata`

| Field | Type | 설명 |
|-------|------|-------------|
| `gen` | `int` | generation (optimistic lock 버전) |
| `ttl` | `int` | time-to-live (초) |

### `AerospikeKey`

| Field | Type | 설명 |
|-------|------|-------------|
| `namespace` | `str` | namespace |
| `set_name` | `str` | set 이름 |
| `user_key` | `str \| int \| bytes \| None` | primary key (`POLICY_KEY_DIGEST` 시 `None`) |
| `digest` | `bytes` | 20-byte RIPEMD-160 digest |

### `BatchRecord`

반환자: batch operation (`BatchWriteResult.batch_records` 내부)

| Field | Type | 설명 |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | record key |
| `result` | `int` | per-record result code (0 = success) |
| `record` | `Record \| None` | record 데이터 (operation 실패 시 `None`) |
| `in_doubt` | `bool` | transient error 에도 불구하고 write 가 완료되었을 수 있는지 (default `False`) |

```python
results = client.batch_operate(keys, ops)
for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)
```

### `BatchWriteResult`

반환자: `batch_write()`, `batch_operate()`, `batch_remove()`, `batch_write_numpy()` (sync **와** async). Sync 와 async `batch_read()` 는 [`LazyBatchRecords`](#lazybatchrecords) 반환.

| Field | Type | 설명 |
|-------|------|-------------|
| `batch_records` | `list[BatchRecord]` | per-record 결과 |

### `BatchRecords`

`TypeAlias = dict[UserKey, AerospikeRecord]`. import 호환성을 위해 유지되는 historical alias. PR-374 가 `batch_read()` 를 [`LazyBatchRecords`](#lazybatchrecords) 로 전환; 동일 dict shape 가 필요하면 그 handle 에 `.to_dict()` 호출. 현재 어떤 method 도 이 alias 를 반환하지 않음.

### `LazyBatchRecords`

반환자: sync **와** async `batch_read()` — raw Rust 결과의 zero-conversion wrapper. Materialisation 은 명시 method 호출 (또는 lazy + cached `to_dict()` 를 proxy 하는 dict-like Mapping dunder) 까지 지연됨.

| Method / Property | Type | 설명 |
|-------------------|------|-------------|
| `to_dict()` | `dict[UserKey, dict[str, Any]]` | `dict[user_key, bins_dict]` 로 materialise. digest-only 와 failed record 제외. |
| `to_numpy(dtype)` | `NumpyBatchRecords` | structured array 로 materialise. `dtype` **은 `np.dtype` object 여야 함** (예: `np.dtype([("age","<i4"),("height","<f4"),("name","S10")])`). structured dtype 의 각 field name 이 동명 bin 으로 매핑; list-of-tuples shorthand 와 single-field string 은 auto-promote 안 됨 — 먼저 `np.dtype(...)` 로 wrap. per-record fill loop 가 GIL 해제 (`py.detach`) 상태로 실행되어 sibling 작업 (torch inference, 다른 asyncio task) 이 buffer fill 중 GIL 보유 가능. **실패/missing read (`result_code != 0`) 는 row 가 dtype zero value 로 남음 — downstream math 전에 항상 `result_codes` 로 mask.** |
| `batch_records` | `list[BatchRecord]` | 호환 path: lazy NamedTuple 변환. |
| `found_count()` | `int` | 성공 record 수 (변환 불필요). |
| `keys()` | `dict_keys` | dict-style key view, `to_dict().keys()` 와 mirror (missing/failed record 제외). |
| `all_user_keys()` | `list[UserKey \| None]` | 모든 batch record 의 `user_key` 를 request 순서로 — `batch_records` 와 `NumpyBatchRecords` data array 와 positional align. digest-only request (`user_key` element 없음) 는 slot 에 `None` yield, 그래서 `zip(handle.all_user_keys(), handle.batch_records)` 가 항상 모든 record 를 requested key 와 pair. |
| `iter_records()` | `Iterator[BatchRecord]` | 모든 record (digest-only 와 failed 포함) 를 삽입 순서로 순회. |
| `items()` / `values()` / `__iter__` | dict views | dict-like backward-compat — cached `to_dict()` 와 동일 의미. |
| `lazy_records[user_key]` | `dict[str, Any]` | dict-style item 접근 (`__getitem__`). |
| `user_key in lazy_records` | `bool` | dict-style membership (`__contains__`). |
| `lazy_records.get(user_key, default=None)` | `dict[str, Any] \| Any` | dict-style `get`, 선택적 default; `dict.get` 의미 mirror. |
| `len(lazy_records)` | `int` | dict-view cardinality — `len(lazy_records.to_dict())` 와 매칭 (성공한 read, `user_key` 와 `record` body 보유). 빠름: pure-Rust filter+count, PyDict 할당 없음. raw record 수 (missing read / per-record failure 포함) 는 `len(lazy_records.batch_records)`. |
| `release_cache()` | `None` | 첫 Mapping 접근 / `to_dict()` 가 빌드한 cached `PyDict` 를 drop, raw Rust record 는 유지 (그래서 `batch_records`, `iter_records()`, `all_user_keys()`, `found_count()`, `to_numpy(dtype)` 가 계속 동작). 이후 Mapping 접근이 cache 를 lazy 하게 rebuild. 더 이상 필요 없는 대형 batch materialisation 후 유용. |

### `ExistsResult`

반환자: `exists()`

| Field | Type | 설명 |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | record key |
| `meta` | `RecordMetadata \| None` | record 없으면 `None` |

```python
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

### `InfoNodeResult`

반환자: `info_all()`

| Field | Type | 설명 |
|-------|------|-------------|
| `node_name` | `str` | cluster node 이름 |
| `error_code` | `int` | 성공 시 0 |
| `response` | `str` | info response string |

### `OperateOrderedResult`

반환자: `operate_ordered()`

| Field | Type | 설명 |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | record key |
| `meta` | `RecordMetadata \| None` | record metadata |
| `ordered_bins` | `list[BinTuple]` | 순서 보존된 operation 결과 |

### `BinTuple`

| Field | Type | 설명 |
|-------|------|-------------|
| `name` | `str` | bin 이름 |
| `value` | `Any` | bin value |

### Return Type 빠른 참조

| Method | Return Type |
|--------|-------------|
| `get()`, `select()` | `Record` |
| `exists()` | `ExistsResult` |
| `operate()` | `Record` |
| `operate_ordered()` | `OperateOrderedResult` |
| `info_all()` | `list[InfoNodeResult]` |
| `batch_read()` (sync 와 async) | `LazyBatchRecords` — `.to_dict()` 또는 `.to_numpy(dtype)` 로 materialise |
| `batch_write()`, `batch_operate()`, `batch_remove()` | `BatchWriteResult` (`batch_records: list[BatchRecord]`) |
| `batch_write_numpy()` | `BatchWriteResult` |
| `Query.results()` | `list[Record]` |

---

## Input Type (TypedDict)

모든 field 는 선택적 (`total=False`).

### `ClientConfig`

사용자: `aerospike_py.client(config)`, `AsyncClient(config)`

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | seed node |
| `cluster_name` | `str \| None` | | 예상 cluster name. `None` 은 field 생략과 동일 처리. |
| `auth_mode` | `int` | `AUTH_INTERNAL` | `AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI` |
| `user` | `str` | | auth username |
| `password` | `str` | | auth password |
| `timeout` | `int` | `1000` | connection timeout (ms) |
| `idle_timeout` | `int` | | connection idle timeout (ms) |
| `max_conns_per_node` | `int` | `100` | node 당 최대 connection |
| `min_conns_per_node` | `int` | `0` | pre-warm connection |
| `tend_interval` | `int` | `1000` | cluster tend interval (ms) |
| `use_services_alternate` | `bool` | `false` | alternate service address 사용 |

### `ReadPolicy`

사용자: `get()`, `select()`, `exists()`

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket timeout (ms) |
| `total_timeout` | `int` | `1000` | 총 transaction timeout (ms) |
| `max_retries` | `int` | `2` | 최대 retry |
| `sleep_between_retries` | `int` | `0` | retry 간 sleep (ms) |
| `timeout_delay` | `int` | `0` | deadline 이후 request timeout 까지의 delay (ms). 재사용 connection 이 stale response 를 보지 않도록 socket drain. |
| `filter_expression` | `Any` | | `aerospike_py.exp` 로 빌드된 expression filter. |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | replica 선택 알고리즘. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP namespace read consistency. `aerospike-core` `ConsistencyLevel` 로 매핑. |
| `read_touch_ttl_percent` | `int` | `0` | original write TTL 의 N% 이내일 때 read 시 TTL reset (server v8+). `0` = server default, `-1` = reset 안 함, `1..=100` = percent. |

### `WritePolicy`

사용자: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket timeout (ms) |
| `total_timeout` | `int` | `1000` | 총 transaction timeout (ms) |
| `max_retries` | `int` | `0` | 최대 retry |
| `sleep_between_retries` | `int` | `0` | retry 간 sleep (ms) |
| `timeout_delay` | `int` | `0` | deadline 이후 request timeout 까지의 delay (ms). |
| `durable_delete` | `bool` | `false` | durable delete (Enterprise) |
| `key` | `int` | `POLICY_KEY_DIGEST` | key send policy |
| `exists` | `int` | `POLICY_EXISTS_IGNORE` | existence policy |
| `gen` | `int` | `POLICY_GEN_IGNORE` | generation policy |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | commit level |
| `ttl` | `int` | `0` | record TTL (초) |
| `filter_expression` | `Any` | | expression filter (`aerospike_py.exp`). |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | read-after-write `operate()` op 의 AP read consistency. |
| `read_touch_ttl_percent` | `int` | `0` | write TTL 의 N% 이내 read 시 TTL reset (server v8+). |

### `BatchPolicy`

사용자: `batch_read()`, `batch_operate()`, `batch_write()`, `batch_remove()`

#### Transport / batch-level field

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket timeout (ms) |
| `total_timeout` | `int` | `1000` | 총 transaction timeout (ms) |
| `max_retries` | `int` | `2` | 최대 retry |
| `sleep_between_retries` | `int` | `0` | retry 간 sleep (ms) |
| `timeout_delay` | `int` | `0` | deadline 이후 request timeout 까지의 delay (ms). |
| `concurrency` | `int` | `BATCH_CONCURRENCY_PARALLEL` | per-node dispatch mode: `BATCH_CONCURRENCY_SEQUENTIAL` (한 번에 한 node) 또는 `BATCH_CONCURRENCY_PARALLEL` (모든 node 병렬 — default). [Batch Concurrency constants](constants.md#batch-concurrency) 참조. 다른 값은 `ValueError`. |
| `filter_expression` | `Any` | | expression filter |
| `allow_inline` | `bool` | `true` | 수신 thread 에서 server inline 처리 허용 |
| `allow_inline_ssd` | `bool` | `false` | SSD namespace 의 inline 처리 허용 |
| `respond_all_keys` | `bool` | `true` | per-record error 와 관계없이 모든 key 시도 |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | replica 선택. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | `batch_read` 의 AP read consistency. |
| `read_touch_ttl_percent` | `int` | `0` | write TTL 의 N% 이내 read 시 TTL reset (server v8+). |

#### Write default (`batch_write` 가 사용)

이 field 들은 `batch_write()` 호출의 모든 record 에 적용. Per-record [`WriteMeta`](#writemeta) 가 override — [precedence rule](#write-field-precedence-batch_write) 참조.

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `key` | `int` | `POLICY_KEY_DIGEST` | key send policy. server-side 에 user key 저장하려면 `POLICY_KEY_SEND`. |
| `exists` | `int` | `POLICY_EXISTS_UPDATE` | existence policy (`UPDATE`, `CREATE_ONLY`, `REPLACE` 등). |
| `gen` | `int` | `POLICY_GEN_IGNORE` | generation policy. 참고: batch-level 에선 `POLICY_GEN_*` enum index. Per-record `WriteMeta["gen"]` 은 예상 generation 값. |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | commit level (`ALL` 또는 `MASTER`). |
| `durable_delete` | `bool` | `false` | durable delete (Enterprise 3.10+). |
| `ttl` | `int` | `0` | record TTL (초) (`0` = namespace default, `-1` = 영원, `-2` = update 안 함). |

### `QueryPolicy`

사용자: `Query.results()`, `Query.foreach()`

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket timeout (ms) |
| `total_timeout` | `int` | `0` | 총 timeout (0 = 무제한) |
| `max_retries` | `int` | `2` | 최대 retry |
| `sleep_between_retries` | `int` | `0` | retry 간 sleep (ms) |
| `timeout_delay` | `int` | `0` | deadline 이후 request timeout 까지의 delay (ms). |
| `max_records` | `int` | `0` | 최대 record (0 = 전체) |
| `records_per_second` | `int` | `0` | node 당 rate limit (0 = 무제한). |
| `max_concurrent_nodes` | `int` | `0` | 병렬 node query 제한 (0 = 무제한). |
| `record_queue_size` | `int` | `1024` | record 결과의 buffer capacity. |
| `filter_expression` | `Any` | | expression filter. |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | replica 선택. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency. |
| `read_touch_ttl_percent` | `int` | `0` | write TTL 의 N% 이내 read 시 TTL reset (server v8+). |
| `expected_duration` | `int` | `QUERY_DURATION_LONG` | query duration 에 대한 server hint (`QUERY_DURATION_LONG` / `_SHORT` / `_LONG_RELAX_AP`). |
| `include_bin_data` | `bool` | `true` | 결과에 bin payload 포함. key/metadata 만 fetch 하려면 `False`. |
| `partition_filter` | `PartitionFilter` | (전체 4096) | query/scan 을 partition subset 으로 제한. `aerospike_py.partition_filter_*()` helper 사용. |

### `ScanPolicy`

사용자: `where()` predicate 없는 `client.scan()` 과 `client.query()` 호출. 공식 Python C client 의 `ScanPolicy` mirror. 현재 Rust layer 가 scan 호출을 `QueryPolicy` parser 로 routing — `aerospike-core` 가 별도 `ScanPolicy` struct 를 노출하면 user-facing type 변경 없이 scan path 가 전용 parser 로 전환. [issue #316](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/316) 참조.

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket timeout (ms). |
| `total_timeout` | `int` | `0` | 총 timeout (0 = 무제한). |
| `max_retries` | `int` | `2` | 최대 retry. |
| `sleep_between_retries` | `int` | `0` | retry 간 sleep (ms). |
| `timeout_delay` | `int` | `0` | deadline 이후 request timeout 까지의 delay (ms). |
| `filter_expression` | `Any` | | expression filter. |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | replica 선택. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency. |
| `records_per_second` | `int` | `0` | node 당 rate limit (0 = 무제한; server 4.7+). |
| `max_records` | `int` | `0` | 대략적 최대 반환 record (0 = 전체; server 6.0+). |
| `durable_delete` | `bool` | `false` | background scan-write durable delete (Enterprise 3.10+). |
| `ttl` | `int` | `0` | background scan-write 의 default TTL. |
| `partition_filter` | `PartitionFilter` | (전체 4096) | scan 을 partition subset 으로 제한. |

### `BatchReadPolicy`

사용자: `batch_read()` 의 per-record policy.

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `read_touch_ttl_percent` | `int` | `0` | write TTL 의 N% 이내 read 시 TTL reset (server v8+). `0` = server default, `-1` = reset 안 함, `1..=100` = percent. |
| `filter_expression` | `Any` | | expression filter. 실패한 record 는 `BatchRecord.result == FILTERED_OUT` 반환. |

### `BatchDeletePolicy`

사용자: `batch_remove()` 의 batch-level policy. Per-record override 는 [`BatchDeleteMeta`](#batchdeletemeta).

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `gen` | `int` | `POLICY_GEN_IGNORE` | generation policy enum (`POLICY_GEN_*`). |
| `key` | `int` | `POLICY_KEY_DIGEST` | delete 와 함께 user key send (XDR-friendly). |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | commit level. |
| `durable_delete` | `bool` | `false` | tombstone 남기기 (Enterprise 3.10+). |
| `filter_expression` | `Any` | | expression filter. |

### `BatchDeleteMeta`

`batch_remove()` 의 per-record meta. `keys` 인자의 `(key, meta)` tuple 두 번째 element 로 전달. `gen` 설정 시 CAS-style "generation 일치 시에만 delete" 의미 활성화 — generation 이 advance 했으면 server 가 per-record `GENERATION_ERROR` 반환.

| Field | Type | 설명 |
|-------|------|-------------|
| `gen` | `int` | 예상 generation. 이 설정 시 `POLICY_GEN_EQ` 가 함의됨. |
| `key` | `int` | key send policy (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `commit_level` | `int` | commit level (`POLICY_COMMIT_LEVEL_ALL` / `_MASTER`). |
| `durable_delete` | `bool` | durable delete (Enterprise 3.10+). |

```python
# CAS delete: generation 이 여전히 3 일 때만 user_1 delete.
client.batch_remove([
    (("test", "demo", "user_1"), {"gen": 3}),
    ("test", "demo", "user_2"),  # bare key, CAS 없음
])
```

### `BatchUDFPolicy`

사용자: [`batch_apply()`](client.md#batch_applykeys-module-function-argsnone-policynone) 의 batch-level UDF policy. Per-record override 는 [`BatchUDFMeta`](#batchudfmeta). Transport-level option (timeout, retry, `concurrency` 등) 은 [`BatchPolicy`](#batchpolicy) 에 있으며 `batch_apply()` 에 전달하는 같은 policy dict 로 merge.

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | commit level (`POLICY_COMMIT_LEVEL_ALL` / `_MASTER`). |
| `ttl` | `int` | `0` | record TTL (초) (`0` = namespace default, `-1` = 영원, `-2` = update 안 함). |
| `key` | `int` | `POLICY_KEY_DIGEST` | key send policy (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `durable_delete` | `bool` | `false` | record delete UDF 의 durable delete (Enterprise 3.10+). |
| `filter_expression` | `Any` | | 각 record 에 적용되는 expression filter. 필터 실패한 record 는 `BatchRecord.result == FILTERED_OUT` 반환. |

### `BatchUDFMeta`

`batch_apply()` 의 per-record meta. `keys` 인자의 `(key, meta)` tuple 두 번째 element 로 전달. 특정 record 에 대해 UDF 호출 shape 와 policy field 둘 다 override 가능한 single flat dict ([`BatchDeleteMeta`](#batchdeletemeta) 매칭).

| Field | Type | 설명 |
|-------|------|-------------|
| `module` | `str` | 이 record 의 UDF module 이름 override. `batch_apply()` 의 `module` 인자가 fallback. |
| `function` | `str` | 이 record 의 UDF function 이름 override. |
| `args` | `list[Any]` | 인자 list override. `[]` 명시 전달 시 default args clear. |
| `ttl` | `int` | 이 record 의 TTL (초) override (`WriteMeta.ttl` 과 동일 의미). |
| `commit_level` | `int` | commit level override. |
| `key` | `int` | key send policy override (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `durable_delete` | `bool` | durable_delete override. |

:::note
`filter_expression` 은 `BatchUDFMeta` 에 **허용되지 않음** — batch-level [`BatchUDFPolicy`](#batchudfpolicy) 에 설정. (Per-record `filter_expression` 은 aerospike-core 2.0 에서 unwired; [`BatchDeleteMeta`](#batchdeletemeta) shape 와 매칭.)
:::

```python
# 다수 key 에 같은 UDF apply.
keys = [("test", "demo", f"u_{i}") for i in range(10)]
results = client.batch_apply(keys, "my_udf", "increment_counter", [1])

# Per-record override: 한 record 에 다른 args / 더 긴 TTL.
results = client.batch_apply(
    [
        ("test", "demo", "u_1"),  # default args 사용
        (("test", "demo", "u_2"), {"args": [5], "ttl": 3600}),
    ],
    "my_udf", "increment_counter", args=[1],
)
```

### `PartitionFilter`

query/scan 을 partition subset 으로 scoping 하는 opaque handle (server 6.0+). 모듈 레벨 helper 로 생성:

```python
import aerospike_py

pf_all   = aerospike_py.partition_filter_all()
pf_one   = aerospike_py.partition_filter_by_id(42)        # 단일 partition (0..4095)
pf_range = aerospike_py.partition_filter_by_range(0, 1024) # partition 의 1/4
records = client.query("test", "demo").results(policy={"partition_filter": pf_range})
```

handle 은 mutable internal state (`Arc<Mutex<Vec<PartitionStatus>>>`) 보유. aerospike-py 가 parse 시 내부 filter 를 clone 해 user handle 이 in-flight query state mutation 으로부터 격리됨. 이전 run 이 멈춘 곳부터 scan 을 의도적으로 resume 하려면 같은 handle 을 여러 `results()` 호출에 전달 — v2 cursor 의미는 [issue #318](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/318) 참조.

### `AdminPolicy`

사용자: 모든 `admin_*` method, index operation, `truncate()`

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `timeout` | `int` | `1000` | timeout (ms) |

### `WriteMeta`

사용자: `put()`, `remove()`, `touch()`, `operate()` 의 `meta` 파라미터, **그리고 `batch_write()` 에서 per-record** 로 third tuple element `(key, bins, meta)`.

`batch_write()` 에서 per-record `WriteMeta` 에 설정된 field 는 대응하는 batch-level [`BatchPolicy`](#batchpolicy) default 를 override — [precedence rule](#write-field-precedence-batch_write) 참조.

| Field | Type | 설명 |
|-------|------|-------------|
| `gen` | `int` | 예상 generation. 이 설정 시 `POLICY_GEN_EQ` 함의 (CAS-style write). |
| `ttl` | `int` | record TTL (초). 특수 값: `0` = namespace default, `-1` = 영원, `-2` = update 안 함. |
| `key` | `int` | key send policy (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `exists` | `int` | existence policy (`POLICY_EXISTS_*`). |
| `commit_level` | `int` | commit level (`POLICY_COMMIT_LEVEL_ALL` / `_MASTER`). |
| `durable_delete` | `bool` | durable delete (Enterprise 3.10+). |

#### Write field 우선순위 (batch_write) {#write-field-precedence-batch_write}

모든 write field 에 대해 **per-record `WriteMeta` 가 항상 batch-level `BatchPolicy` 보다 우위**:

| Field            | `BatchPolicy` (batch-level) | `WriteMeta` (per-record) | 비고 |
|------------------|-----------------------------|--------------------------|-------|
| `ttl`            | ✅                          | ✅                       | 양쪽 의미 동일. |
| `key`            | ✅                          | ✅                       | server-side 에 user key 저장하려면 `POLICY_KEY_SEND`. |
| `exists`         | ✅                          | ✅                       | 예: upsert-fail-on-exists 를 위한 `POLICY_EXISTS_CREATE_ONLY`. |
| `gen`            | ✅ (enum index)             | ✅ (예상 값)             | 비대칭: batch-level = `POLICY_GEN_*` enum index; per-record = `POLICY_GEN_EQ` 를 강제하는 numeric generation. |
| `commit_level`   | ✅                          | ✅                       | |
| `durable_delete` | ✅                          | ✅                       | |

### `Privilege`

사용자: `admin_create_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`

| Field | Type | 설명 |
|-------|------|-------------|
| `code` | `int \| str` | privilege code constant (`PRIV_READ`, `PRIV_WRITE` 등) 또는 canonical name (`"read"`, `"read-write"` 등) |
| `ns` | `str` | namespace scope (빈 문자 = global) |
| `set` | `str` | set scope (빈 문자 = namespace-wide) |

### `UserInfo`

반환자: `admin_query_user_info()`, `admin_query_users_info()`

| Field | Type | 설명 |
|-------|------|-------------|
| `user` | `str` | username |
| `roles` | `list[str]` | 할당된 role |
| `conns_in_use` | `int` | 활성 connection |

### `RoleInfo`

반환자: `admin_query_role()`, `admin_query_roles()`

| Field | Type | 설명 |
|-------|------|-------------|
| `name` | `str` | role 이름 |
| `privileges` | `list[Privilege]` | 할당된 privilege |
| `allowlist` | `list[str]` | IP allowlist |
| `read_quota` | `int` | read quota |
| `write_quota` | `int` | write quota |
