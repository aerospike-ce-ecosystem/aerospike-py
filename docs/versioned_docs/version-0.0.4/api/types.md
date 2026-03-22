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

Returned by: `get()`, `select()`, `operate()`, `batch_operate()`, `batch_remove()`, `Query.results()`

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
| `batch_read()` | `BatchRecords` \| `NumpyBatchRecords` |
| `batch_operate()`, `batch_remove()` | `list[Record]` |
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
| `expressions` | `Any` | | Expression filter (`aerospike_py.exp`) |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | Replica algorithm |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency |

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
| `expressions` | `Any` | | Expression filter |

### `BatchPolicy`

Used by: `batch_read()`, `batch_operate()`, `batch_remove()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `1000` | Total transaction timeout (ms) |
| `max_retries` | `int` | `2` | Max retries |
| `filter_expression` | `Any` | | Expression filter |

### `QueryPolicy`

Used by: `Query.results()`, `Query.foreach()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket timeout (ms) |
| `total_timeout` | `int` | `0` | Total timeout (0 = no limit) |
| `max_retries` | `int` | `2` | Max retries |
| `max_records` | `int` | `0` | Max records (0 = all) |
| `records_per_second` | `int` | `0` | Rate limit (0 = unlimited) |
| `expressions` | `Any` | | Expression filter |

### `AdminPolicy`

Used by: all `admin_*` methods, index operations, `truncate()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout` | `int` | `1000` | Timeout (ms) |

### `WriteMeta`

Used by: `put()`, `remove()`, `touch()`, `operate()` etc. as `meta` parameter

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Expected generation (for `POLICY_GEN_EQ`) |
| `ttl` | `int` | Record TTL in seconds |

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
