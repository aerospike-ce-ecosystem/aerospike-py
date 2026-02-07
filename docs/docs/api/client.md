---
title: Client
sidebar_label: Client (Sync & Async)
sidebar_position: 1
description: Complete API reference for the synchronous Client and asynchronous AsyncClient classes.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

aerospike-py provides both synchronous (`Client`) and asynchronous (`AsyncClient`) APIs with identical functionality.

## Creating a Client

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()

asyncio.run(main())
```

  </TabItem>
</Tabs>

## Context Manager

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

### `__enter__()` / `__exit__()`

```python
with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:
    client.put(key, bins)
# close() is called automatically on exit
```

  </TabItem>
  <TabItem value="async" label="Async Client">

### `async __aenter__()` / `async __aexit__()`

```python
async with AsyncClient({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}) as client:
    await client.connect()
    await client.put(key, bins)
# close() is called automatically
```

  </TabItem>
</Tabs>

## Connection

### `connect(username=None, password=None)`

Connect to the Aerospike cluster.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

Returns `self` for method chaining.

```python
client = aerospike.client(config).connect()
# With authentication
client = aerospike.client(config).connect("admin", "admin")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.connect()
await client.connect("admin", "admin")
```

  </TabItem>
</Tabs>

### `is_connected()`

Returns `True` if the client is connected. This is a synchronous method in both clients.

```python
if client.is_connected():
    print("Connected")
```

### `close()`

Close the connection to the cluster.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.close()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.close()
```

  </TabItem>
</Tabs>

### `get_node_names()`

Returns a list of cluster node names.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
nodes = client.get_node_names()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
nodes = await client.get_node_names()
```

  </TabItem>
</Tabs>

## CRUD Operations

### `put(key, bins, meta=None, policy=None)`

Write a record.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `tuple[str, str, str\|int\|bytes]` | `(namespace, set, pk)` |
| `bins` | `dict[str, Any]` | Bin name-value pairs |
| `meta` | `dict` | Optional: `{"ttl": int, "gen": int}` |
| `policy` | `dict` | Optional: `{"key", "exists", "gen", "timeout", ...}` |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"x": 1}, meta={"ttl": 300})
client.put(key, {"x": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
key = ("test", "demo", "user1")
await client.put(key, {"name": "Alice", "age": 30})
await client.put(key, {"x": 1}, meta={"ttl": 300})
await client.put(key, {"x": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

  </TabItem>
</Tabs>

### `get(key, policy=None)`

Read a record. Returns `(key, meta, bins)`.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
key, meta, bins = client.get(("test", "demo", "user1"))
# meta = {"gen": 1, "ttl": 2591998}
# bins = {"name": "Alice", "age": 30}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
key, meta, bins = await client.get(("test", "demo", "user1"))
```

  </TabItem>
</Tabs>

:::note

Raises `RecordNotFound` if the record does not exist.

:::

### `select(key, bins, policy=None)`

Read specific bins from a record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta, bins = client.select(key, ["name"])
# bins = {"name": "Alice"}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta, bins = await client.select(key, ["name"])
```

  </TabItem>
</Tabs>

### `exists(key, policy=None)`

Check if a record exists. Returns `(key, meta)` where `meta` is `None` if not found.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta = client.exists(key)
if meta is not None:
    print(f"Found, gen={meta['gen']}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta = await client.exists(key)
if meta is not None:
    print(f"Found, gen={meta['gen']}")
```

  </TabItem>
</Tabs>

### `remove(key, meta=None, policy=None)`

