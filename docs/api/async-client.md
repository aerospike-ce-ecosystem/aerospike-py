# AsyncClient

The `AsyncClient` provides a fully asynchronous API for Aerospike operations using Python's `asyncio`.

## Creating an AsyncClient

```python
import asyncio
from aerospike_py import AsyncClient

async def main():
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    })
    await client.connect()
    # ... operations ...
    await client.close()

asyncio.run(main())
```

## Context Manager

`AsyncClient` supports the async context manager protocol (`async with`):

### `async __aenter__()` / `async __aexit__()`

```python
async def main():
    async with AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "cluster_name": "docker",
    }) as client:
        await client.connect()
        # ... operations ...
    # close() is called automatically
```

## Connection

### `async connect(username=None, password=None)`

Connect to the Aerospike cluster.

```python
await client.connect()
await client.connect("admin", "admin")
```

### `is_connected()`

Returns `True` if connected. This is a synchronous method.

```python
if client.is_connected():
    print("Connected")
```

### `async close()`

Close the connection.

```python
await client.close()
```

### `async get_node_names()`

Returns cluster node names.

```python
nodes = await client.get_node_names()
```

## CRUD Operations

### `async put(key, bins, meta=None, policy=None)`

Write a record.

```python
key = ("test", "demo", "user1")
await client.put(key, {"name": "Alice", "age": 30})
await client.put(key, {"x": 1}, meta={"ttl": 300})
```

### `async get(key, policy=None)`

Read a record. Returns `(key, meta, bins)`.

```python
_, meta, bins = await client.get(key)
```

### `async select(key, bins, policy=None)`

Read specific bins.

```python
_, meta, bins = await client.select(key, ["name"])
```

### `async exists(key, policy=None)`

Check if a record exists. Returns `(key, meta)`.

```python
_, meta = await client.exists(key)
```

### `async remove(key, meta=None, policy=None)`

Delete a record.

```python
await client.remove(key)
```

### `async touch(key, val=0, meta=None, policy=None)`

Reset TTL.

```python
await client.touch(key, val=300)
```

### `async increment(key, bin, offset, meta=None, policy=None)`

Increment a bin value.

```python
await client.increment(key, "counter", 1)
```

## String / Numeric Operations

### `async append(key, bin, val, meta=None, policy=None)`

Append string to a bin.

```python
await client.append(key, "name", "_suffix")
```

### `async prepend(key, bin, val, meta=None, policy=None)`

Prepend string to a bin.

```python
await client.prepend(key, "name", "prefix_")
```

### `async remove_bin(key, bin_names, meta=None, policy=None)`

Remove specific bins from a record.

```python
await client.remove_bin(key, ["temp_bin", "debug_bin"])
```

## Multi-Operation

### `async operate(key, ops, meta=None, policy=None)`

Execute multiple operations atomically.

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = await client.operate(key, ops)
```

### `async operate_ordered(key, ops, meta=None, policy=None)`

Same as `operate` but returns results as an ordered list of `(bin, value)` tuples.

```python
_, meta, results = await client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

## Batch Operations

### `async get_many(keys, policy=None)`

Read multiple records concurrently.

```python
keys = [("test", "demo", f"user{i}") for i in range(10)]
records = await client.get_many(keys)
```

### `async exists_many(keys, policy=None)`

Check existence of multiple records.

```python
results = await client.exists_many(keys)
```

### `async select_many(keys, bins, policy=None)`

Read specific bins from multiple records.

```python
records = await client.select_many(keys, ["name", "age"])
```

### `async batch_operate(keys, ops, policy=None)`

Execute operations on multiple records.

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = await client.batch_operate(keys, ops)
```

### `async batch_remove(keys, policy=None)`

Delete multiple records.

```python
await client.batch_remove(keys)
```

## Scan

### `async scan(namespace, set_name, policy=None)`

Scan all records in a namespace/set.

```python
records = await client.scan("test", "demo")
for key, meta, bins in records:
    print(bins)
```

## Truncate

### `async truncate(namespace, set_name, nanos=0, policy=None)`

Remove all records in a namespace/set.

```python
await client.truncate("test", "demo")
```

## UDF

### `async udf_put(filename, udf_type=0, policy=None)`

Register a Lua UDF module.

```python
await client.udf_put("my_udf.lua")
```

### `async udf_remove(module, policy=None)`

Remove a UDF module.

```python
await client.udf_remove("my_udf")
```

### `async apply(key, module, function, args=None, policy=None)`

Execute a UDF on a record.

```python
result = await client.apply(key, "my_udf", "my_function", [1, "hello"])
```

## Concurrency Patterns

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

## Index Management

### `async index_integer_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a numeric secondary index.

```python
await client.index_integer_create("test", "demo", "age", "age_idx")
```

### `async index_string_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a string secondary index.

```python
await client.index_string_create("test", "demo", "name", "name_idx")
```

### `async index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a geospatial secondary index.

```python
await client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

### `async index_remove(namespace, index_name, policy=None)`

Remove a secondary index.

```python
await client.index_remove("test", "age_idx")
```

## Admin Operations

### User Management

| Method | Description |
|--------|-------------|
| `async admin_create_user(username, password, roles)` | Create a user |
| `async admin_drop_user(username)` | Delete a user |
| `async admin_change_password(username, password)` | Change password |
| `async admin_grant_roles(username, roles)` | Grant roles |
| `async admin_revoke_roles(username, roles)` | Revoke roles |
| `async admin_query_user(username)` | Get user info |
| `async admin_query_users()` | List all users |

### Role Management

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

# Query users
users = await client.admin_query_users()
```

## Expression Filters

All read/write/batch/scan operations that accept a `policy` parameter support the `filter_expression` key for server-side filtering:

```python
from aerospike_py import exp

expr = exp.ge(exp.int_bin("age"), exp.int_val(21))

# Get with filter
_, _, bins = await client.get(key, policy={"filter_expression": expr})

# Scan with filter
records = await client.scan("test", "demo", policy={"filter_expression": expr})

# Batch with filter
records = await client.get_many(keys, policy={"filter_expression": expr})
```

See the [Expression Filters Guide](../guides/expression-filters.md) for detailed documentation.
