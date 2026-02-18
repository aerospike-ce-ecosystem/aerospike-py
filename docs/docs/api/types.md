---
title: Types
sidebar_label: Types
sidebar_position: 2
description: NamedTuple return types and TypedDict input types for aerospike-py.
---

aerospike-py uses **NamedTuple** classes for return values and **TypedDict** classes for input parameters.
All types can be imported from the top-level package or from `aerospike_py.types`.

```python
from aerospike_py import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
# or
from aerospike_py.types import Record, ExistsResult, ReadPolicy, WritePolicy, WriteMeta
```

## Return Types (NamedTuple)

NamedTuple return types support both attribute access and tuple unpacking for backward compatibility.

### `Record`

Full record returned by read and operate methods.

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key (`None` if `POLICY_KEY_DIGEST`) |
| `meta` | `RecordMetadata \| None` | Record metadata |
| `bins` | `dict[str, Any] \| None` | Bin name-value pairs |

**Returned by**: `get()`, `select()`, `operate()`, `batch_operate()`, `batch_remove()`, `Query.results()`

```python
record: Record = client.get(key)
print(record.meta.gen)   # attribute access
print(record.bins)       # {"name": "Alice", "age": 30}

key, meta, bins = record  # tuple unpacking (backward compat)
```

### `RecordMetadata`

Record metadata with generation and TTL.

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Record generation (optimistic lock version) |
| `ttl` | `int` | Record time-to-live in seconds |

```python
record = client.get(key)
print(record.meta.gen)  # 1
print(record.meta.ttl)  # 2591998
```

### `AerospikeKey`

Record key returned by the server.

| Field | Type | Description |
|-------|------|-------------|
| `namespace` | `str` | Namespace name |
| `set_name` | `str` | Set name |
| `user_key` | `str \| int \| bytes \| None` | User-provided primary key (`None` if `POLICY_KEY_DIGEST`) |
| `digest` | `bytes` | 20-byte RIPEMD-160 digest |

```python
record = client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})
print(record.key.namespace)   # "test"
print(record.key.set_name)    # "demo"
print(record.key.user_key)    # "user1"
```

### `ExistsResult`

Existence check result.

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `meta` | `RecordMetadata \| None` | Metadata (`None` if record does not exist) |

**Returned by**: `exists()`

```python
result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")

_, meta = result  # tuple unpacking
```

### `InfoNodeResult`

Info command result per cluster node.

| Field | Type | Description |
|-------|------|-------------|
| `node_name` | `str` | Cluster node name |
| `error_code` | `int` | 0 on success |
| `response` | `str` | Info response string |

**Returned by**: `info_all()`

```python
results: list[InfoNodeResult] = client.info_all("namespaces")
for result in results:
    print(f"{result.node_name}: {result.response}")
```

### `OperateOrderedResult`

Result from `operate_ordered()` with ordered bin results.

| Field | Type | Description |
|-------|------|-------------|
| `key` | `AerospikeKey \| None` | Record key |
| `meta` | `RecordMetadata \| None` | Record metadata |
| `ordered_bins` | `list[BinTuple]` | Ordered operation results |

**Returned by**: `operate_ordered()`

```python
result: OperateOrderedResult = client.operate_ordered(key, ops)
for bin_tuple in result.ordered_bins:
    print(f"{bin_tuple.name} = {bin_tuple.value}")
```

### `BinTuple`

Single bin name-value pair used in ordered results.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Bin name |
| `value` | `Any` | Bin value |

## API → Return Type Quick Reference

| Method | Return Type |
|--------|-------------|
| `get()` | `Record` |
| `select()` | `Record` |
| `exists()` | `ExistsResult` |
| `operate()` | `Record` |
| `operate_ordered()` | `OperateOrderedResult` |
| `info_all()` | `list[InfoNodeResult]` |
| `batch_read()` | `BatchRecords` |
| `batch_operate()` | `list[Record]` |
| `batch_remove()` | `list[Record]` |
| `Query.results()` | `list[Record]` |

---

## Input Types (TypedDict)

TypedDict input types provide IDE autocompletion and type checking for `policy` and `meta` parameters.
All fields are optional (`total=False`).

### `ClientConfig`

Configuration dictionary for client creation.

**Used by**: `aerospike_py.client(config)`, `AsyncClient(config)`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hosts` | `list[tuple[str, int]]` | *required* | Cluster seed nodes |
| `cluster_name` | `str` | | Expected cluster name |
| `auth_mode` | `int` | `AUTH_INTERNAL` | Authentication mode (`AUTH_INTERNAL`, `AUTH_EXTERNAL`, `AUTH_PKI`) |
| `user` | `str` | | Username for authentication |
| `password` | `str` | | Password for authentication |
| `timeout` | `int` | `1000` | Connection timeout in ms |
| `idle_timeout` | `int` | | Connection idle timeout in ms |
| `max_conns_per_node` | `int` | | Max connections per node |
| `min_conns_per_node` | `int` | | Min connections per node |
| `tend_interval` | `int` | | Cluster tend interval in ms |
| `use_services_alternate` | `bool` | `False` | Use alternate services addresses |

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
    "timeout": 5000,
}
client = aerospike_py.client(config).connect()
```

### `ReadPolicy`

Policy for read operations.

