---
title: Types
sidebar_label: Types
sidebar_position: 2
description: NamedTuple return types and TypedDict input types.
---

All types are importable from `aerospike_py` or `aerospike_py.types`.

```python
from aerospike_py import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
```

## Return Types (NamedTuple)

All return types support both attribute access and tuple unpacking.

### `Record`

Returned by: `get()`, `select()`, `operate()`, `Query.results()`

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `meta` | `RecordMetadata \| None` | Generation and TTL |
| `bins` | `dict[str, Any] \| None` | Bin values |

```python
record: Record = client.get(key)
print(record.bins)         # attribute access
_, meta, bins = record     # tuple unpacking
```

### `RecordMetadata`

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Generation (optimistic lock version) |
| `ttl` | `int` | Time-to-live in seconds |

### `AerospikeKey`

| Field | Type | Description |
|-------|------|-------------|
| `namespace` | `str` | Namespace |
| `set_name` | `str` | Set name |
| `user_key` | `str \| int \| bytes \| None` | Primary key (`None` if `POLICY_KEY_DIGEST`) |
| `digest` | `bytes` | 20-byte RIPEMD-160 digest |

### `BatchRecord`

Returned by: batch operations (inside `BatchRecords.batch_records`)

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `result` | `int` | Per-record result code (0 = success) |
| `record` | `Record \| None` | Record data (`None` if operation failed) |
| `in_doubt` | `bool` | Whether the write may have completed despite a transient error (default `False`) |

```python
results = client.batch_operate(keys, ops)
for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)
```

### `BatchRecords`

Returned by: sync `batch_read()`, `batch_write()`, `batch_operate()`, `batch_remove()`, `batch_write_numpy()`

| Field | Type | Description |
|-------|------|-------------|
| `batch_records` | `list[BatchRecord]` | Per-record results |

### `BatchReadHandle`

Returned by: async `batch_read()` (zero-conversion handle wrapping raw Rust results)

| Method / Property | Type | Description |
|-------------------|------|-------------|
| `as_dict()` | `dict[str \| int, dict[str, Any]]` | Fastest path: returns `dict[key, bins_dict]` directly. Excludes digest-only and failed records. |
| `batch_records` | `list[BatchRecord]` | Compat path: lazy NamedTuple conversion, cached after first access. |
| `found_count()` | `int` | Count of successful records (no conversion needed). |
| `keys()` | `list[str \| int]` | Extract user keys without converting record data. |
| `len(handle)` | `int` | Total number of records (including failures). |
| `handle[i]` | `BatchRecord` | Index access with negative index support. |
| `for br in handle` | `BatchRecord` | Iteration (via `batch_records`). |

### `ExistsResult`

Returned by: `exists()`

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `meta` | `RecordMetadata \| None` | `None` if record does not exist |

```python
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

### `InfoNodeResult`

Returned by: `info_all()`

| Field | Type | Description |
|-------|------|-------------|
| `node_name` | `str` | Cluster node name |
| `error_code` | `int` | 0 on success |
| `response` | `str` | Info response string |

### `OperateOrderedResult`

Returned by: `operate_ordered()`

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `meta` | `RecordMetadata \| None` | Record metadata |
| `ordered_bins` | `list[BinTuple]` | Ordered operation results |

### `BinTuple`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Bin name |
| `value` | `Any` | Bin value |

### Return Type Quick Reference

| Method | Return Type |
|--------|-------------|
| `get()`, `select()` | `Record` |
| `exists()` | `ExistsResult` |
| `operate()` | `Record` |
| `operate_ordered()` | `OperateOrderedResult` |
| `info_all()` | `list[InfoNodeResult]` |
| `batch_read()` (sync) | `BatchRecords` \| `NumpyBatchRecords` |
| `batch_read()` (async) | `BatchReadHandle` \| `NumpyBatchRecords` |
| `batch_write()`, `batch_operate()`, `batch_remove()` | `BatchRecords` |
| `batch_write_numpy()` | `BatchRecords` |
| `Query.results()` | `list[Record]` |

---

## Input Types (TypedDict)

All fields are optional (`total=False`).

### `ClientConfig`

Used by: `aerospike_py.client(config)`, `AsyncClient(config)`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | Seed nodes |
| `cluster_name` | `str` | | Expected cluster name |
| `auth_mode` | `int` | `AUTH_INTERNAL` | `AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI` |
| `user` | `str` | | Authentication username |
| `password` | `str` | | Authentication password |
| `timeout` | `int` | `1000` | Connection timeout (ms) |
| `idle_timeout` | `int` | | Connection idle timeout (ms) |
| `max_conns_per_node` | `int` | `100` | Max connections per node |
| `min_conns_per_node` | `int` | `0` | Pre-warm connections |
| `tend_interval` | `int` | `1000` | Cluster tend interval (ms) |
| `use_services_alternate` | `bool` | `false` | Use alternate service addresses |

### `ReadPolicy`

Used by: `get()`, `select()`, `exists()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `1000` | Total transaction timeout (ms) |
| `max_retries` | `int` | `2` | Max retries |
| `sleep_between_retries` | `int` | `0` | Sleep between retries (ms) |
| `filter_expression` | `Any` | | Expression filter built via `aerospike_py.exp`. |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | Replica selection algorithm. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP namespace read consistency. Maps to `aerospike-core` `ConsistencyLevel`. |
| `read_touch_ttl_percent` | `int` | `0` | Reset TTL on read when within N% of original write TTL (server v8+). `0` = server default, `-1` = never reset, `1..=100` = percent. |