Delete a record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove(key)
# With generation check
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove(key)
await client.remove(key, meta={"gen": 3}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

  </TabItem>
</Tabs>

### `touch(key, val=0, meta=None, policy=None)`

Reset TTL for a record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.touch(key, val=300)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.touch(key, val=300)
```

  </TabItem>
</Tabs>

## String / Numeric Operations

### `append(key, bin, val, meta=None, policy=None)`

Append string to a bin.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.append(key, "name", "_suffix")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.append(key, "name", "_suffix")
```

  </TabItem>
</Tabs>

### `prepend(key, bin, val, meta=None, policy=None)`

Prepend string to a bin.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.prepend(key, "name", "prefix_")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.prepend(key, "name", "prefix_")
```

  </TabItem>
</Tabs>

### `increment(key, bin, offset, meta=None, policy=None)`

Increment integer or float bin value.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.increment(key, "age", 1)
client.increment(key, "score", 0.5)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.increment(key, "age", 1)
await client.increment(key, "score", 0.5)
```

  </TabItem>
</Tabs>

### `remove_bin(key, bin_names, meta=None, policy=None)`

Remove specific bins from a record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove_bin(key, ["temp_bin", "debug_bin"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove_bin(key, ["temp_bin", "debug_bin"])
```

  </TabItem>
</Tabs>

## Multi-Operation

### `operate(key, ops, meta=None, policy=None)`

Execute multiple operations atomically on a single record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = client.operate(key, ops)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = await client.operate(key, ops)
```

  </TabItem>
</Tabs>

### `operate_ordered(key, ops, meta=None, policy=None)`

Same as `operate` but returns results as an ordered list of `(bin, value)` tuples.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
_, meta, results = client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
_, meta, results = await client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

  </TabItem>
</Tabs>

## Batch Operations

### `batch_read(keys, bins=None, policy=None)`

Read multiple records. Returns `BatchRecords`.

- `bins=None` - Read all bins
- `bins=["a", "b"]` - Read specific bins
- `bins=[]` - Existence check only

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# Read all bins
batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(bins)

# Read specific bins
batch = client.batch_read(keys, bins=["name", "age"])

# Existence check
batch = client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# Read all bins
batch = await client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        key, meta, bins = br.record
        print(bins)

# Read specific bins
batch = await client.batch_read(keys, bins=["name", "age"])

# Existence check
batch = await client.batch_read(keys, bins=[])
for br in batch.batch_records:
    print(f"{br.key}: exists={br.record is not None}")
```

  </TabItem>
</Tabs>

### `batch_operate(keys, ops, policy=None)`

Execute operations on multiple records.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = await client.batch_operate(keys, ops)
```

  </TabItem>
</Tabs>

### `batch_remove(keys, policy=None)`

Delete multiple records.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
results = client.batch_remove(keys)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.batch_remove(keys)
```

  </TabItem>
</Tabs>

## Query & Scan

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

### `query(namespace, set_name)`

Create a `Query` object for secondary index queries. See [Query & Scan API](query-scan.md).

```python
query = client.query("test", "demo")
```

### `scan(namespace, set_name)`

Create a `Scan` object for full namespace/set scans. See [Query & Scan API](query-scan.md).

```python
scan = client.scan("test", "demo")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

### `async scan(namespace, set_name, policy=None)`

Scan all records in a namespace/set. Returns a list of records directly.

```python
records = await client.scan("test", "demo")
for key, meta, bins in records:
    print(bins)
```

:::note

AsyncClient does not have a `query()` method. Use `scan()` with [Expression Filters](../guides/expression-filters.md) for server-side filtering.

:::

  </TabItem>
</Tabs>

## Index Management

### `index_integer_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a numeric secondary index.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_integer_create("test", "demo", "age", "age_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_integer_create("test", "demo", "age", "age_idx")
```

  </TabItem>
</Tabs>

### `index_string_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a string secondary index.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_string_create("test", "demo", "name", "name_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_string_create("test", "demo", "name", "name_idx")
```

  </TabItem>
</Tabs>

### `index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a geospatial secondary index.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

  </TabItem>
</Tabs>

### `index_remove(namespace, index_name, policy=None)`

Remove a secondary index.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_remove("test", "age_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_remove("test", "age_idx")
```

  </TabItem>
</Tabs>

## Truncate

### `truncate(namespace, set_name, nanos=0, policy=None)`

Remove all records in a namespace/set.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.truncate("test", "demo")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.truncate("test", "demo")
```

  </TabItem>
</Tabs>

## UDF

### `udf_put(filename, udf_type=0, policy=None)`

Register a Lua UDF module.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.udf_put("my_udf.lua")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.udf_put("my_udf.lua")
```

  </TabItem>
</Tabs>

### `udf_remove(module, policy=None)`

Remove a registered UDF module.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.udf_remove("my_udf")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.udf_remove("my_udf")
```

  </TabItem>
</Tabs>

### `apply(key, module, function, args=None, policy=None)`

Execute a UDF on a record.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
result = await client.apply(key, "my_udf", "my_function", [1, "hello"])
```

  </TabItem>
</Tabs>

## Concurrency Patterns (Async)

### Parallel Writes with `asyncio.gather`

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.put(k, {"idx": i}) for i, k in enumerate(keys)]
await asyncio.gather(*tasks)
```

### Parallel Reads

```python
keys = [("test", "demo", f"item_{i}") for i in range(100)]
tasks = [client.get(k) for k in keys]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### Mixed Operations

```python
async def process_user(client, user_id):
    key = ("test", "users", user_id)
    _, _, bins = await client.get(key)
    bins["visits"] = bins.get("visits", 0) + 1
    await client.put(key, bins)
    return bins

results = await asyncio.gather(*[
    process_user(client, f"user_{i}")
    for i in range(10)
])
```

## Admin Operations

### User Management

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

| Method | Description |
|--------|-------------|
| `admin_create_user(username, password, roles)` | Create a user |
| `admin_drop_user(username)` | Delete a user |
| `admin_change_password(username, password)` | Change password |
| `admin_grant_roles(username, roles)` | Grant roles |
| `admin_revoke_roles(username, roles)` | Revoke roles |
| `admin_query_user(username)` | Get user info |
| `admin_query_users()` | List all users |

  </TabItem>
  <TabItem value="async" label="Async Client">

| Method | Description |
|--------|-------------|
| `async admin_create_user(username, password, roles)` | Create a user |
| `async admin_drop_user(username)` | Delete a user |
| `async admin_change_password(username, password)` | Change password |
| `async admin_grant_roles(username, roles)` | Grant roles |
| `async admin_revoke_roles(username, roles)` | Revoke roles |
| `async admin_query_user(username)` | Get user info |
| `async admin_query_users()` | List all users |

  </TabItem>
</Tabs>

### Role Management

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

| Method | Description |
|--------|-------------|
| `admin_create_role(role, privileges, ...)` | Create a role |
| `admin_drop_role(role)` | Delete a role |
| `admin_grant_privileges(role, privileges)` | Grant privileges |
| `admin_revoke_privileges(role, privileges)` | Revoke privileges |
| `admin_query_role(role)` | Get role info |
| `admin_query_roles()` | List all roles |
| `admin_set_whitelist(role, whitelist)` | Set IP whitelist |
| `admin_set_quotas(role, read_quota, write_quota)` | Set quotas |

```python
# Create user
client.admin_create_user("new_user", "password", ["read-write"])

# Create role with privileges
client.admin_create_role("custom_role", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

| Method | Description |
|--------|-------------|
| `async admin_create_role(role, privileges, ...)` | Create a role |
| `async admin_drop_role(role)` | Delete a role |
| `async admin_grant_privileges(role, privileges)` | Grant privileges |
| `async admin_revoke_privileges(role, privileges)` | Revoke privileges |
| `async admin_query_role(role)` | Get role info |
| `async admin_query_roles()` | List all roles |
| `async admin_set_whitelist(role, whitelist)` | Set IP whitelist |
| `async admin_set_quotas(role, read_quota, write_quota)` | Set quotas |

```python
# Create user
await client.admin_create_user("new_user", "password", ["read-write"])

# Grant roles
await client.admin_grant_roles("new_user", ["sys-admin"])

# Create role with privileges
await client.admin_create_role("custom_role", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"}
])
```

  </TabItem>
</Tabs>

## Expression Filters

All read/write/batch operations that accept a `policy` parameter support the `filter_expression` key for server-side filtering (requires Server 5.2+):

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
from aerospike_py import exp

expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Get with filter
_, _, bins = client.get(key, policy={"filter_expression": expr})

# Put with filter (only update if filter matches)
expr = exp.eq(exp.string_bin("status"), exp.string_val("active"))
client.put(key, {"visits": 1}, policy={"filter_expression": expr})

# Query with filter
query = client.query("test", "demo")
records = query.results(policy={"filter_expression": expr})

# Scan with filter
scan = client.scan("test", "demo")
records = scan.results(policy={"filter_expression": expr})

# Batch with filter
ops = [{"op": aerospike.OPERATOR_READ, "bin": "status", "val": None}]
records = client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
from aerospike_py import exp

expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Get with filter
_, _, bins = await client.get(key, policy={"filter_expression": expr})

# Scan with filter
records = await client.scan("test", "demo", policy={"filter_expression": expr})

# Batch with filter
ops = [{"op": aerospike.OPERATOR_READ, "bin": "age", "val": None}]
records = await client.batch_operate(keys, ops, policy={"filter_expression": expr})
```

  </TabItem>
</Tabs>

:::tip

If a record does not match the filter expression, the operation raises `FilteredOut`.
See the [Expression Filters Guide](../guides/expression-filters.md) for detailed documentation.

:::
