# Client (Sync)

The synchronous `Client` class wraps the Rust native client with a Python-friendly API.

## Creating a Client

```python
import aerospike_py as aerospike

client = aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect()
```

## Context Manager

`Client` supports the context manager protocol (`with` statement):

### `__enter__()` / `__exit__()`

```python
with aerospike.client({
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}).connect() as client:
    client.put(key, bins)
# close() is called automatically on exit
```

## Connection

### `connect(username=None, password=None)`

Connect to the Aerospike cluster. Returns `self` for method chaining.

```python
client = aerospike.client(config).connect()
# With authentication
client = aerospike.client(config).connect("admin", "admin")
```

### `is_connected()`

Returns `True` if the client is connected.

```python
if client.is_connected():
    print("Connected")
```

### `close()`

Close the connection to the cluster.

```python
client.close()
```

### `get_node_names()`

Returns a list of cluster node names.

```python
nodes = client.get_node_names()
# ['BB9...']
```

## CRUD Operations

### `put(key, bins, meta=None, policy=None)`

Write a record.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `tuple[str, str, str\|int\|bytes]` | `(namespace, set, pk)` |
| `bins` | `dict[str, Any]` | Bin name-value pairs |
| `meta` | `dict` | Optional: `{"ttl": int, "gen": int}` |
| `policy` | `dict` | Optional: `{"key", "exists", "gen", "timeout", ...}` |

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"x": 1}, meta={"ttl": 300})
client.put(key, {"x": 1}, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
```

### `get(key, policy=None)`

Read a record. Returns `(key, meta, bins)`.

```python
key, meta, bins = client.get(("test", "demo", "user1"))
# meta = {"gen": 1, "ttl": 2591998}
# bins = {"name": "Alice", "age": 30}
```

!!! note
    Raises `RecordNotFound` if the record does not exist.

### `select(key, bins, policy=None)`

Read specific bins from a record.

```python
_, meta, bins = client.select(key, ["name"])
# bins = {"name": "Alice"}
```

### `exists(key, policy=None)`

Check if a record exists. Returns `(key, meta)` where `meta` is `None` if not found.

```python
_, meta = client.exists(key)
if meta is not None:
    print(f"Found, gen={meta['gen']}")
```

### `remove(key, meta=None, policy=None)`

Delete a record.

```python
client.remove(key)
# With generation check
client.remove(key, meta={"gen": 3}, policy={"gen": aerospike.POLICY_GEN_EQ})
```

### `touch(key, val=0, meta=None, policy=None)`

Reset TTL for a record.

```python
client.touch(key, val=300)
```

## String / Numeric Operations

### `append(key, bin, val, meta=None, policy=None)`

Append string to a bin.

```python
client.append(key, "name", "_suffix")
```

### `prepend(key, bin, val, meta=None, policy=None)`

Prepend string to a bin.

```python
client.prepend(key, "name", "prefix_")
```

### `increment(key, bin, offset, meta=None, policy=None)`

Increment integer or float bin value.

```python
client.increment(key, "age", 1)
client.increment(key, "score", 0.5)
```

### `remove_bin(key, bin_names, meta=None, policy=None)`

Remove specific bins from a record.

```python
client.remove_bin(key, ["temp_bin", "debug_bin"])
```

## Multi-Operation

### `operate(key, ops, meta=None, policy=None)`

Execute multiple operations atomically on a single record.

```python
ops = [
    {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": None},
]
_, meta, bins = client.operate(key, ops)
```

### `operate_ordered(key, ops, meta=None, policy=None)`

Same as `operate` but returns results as an ordered list of `(bin, value)` tuples.

```python
_, meta, results = client.operate_ordered(key, ops)
# results = [("counter", 2)]
```

## Batch Operations

### `get_many(keys, policy=None)`

Read multiple records. Returns `list[Record]`.

```python
keys = [("test", "demo", f"user{i}") for i in range(10)]
records = client.get_many(keys)
for key, meta, bins in records:
    print(bins)
```

### `exists_many(keys, policy=None)`

Check existence of multiple records. Returns `list[(key, meta)]`.

```python
results = client.exists_many(keys)
for key, meta in results:
    print("exists" if meta else "not found")
```

### `select_many(keys, bins, policy=None)`

Read specific bins from multiple records.

```python
records = client.select_many(keys, ["name", "age"])
```

### `batch_operate(keys, ops, policy=None)`

Execute operations on multiple records.

```python
ops = [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
```

### `batch_remove(keys, policy=None)`

Delete multiple records.

```python
results = client.batch_remove(keys)
```

## Query & Scan

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

## Index Management

### `index_integer_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a numeric secondary index.

```python
client.index_integer_create("test", "demo", "age", "age_idx")
```

### `index_string_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a string secondary index.

```python
client.index_string_create("test", "demo", "name", "name_idx")
```

### `index_geo2dsphere_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a geospatial secondary index.

```python
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

### `index_remove(namespace, index_name, policy=None)`

Remove a secondary index.

```python
client.index_remove("test", "age_idx")
```

## Truncate

### `truncate(namespace, set_name, nanos=0, policy=None)`

Remove all records in a namespace/set.

```python
client.truncate("test", "demo")
```

## UDF

### `udf_put(filename, udf_type=0, policy=None)`

Register a Lua UDF module.

```python
client.udf_put("my_udf.lua")
```

### `udf_remove(module, policy=None)`

Remove a registered UDF module.

```python
client.udf_remove("my_udf")
```

### `apply(key, module, function, args=None, policy=None)`

Execute a UDF on a record.

```python
result = client.apply(key, "my_udf", "my_function", [1, "hello"])
```

## Admin Operations

### User Management

| Method | Description |
|--------|-------------|
| `admin_create_user(username, password, roles)` | Create a user |
| `admin_drop_user(username)` | Delete a user |
| `admin_change_password(username, password)` | Change password |
| `admin_grant_roles(username, roles)` | Grant roles |
| `admin_revoke_roles(username, roles)` | Revoke roles |
| `admin_query_user(username)` | Get user info |
| `admin_query_users()` | List all users |

### Role Management

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

## Expression Filters

All read/write/batch operations that accept a `policy` parameter support the `filter_expression` key for server-side filtering (requires Server 5.2+):

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
records = client.get_many(keys, policy={"filter_expression": expr})
```

!!! tip
    If a record does not match the filter expression, the operation raises `FilteredOut`.
    See the [Expression Filters Guide](../guides/expression-filters.md) for detailed documentation.