### `WritePolicy`

Used by: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `1000` | Total transaction timeout (ms) |
| `max_retries` | `int` | `0` | Max retries |
| `durable_delete` | `bool` | `false` | Durable delete (Enterprise) |
| `key` | `int` | `POLICY_KEY_DIGEST` | Key send policy |
| `exists` | `int` | `POLICY_EXISTS_IGNORE` | Existence policy |
| `gen` | `int` | `POLICY_GEN_IGNORE` | Generation policy |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | Commit level |
| `ttl` | `int` | `0` | Record TTL (seconds) |
| `filter_expression` | `Any` | | Expression filter (`aerospike_py.exp`). |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency for read-after-write `operate()` ops. |
| `read_touch_ttl_percent` | `int` | `0` | Reset TTL on read within N% of write TTL (server v8+). |

### `BatchPolicy`

Used by: `batch_read()`, `batch_operate()`, `batch_write()`, `batch_remove()`

#### Transport / batch-level fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `1000` | Total transaction timeout (ms) |
| `max_retries` | `int` | `2` | Max retries |
| `filter_expression` | `Any` | | Expression filter |
| `allow_inline` | `bool` | `true` | Allow server inline processing in receiving thread |
| `allow_inline_ssd` | `bool` | `false` | Allow inline processing for SSD namespaces |
| `respond_all_keys` | `bool` | `true` | Attempt all keys regardless of per-record errors |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | Replica selection. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency for `batch_read`. |
| `read_touch_ttl_percent` | `int` | `0` | Reset TTL on read within N% of write TTL (server v8+). |

#### Write defaults (used by `batch_write`)