**Used by**: `get()`, `select()`, `exists()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket idle timeout in ms |
| `total_timeout` | `int` | `1000` | Total transaction timeout in ms |
| `max_retries` | `int` | `2` | Maximum number of retries |
| `sleep_between_retries` | `int` | `0` | Sleep between retries in ms |
| `filter_expression` | `Any` | | Expression filter (deprecated, use `expressions`) |
| `expressions` | `Any` | | Expression filter built with `aerospike_py.exp` |
| `replica` | `int` | `POLICY_REPLICA_SEQUENCE` | Replica algorithm |
| `read_mode_ap` | `int` | `POLICY_READ_MODE_AP_ONE` | AP read consistency level |

```python
policy: ReadPolicy = {
    "total_timeout": 5000,
    "max_retries": 3,
}
record = client.get(key, policy=policy)
```

### `WritePolicy`

Policy for write operations.

**Used by**: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket idle timeout in ms |
| `total_timeout` | `int` | `1000` | Total transaction timeout in ms |
| `max_retries` | `int` | `0` | Maximum number of retries |
| `durable_delete` | `bool` | `False` | Use durable delete (Enterprise only) |
| `key` | `int` | `POLICY_KEY_DIGEST` | Key send policy (`POLICY_KEY_DIGEST`, `POLICY_KEY_SEND`) |
| `exists` | `int` | `POLICY_EXISTS_IGNORE` | Existence policy (`POLICY_EXISTS_*`) |
| `gen` | `int` | `POLICY_GEN_IGNORE` | Generation policy (`POLICY_GEN_IGNORE`, `POLICY_GEN_EQ`, `POLICY_GEN_GT`) |
| `commit_level` | `int` | `POLICY_COMMIT_LEVEL_ALL` | Commit level (`POLICY_COMMIT_LEVEL_ALL`, `POLICY_COMMIT_LEVEL_MASTER`) |
| `ttl` | `int` | `0` | Record TTL in seconds |
| `filter_expression` | `Any` | | Expression filter (deprecated, use `expressions`) |
| `expressions` | `Any` | | Expression filter built with `aerospike_py.exp` |

```python
policy: WritePolicy = {
    "key": aerospike_py.POLICY_KEY_SEND,
    "exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY,
}
client.put(key, bins, policy=policy)
```

### `BatchPolicy`

Policy for batch operations.

**Used by**: `batch_read()`, `batch_operate()`, `batch_remove()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket idle timeout in ms |
| `total_timeout` | `int` | `1000` | Total transaction timeout in ms |
| `max_retries` | `int` | `2` | Maximum number of retries |
| `filter_expression` | `Any` | | Expression filter |

```python
policy: BatchPolicy = {"total_timeout": 10000}
batch = client.batch_read(keys, policy=policy)
```

### `QueryPolicy`

Policy for query operations.

**Used by**: `Query.results()`, `Query.foreach()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Socket idle timeout in ms |
| `total_timeout` | `int` | `0` | Total transaction timeout in ms (0 = no limit) |
| `max_retries` | `int` | `2` | Maximum number of retries |
| `max_records` | `int` | `0` | Max records to return (0 = all) |
| `records_per_second` | `int` | `0` | Rate limit (0 = unlimited) |
| `filter_expression` | `Any` | | Expression filter (deprecated, use `expressions`) |
| `expressions` | `Any` | | Expression filter built with `aerospike_py.exp` |

```python
policy: QueryPolicy = {"max_records": 100}
records = query.results(policy=policy)
```

### `AdminPolicy`

Policy for admin operations.

**Used by**: `admin_create_user()`, `admin_drop_user()`, `admin_change_password()`, `admin_grant_roles()`, `admin_revoke_roles()`, `admin_query_user_info()`, `admin_query_users_info()`, `admin_create_role()`, `admin_drop_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`, `admin_query_role()`, `admin_query_roles()`, `admin_set_whitelist()`, `admin_set_quotas()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout` | `int` | `1000` | Admin operation timeout in ms |

```python
policy: AdminPolicy = {"timeout": 5000}
client.admin_create_user("user", "pass", ["read-write"], policy=policy)
```

### `WriteMeta`

Metadata for write operations.

**Used by**: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()` — as the `meta` parameter

| Field | Type | Description |
|-------|------|-------------|
| `gen` | `int` | Expected generation for optimistic locking (use with `POLICY_GEN_EQ`) |
| `ttl` | `int` | Record time-to-live in seconds |

```python
# Set TTL
meta: WriteMeta = {"ttl": 300}
client.put(key, bins, meta=meta)

# Optimistic locking
record = client.get(key)
meta: WriteMeta = {"gen": record.meta.gen}
client.put(key, new_bins, meta=meta, policy={"gen": aerospike_py.POLICY_GEN_EQ})
```

### `Privilege`

Privilege definition for admin role management.

**Used by**: `admin_create_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`

| Field | Type | Description |
|-------|------|-------------|
| `code` | `int` | Privilege code (`PRIV_READ`, `PRIV_WRITE`, `PRIV_READ_WRITE`, etc.) |
| `ns` | `str` | Namespace scope (empty string for global) |
| `set` | `str` | Set scope (empty string for namespace-wide) |

```python
privilege: Privilege = {
    "code": aerospike_py.PRIV_READ_WRITE,
    "ns": "test",
    "set": "demo",
}
client.admin_create_role("custom_role", [privilege])
```

### `UserInfo`

User information returned by admin queries.

**Returned by**: `admin_query_user_info()`, `admin_query_users_info()`

| Field | Type | Description |
|-------|------|-------------|
| `user` | `str` | Username |
| `roles` | `list[str]` | Assigned role names |
| `conns_in_use` | `int` | Number of active connections |

### `RoleInfo`

Role information returned by admin queries.

**Returned by**: `admin_query_role()`, `admin_query_roles()`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Role name |
| `privileges` | `list[Privilege]` | Assigned privileges |
| `allowlist` | `list[str]` | IP allowlist |
| `read_quota` | `int` | Read quota |
| `write_quota` | `int` | Write quota |
