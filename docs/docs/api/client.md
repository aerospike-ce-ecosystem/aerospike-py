---
title: Client API
sidebar_label: Client (Sync & Async)
sidebar_position: 1
description: Complete API reference for Client and AsyncClient.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

Both `Client` (sync) and `AsyncClient` (async) provide identical functionality. Async methods are coroutines that must be awaited.

## Factory & Utilities

### `client(config) -> Client`

Create a new sync client.

```python
import aerospike_py

client = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]}).connect()
```

### `set_log_level(level)`

Set log verbosity. See [Logging guide](../integrations/observability/logging.md).

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

### `get_metrics() -> str`

Return Prometheus-format metrics string. See [Metrics guide](../integrations/observability/metrics.md).

### `start_metrics_server(port=9464)` / `stop_metrics_server()`

Start/stop a background HTTP server at `/metrics`.

### `init_tracing()` / `shutdown_tracing()`

Initialize/shut down OpenTelemetry tracing. See [Tracing guide](../integrations/observability/tracing.md).

---

## Connection

### `connect(username=None, password=None)`

Connect to the cluster. Returns `self` for chaining.

**Raises:** `ClusterError`

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
client = aerospike_py.client(config).connect()
client = aerospike_py.client(config).connect("admin", "admin")
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
client = await AsyncClient(config).connect()
```

  </TabItem>
</Tabs>

### `is_connected() -> bool`

```python
if client.is_connected():
    print("Connected")
```

### `close()`

Close the connection. Use context managers for automatic cleanup.

### `get_node_names() -> list[str]`

```python
nodes = client.get_node_names()  # ['BB9020011AC4202']
```

---

## Info

### `info_all(command, policy=None) -> list[InfoNodeResult]`

Send info command to all nodes.

```python
for node, err, response in client.info_all("namespaces"):
    print(f"{node}: {response}")