These fields apply to every record in a `batch_write()` call. Per-record [`WriteMeta`](#writemeta) overrides them — see the [precedence rule](#write-field-precedence-batch_write).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `int` | `POLICY_KEY_DIGEST` | Key send policy. Set `POLICY_KEY_SEND` to persist user keys server-side. |
| `exists` | `int` | `POLICY_EXISTS_UPDATE` | Existence policy (`UPDATE`, `CREATE_ONLY`, `REPLACE`, etc.). |
| `gen` | `int` | `POLICY_GEN_IGNORE` | Generation policy. Note: at batch-level, this is the `POLICY_GEN_*` enum index. Per-record `WriteMeta["gen"]` is the expected generation value. |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | Commit level (`ALL` or `MASTER`). |
| `durable_delete` | `bool` | `false` | Durable delete (Enterprise 3.10+). |
| `ttl` | `int` | `0` | Record TTL in seconds (`0` = namespace default, `-1` = never expire, `-2` = don't update). |

### `QueryPolicy`

Used by: `Query.results()`, `Query.foreach()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `0` | Total timeout (0 = no limit) |
| `max_retries` | `int` | `2` | Max retries |
| `max_records` | `int` | `0` | Max records (0 = all) |
| `records_per_second` | `int` | `0` | Rate limit per node (0 = unlimited). |
| `max_concurrent_nodes` | `int` | `0` | Limit parallel node queries (0 = unlimited). |
| `record_queue_size` | `int` | `5000` | Buffer capacity for record results. |
| `filter_expression` | `Any` | | Expression filter. |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | Replica selection. |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency. |
| `read_touch_ttl_percent` | `int` | `0` | Reset TTL on read within N% of write TTL (server v8+). |
| `expected_duration` | `int` | `QUERY_DURATION_LONG` | Server hint about query duration (`QUERY_DURATION_LONG` / `_SHORT` / `_LONG_RELAX_AP`). |
| `include_bin_data` | `bool` | `true` | Include bin payload in results. Set `False` to fetch keys/metadata only. |
| `partition_filter` | `PartitionFilter` | (all 4096) | Restrict the query/scan to a partition subset. Use `aerospike_py.partition_filter_*()` helpers. |

### `BatchReadPolicy`

Used by: per-record policy in `batch_read()`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `read_touch_ttl_percent` | `int` | `0` | Reset TTL on read within N% of write TTL (server v8+). `0` = server default, `-1` = never reset, `1..=100` = percent. |
| `filter_expression` | `Any` | | Expression filter. Records that fail return `BatchRecord.result == FILTERED_OUT`. |

### `BatchDeletePolicy`

Used by: batch-level policy for `batch_remove()`. Per-record overrides go in [`BatchDeleteMeta`](#batchdeletemeta).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gen` | `int` | `POLICY_GEN_IGNORE` | Generation policy enum (`POLICY_GEN_*`). |
| `key` | `int` | `POLICY_KEY_DIGEST` | Send user key with the delete (XDR-friendly). |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | Commit level. |
| `durable_delete` | `bool` | `false` | Leave a tombstone (Enterprise 3.10+). |
| `filter_expression` | `Any` | | Expression filter. |

### `BatchDeleteMeta`

Per-record meta for `batch_remove()`. Pass as the second element of a `(key, meta)` tuple in the `keys` argument. Setting `gen` enables CAS-style "delete only if generation matches" semantics — server returns per-record `GENERATION_ERROR` if generation has advanced.

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Expected generation. Setting this implies `POLICY_GEN_EQ`. |
| `key` | `int` | Key send policy (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `commit_level` | `int` | Commit level (`POLICY_COMMIT_LEVEL_ALL` / `_MASTER`). |
| `durable_delete` | `bool` | Durable delete (Enterprise 3.10+). |

```python
# CAS delete: only delete user_1 if generation is still 3.
client.batch_remove([
    (("test", "demo", "user_1"), {"gen": 3}),
    ("test", "demo", "user_2"),  # bare key, no CAS
])
```

### `PartitionFilter`

Opaque handle scoping a query/scan to a subset of partitions (server 6.0+). Construct via the module-level helpers:

```python
import aerospike_py

pf_all   = aerospike_py.partition_filter_all()
pf_one   = aerospike_py.partition_filter_by_id(42)        # single partition (0..4095)
pf_range = aerospike_py.partition_filter_by_range(0, 1024) # 1/4 of partitions
records = client.query("test", "demo").results(policy={"partition_filter": pf_range})
```

The handle holds mutable internal state (`Arc<Mutex<Vec<PartitionStatus>>>`). aerospike-py clones the inner filter at parse time so the user's handle is isolated from in-flight query state mutations. To deliberately resume a scan from where the previous run left off, pass the same handle to multiple `results()` calls — see [issue #318](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/318) for v2 cursor semantics.

### `AdminPolicy`

Used by: all `admin_*` methods, index operations, `truncate()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout` | `int` | `1000` | Timeout (ms) |

### `WriteMeta`

Used by: `put()`, `remove()`, `touch()`, `operate()` as the `meta` parameter, **and per-record in `batch_write()`** as the third tuple element `(key, bins, meta)`.

In `batch_write()`, fields set in per-record `WriteMeta` override the corresponding batch-level [`BatchPolicy`](#batchpolicy) defaults — see the [precedence rule](#write-field-precedence-batch_write).

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Expected generation. Setting this implies `POLICY_GEN_EQ` (CAS-style write). |
| `ttl` | `int` | Record TTL in seconds. Special values: `0` = namespace default, `-1` = never expire, `-2` = don't update. |
| `key` | `int` | Key send policy (`POLICY_KEY_DIGEST` / `POLICY_KEY_SEND`). |
| `exists` | `int` | Existence policy (`POLICY_EXISTS_*`). |
| `commit_level` | `int` | Commit level (`POLICY_COMMIT_LEVEL_ALL` / `_MASTER`). |
| `durable_delete` | `bool` | Durable delete (Enterprise 3.10+). |

#### Write field precedence (batch_write)

For every write field, **per-record `WriteMeta` always wins over batch-level `BatchPolicy`**:

| Field            | `BatchPolicy` (batch-level) | `WriteMeta` (per-record) | Notes |
|------------------|-----------------------------|--------------------------|-------|
| `ttl`            | ✅                          | ✅                       | Same semantics on both sides. |
| `key`            | ✅                          | ✅                       | Set `POLICY_KEY_SEND` to persist user keys server-side. |
| `exists`         | ✅                          | ✅                       | e.g. `POLICY_EXISTS_CREATE_ONLY` for upsert-fail-on-exists. |
| `gen`            | ✅ (enum index)             | ✅ (expected value)      | Asymmetric: batch-level = `POLICY_GEN_*` enum index; per-record = numeric generation that forces `POLICY_GEN_EQ`. |
| `commit_level`   | ✅                          | ✅                       | |
| `durable_delete` | ✅                          | ✅                       | |

### `Privilege`

Used by: `admin_create_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`

| Field | Type | Description |
|-------|------|-------------|
| `code` | `int` | Privilege code (`PRIV_READ`, `PRIV_WRITE`, etc.) |
| `ns` | `str` | Namespace scope (empty = global) |
| `set` | `str` | Set scope (empty = namespace-wide) |

### `UserInfo`

Returned by: `admin_query_user_info()`, `admin_query_users_info()`

| Field | Type | Description |
|-------|------|-------------|
| `user` | `str` | Username |
| `roles` | `list[str]` | Assigned roles |
| `conns_in_use` | `int` | Active connections |

### `RoleInfo`

Returned by: `admin_query_role()`, `admin_query_roles()`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Role name |
| `privileges` | `list[Privilege]` | Assigned privileges |
| `allowlist` | `list[str]` | IP allowlist |
| `read_quota` | `int` | Read quota |
| `write_quota` | `int` | Write quota |