```

### `info_random_node(command, policy=None) -> str`

Send info command to a random node.

---

## CRUD

### `put(key, bins, meta=None, policy=None)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `tuple[str, str, str\|int\|bytes]` | `(namespace, set, primary_key)` |
| `bins` | `dict[str, Any]` | Bin name-value pairs |
| `meta` | [`WriteMeta`](types.md#writemeta) | Optional `{"ttl": int, "gen": int}` |
| `policy` | [`WritePolicy`](types.md#writepolicy) | Optional policy overrides |

**Raises:** `RecordExistsError`, `RecordTooBig`

<Tabs>
  <TabItem value="sync" label="Sync" default>

```python
client.put(("test", "demo", "user1"), {"name": "Alice", "age": 30})
client.put(key, {"score": 100}, meta={"ttl": 300})
```

  </TabItem>
  <TabItem value="async" label="Async">

```python
await client.put(("test", "demo", "user1"), {"name": "Alice", "age": 30})
```

  </TabItem>
</Tabs>

### `get(key, policy=None) -> Record`

**Returns:** [`Record`](types.md#record) `(key, meta, bins)` NamedTuple.
**Raises:** `RecordNotFound`

```python
record = client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice", "age": 30}

# Tuple unpacking (backward compat)
_, meta, bins = client.get(key)
```

### `select(key, bins, policy=None) -> Record`

Read specific bins only.

```python
record = client.select(key, ["name"])
# record.bins = {"name": "Alice"}
```

### `exists(key, policy=None) -> ExistsResult`

**Returns:** [`ExistsResult`](types.md#existsresult) `(key, meta)`. `meta` is `None` if not found.

```python
result = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

### `remove(key, meta=None, policy=None)`

**Raises:** `RecordNotFound`

```python
client.remove(key)
# With generation check
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike_py.POLICY_GEN_EQ})
```

### `touch(key, val=0, meta=None, policy=None)`

Reset record TTL.

```python
client.touch(key, val=300)
```

---

## String / Numeric

### `append(key, bin, val, meta=None, policy=None)`

```python
client.append(key, "name", "_suffix")
```

### `prepend(key, bin, val, meta=None, policy=None)`

```python
client.prepend(key, "name", "prefix_")
```

### `increment(key, bin, offset, meta=None, policy=None)`

```python
client.increment(key, "age", 1)
client.increment(key, "score", 0.5)
```

### `remove_bin(key, bin_names, meta=None, policy=None)`

```python
client.remove_bin(key, ["temp_bin", "debug_bin"])
```

---

## Multi-Operation

### `operate(key, ops, meta=None, policy=None) -> Record`

Execute multiple operations atomically on a single record.

```python
import aerospike_py

ops: list[dict] = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record = client.operate(("test", "demo", "key1"), ops)
print(record.bins)
```

### `operate_ordered(key, ops, meta=None, policy=None) -> OperateOrderedResult`

Like `operate()` but preserves operation order in results.

```python
result = client.operate_ordered(key, ops)
for bt in result.ordered_bins:
    print(f"{bt.name} = {bt.value}")
```

---

## Batch

### `batch_read(keys, bins=None, policy=None, _dtype=None) -> BatchRecords`

| `bins` value | Behavior |
|-------------|----------|
| `None` | Read all bins |
| `["a", "b"]` | Read specific bins |
| `[]` | Existence check only |

Pass `_dtype=np.dtype(...)` for [NumPy batch reads](../guides/crud/numpy-batch.md).

```python
keys: list[tuple] = [("test", "demo", f"user_{i}") for i in range(10)]
batch = client.batch_read(keys, bins=["name", "age"])
for br in batch.batch_records:
    if br.record:
        print(br.record.bins)
```

### `batch_write_numpy(data, namespace, set_name, _dtype, key_field="_key", policy=None) -> list[Record]`

Write multiple records from a numpy structured array. Each row becomes a separate write operation.

| Parameter | Description |
|-----------|-------------|
| `data` | Numpy structured array containing record data. |
| `namespace` | Target Aerospike namespace. |
| `set_name` | Target set name. |
| `_dtype` | Numpy dtype describing the array layout. |
| `key_field` | Name of the dtype field to use as the user key (default `"_key"`). |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |

```python
import numpy as np

dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)
results = client.batch_write_numpy(data, "test", "demo", dtype)
```

See [NumPy Batch Write Guide](../guides/crud/numpy-batch-write.md) for detailed usage and examples.

### `batch_operate(keys, ops, policy=None) -> list[Record]`

```python
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
```

### `batch_remove(keys, policy=None) -> list[Record]`

```python
results = client.batch_remove(keys)
```

---

## Query

### `query(namespace, set_name) -> Query`

Create a query object for secondary index queries.

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records: list[Record] = query.results()
```

See [Query API](query-scan.md) and [Query Guide](../guides/query-scan/query-scan.md) for details.

---

## Index Management

### `index_integer_create(ns, set, bin, index_name, policy=None)`

### `index_string_create(ns, set, bin, index_name, policy=None)`

### `index_geo2dsphere_create(ns, set, bin, index_name, policy=None)`

**Raises:** `IndexFoundError`

```python
client.index_integer_create("test", "demo", "age", "age_idx")
client.index_string_create("test", "demo", "name", "name_idx")
```

### `index_remove(namespace, index_name, policy=None)`

**Raises:** `IndexNotFound`

```python
client.index_remove("test", "age_idx")
```

---

## Truncate

### `truncate(namespace, set_name, nanos=0, policy=None)`

```python
client.truncate("test", "demo")
```

---

## UDF

### `udf_put(filename, udf_type=0, policy=None)`

Register a Lua UDF module.

### `udf_remove(module, policy=None)`

Remove a registered UDF module.

### `apply(key, module, function, args=None, policy=None) -> Any`

Execute a UDF on a single record.

```python
result = client.apply(("test", "demo", "key1"), "my_udf", "my_func", [1, "hello"])
```

---

## Admin

User and role management for security-enabled clusters. See [Admin Guide](../guides/admin/admin.md).

### User Operations

```python
client.admin_create_user("alice", "password", ["read-write"])
client.admin_drop_user("alice")
client.admin_change_password("alice", "new_pass")
client.admin_grant_roles("alice", ["sys-admin"])
client.admin_revoke_roles("alice", ["read-write"])
info: dict = client.admin_query_user_info("alice")
users: list[dict] = client.admin_query_users_info()
```

### Role Operations

```python
client.admin_create_role("reader", [{"code": aerospike_py.PRIV_READ, "ns": "test"}])
client.admin_drop_role("reader")
client.admin_grant_privileges("reader", [{"code": aerospike_py.PRIV_WRITE}])
client.admin_revoke_privileges("reader", [{"code": aerospike_py.PRIV_WRITE}])
client.admin_set_whitelist("reader", ["10.0.0.0/8"])
client.admin_set_quotas("reader", read_quota=1000, write_quota=500)
role: dict = client.admin_query_role("reader")
roles: list[dict] = client.admin_query_roles()
```
