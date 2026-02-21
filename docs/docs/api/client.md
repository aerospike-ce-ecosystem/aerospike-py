---
title: Client
sidebar_label: Client (Sync & Async)
sidebar_position: 1
description: Complete API reference for the synchronous Client and asynchronous AsyncClient classes.
---

<!-- AUTO-GENERATED from .pyi docstrings. Do not edit manually. -->

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

aerospike-py provides both synchronous (`Client`) and asynchronous (`AsyncClient`) APIs with identical functionality.

## Factory Functions

### `client(config)`

Create a new Aerospike client instance.

| Parameter | Description |
|-----------|-------------|
| `config` | [`ClientConfig`](types.md#clientconfig) dictionary. Must contain a ``"hosts"`` key with a list of ``(host, port)`` tuples. |

**Returns:** A new ``Client`` instance (not yet connected).

```python
import aerospike_py

client = aerospike_py.client({
    "hosts": [("127.0.0.1", 3000)],
}).connect()
```

### `set_log_level(level)`

Set the aerospike_py log level.

Accepts ``LOG_LEVEL_*`` constants. Controls both Rust-internal
and Python-side logging.

| Parameter | Description |
|-----------|-------------|
| `level` | One of ``LOG_LEVEL_OFF`` (-1), ``LOG_LEVEL_ERROR`` (0), ``LOG_LEVEL_WARN`` (1), ``LOG_LEVEL_INFO`` (2), ``LOG_LEVEL_DEBUG`` (3), ``LOG_LEVEL_TRACE`` (4). |

```python
import aerospike_py

aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)
```

### `get_metrics()`

Return collected metrics in Prometheus text format.

**Returns:** A string in Prometheus exposition format.

```python
print(aerospike_py.get_metrics())
```

### `start_metrics_server(port=9464)`

Start a background HTTP server serving ``/metrics`` for Prometheus.

| Parameter | Description |
|-----------|-------------|
| `port` | TCP port to listen on (default ``9464``). |

```python
aerospike_py.start_metrics_server(port=9464)
```

### `stop_metrics_server()`

Stop the background metrics HTTP server.

```python
aerospike_py.stop_metrics_server()
```

## Connection

### `connect(username=None, password=None)`

Connect to the Aerospike cluster.

Returns ``self`` for method chaining.

| Parameter | Description |
|-----------|-------------|
| `username` | Optional username for authentication. |
| `password` | Optional password for authentication. |

**Returns:** The connected client instance.

:::note

Raises `ClusterError` Failed to connect to any cluster node.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client = aerospike_py.client(config).connect()

# With authentication
client = aerospike_py.client(config).connect("admin", "admin")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
client = await aerospike_py.AsyncClient(config).connect()
await client.connect("admin", "admin")
```

  </TabItem>
</Tabs>

### `is_connected()`

Check whether the client is connected to the cluster.

**Returns:** ``True`` if the client has an active cluster connection.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
if client.is_connected():
    print("Connected")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
if client.is_connected():
    print("Connected")
```

  </TabItem>
</Tabs>

### `close()`

Close the connection to the cluster.

After calling this method the client can no longer be used for
database operations.

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

Return the names of all nodes in the cluster.

**Returns:** A list of node name strings.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
nodes = client.get_node_names()
# ['BB9020011AC4202', 'BB9030011AC4202']
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
nodes = await client.get_node_names()
```

  </TabItem>
</Tabs>

## Info

### `info_all(command, policy=None)`

Send an info command to all cluster nodes.

| Parameter | Description |
|-----------|-------------|
| `command` | The info command string (e.g. ``"namespaces"``). |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

**Returns:** A list of ``InfoNodeResult(node_name, error_code, response)`` tuples.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
results = client.info_all("namespaces")
for node, err, response in results:
    print(f"{node}: {response}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
results = await client.info_all("namespaces")
for node, err, response in results:
    print(f"{node}: {response}")
```

  </TabItem>
</Tabs>

### `info_random_node(command, policy=None)`

Send an info command to a random cluster node.

| Parameter | Description |
|-----------|-------------|
| `command` | The info command string. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

**Returns:** The info response string.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
response = client.info_random_node("build")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
response = await client.info_random_node("build")
```

  </TabItem>
</Tabs>

## CRUD Operations

### `put(key, bins, meta=None, policy=None)`

Write a record to the Aerospike cluster.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bins` | Dictionary of bin name-value pairs to write. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict (e.g. ``{"ttl": 300}``). |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

:::note

Raises `RecordExistsError` Record already exists (with CREATE_ONLY policy).

:::

:::note

Raises `RecordTooBig` Record size exceeds the configured write-block-size.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})

# With TTL (seconds)
client.put(key, {"score": 100}, meta={"ttl": 300})

# Create only (fail if exists)
import aerospike_py
client.put(
    key,
    {"x": 1},
    policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
key = ("test", "demo", "user1")
await client.put(key, {"name": "Alice", "age": 30})

# With TTL (seconds)
await client.put(key, {"score": 100}, meta={"ttl": 300})
```

  </TabItem>
</Tabs>

### `get(key, policy=None)`

Read a record from the cluster.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `policy` | Optional [`ReadPolicy`](types.md#readpolicy) dict. |

**Returns:** A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

:::note

Raises `RecordNotFound` The record does not exist.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
record = client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice", "age": 30}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
record = await client.get(("test", "demo", "user1"))
print(record.bins)  # {"name": "Alice", "age": 30}
```

  </TabItem>
</Tabs>

### `select(key, bins, policy=None)`

Read specific bins from a record.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bins` | List of bin names to retrieve. |
| `policy` | Optional [`ReadPolicy`](types.md#readpolicy) dict. |

**Returns:** A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

:::note

Raises `RecordNotFound` The record does not exist.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
record = client.select(("test", "demo", "user1"), ["name"])
# record.bins = {"name": "Alice"}
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
record = await client.select(("test", "demo", "user1"), ["name"])
# record.bins = {"name": "Alice"}
```

  </TabItem>
</Tabs>

### `exists(key, policy=None)`

Check whether a record exists.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `policy` | Optional [`ReadPolicy`](types.md#readpolicy) dict. |

**Returns:** An ``ExistsResult`` NamedTuple with ``key``, ``meta`` fields.
    ``meta`` is ``None`` if the record does not exist.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
result = client.exists(("test", "demo", "user1"))
if result.meta is not None:
    print(f"Found, gen={result.meta.gen}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
result = await client.exists(("test", "demo", "user1"))
if result.meta is not None:
    print(f"Found, gen={result.meta.gen}")
```

  </TabItem>
</Tabs>

### `remove(key, meta=None, policy=None)`

Delete a record from the cluster.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict for generation check. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

:::note

Raises `RecordNotFound` The record does not exist.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove(("test", "demo", "user1"))

# With generation check
import aerospike_py
client.remove(
    key,
    meta={"gen": 3},
    policy={"gen": aerospike_py.POLICY_GEN_EQ},
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove(("test", "demo", "user1"))
```

  </TabItem>
</Tabs>

### `touch(key, val=0, meta=None, policy=None)`

Reset the TTL of a record.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `val` | New TTL value in seconds. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

:::note

Raises `RecordNotFound` The record does not exist.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.touch(("test", "demo", "user1"), val=300)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.touch(("test", "demo", "user1"), val=300)
```

  </TabItem>
</Tabs>

## String / Numeric Operations

### `append(key, bin, val, meta=None, policy=None)`

Append a string to a bin value.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bin` | Target bin name. |
| `val` | String value to append. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.append(("test", "demo", "user1"), "name", "_suffix")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.append(("test", "demo", "user1"), "name", "_suffix")
```

  </TabItem>
</Tabs>

### `prepend(key, bin, val, meta=None, policy=None)`

Prepend a string to a bin value.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bin` | Target bin name. |
| `val` | String value to prepend. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.prepend(("test", "demo", "user1"), "name", "prefix_")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.prepend(("test", "demo", "user1"), "name", "prefix_")
```

  </TabItem>
</Tabs>

### `increment(key, bin, offset, meta=None, policy=None)`

Increment a numeric bin value.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bin` | Target bin name. |
| `offset` | Integer or float amount to add (use negative to decrement). |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.increment(("test", "demo", "user1"), "age", 1)
client.increment(("test", "demo", "user1"), "score", 0.5)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.increment(("test", "demo", "user1"), "age", 1)
await client.increment(("test", "demo", "user1"), "score", 0.5)
```

  </TabItem>
</Tabs>

### `remove_bin(key, bin_names, meta=None, policy=None)`

Remove specific bins from a record by setting them to nil.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `bin_names` | List of bin names to remove. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.remove_bin(("test", "demo", "user1"), ["temp_bin", "debug_bin"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.remove_bin(("test", "demo", "user1"), ["temp_bin"])
```

  </TabItem>
</Tabs>

## Multi-Operation

### `operate(key, ops, meta=None, policy=None)`

Execute multiple operations atomically on a single record.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `ops` | List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

**Returns:** A ``Record`` NamedTuple with ``key``, ``meta``, ``bins`` fields.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py

ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record = client.operate(("test", "demo", "key1"), ops)
print(record.bins)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py

ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record = await client.operate(("test", "demo", "key1"), ops)
print(record.bins)
```

  </TabItem>
</Tabs>

### `operate_ordered(key, ops, meta=None, policy=None)`

Execute multiple operations with ordered results.

Like ``operate()`` but returns results as an ordered list preserving
the operation order.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `ops` | List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys. |
| `meta` | Optional [`WriteMeta`](types.md#writemeta) dict. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

**Returns:** An ``OperateOrderedResult`` NamedTuple with ``key``, ``meta``,
    ``ordered_bins`` fields.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py

ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
result = client.operate_ordered(("test", "demo", "key1"), ops)
# result.ordered_bins = [BinTuple("counter", 2)]
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py

ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
result = await client.operate_ordered(
    ("test", "demo", "key1"), ops
)
# result.ordered_bins = [BinTuple("counter", 2)]
```

  </TabItem>
</Tabs>

## Batch Operations

### `batch_read(keys, bins=None, policy=None, _dtype=None)`

Read multiple records in a single batch call.

| Parameter | Description |
|-----------|-------------|
| `keys` | List of ``(namespace, set, primary_key)`` tuples. |
| `bins` | Optional list of bin names to read. ``None`` reads all bins; an empty list performs an existence check only. |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |
| `_dtype` | Optional NumPy dtype. When provided, returns ``NumpyBatchRecords`` instead of ``BatchRecords``. |

**Returns:** ``BatchRecords`` (or ``NumpyBatchRecords`` when ``_dtype`` is set).

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.record:
        print(br.record.bins)

# Read specific bins
batch = client.batch_read(keys, bins=["name", "age"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]
batch = await client.batch_read(keys, bins=["name", "age"])
for br in batch.batch_records:
    if br.record:
        print(br.record.bins)
```

  </TabItem>
</Tabs>

### `batch_operate(keys, ops, policy=None)`

Execute operations on multiple records in a single batch call.

| Parameter | Description |
|-----------|-------------|
| `keys` | List of ``(namespace, set, primary_key)`` tuples. |
| `ops` | List of operation dicts to apply to each record. |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |

**Returns:** A list of ``Record`` NamedTuples.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py

keys = [("test", "demo", f"user_{i}") for i in range(10)]
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py

keys = [("test", "demo", f"user_{i}") for i in range(10)]
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results = await client.batch_operate(keys, ops)
```

  </TabItem>
</Tabs>

### `batch_remove(keys, policy=None)`

Delete multiple records in a single batch call.

| Parameter | Description |
|-----------|-------------|
| `keys` | List of ``(namespace, set, primary_key)`` tuples. |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |

**Returns:** A list of ``Record`` NamedTuples.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]
results = client.batch_remove(keys)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]
results = await client.batch_remove(keys)
```

  </TabItem>
</Tabs>

## Query & Scan

### `query(namespace, set_name)`

Create a Query object for secondary index queries.

| Parameter | Description |
|-----------|-------------|
| `namespace` | The namespace to query. |
| `set_name` | The set to query. |

**Returns:** A ``Query`` object. Use ``where()`` to set a predicate filter
    and ``results()`` or ``foreach()`` to execute.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
query = client.query("test", "demo")
query.where(predicates.between("age", 20, 30))
records = await query.results()
```

  </TabItem>
</Tabs>

## Index Management

### `index_integer_create(namespace, set_name, bin_name, index_name, policy=None)`

Create a numeric secondary index.

| Parameter | Description |
|-----------|-------------|
| `namespace` | Target namespace. |
| `set_name` | Target set. |
| `bin_name` | Bin to index. |
| `index_name` | Name for the new index. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

:::note

Raises `IndexFoundError` An index with that name already exists.

:::

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

| Parameter | Description |
|-----------|-------------|
| `namespace` | Target namespace. |
| `set_name` | Target set. |
| `bin_name` | Bin to index. |
| `index_name` | Name for the new index. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

:::note

Raises `IndexFoundError` An index with that name already exists.

:::

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

| Parameter | Description |
|-----------|-------------|
| `namespace` | Target namespace. |
| `set_name` | Target set. |
| `bin_name` | Bin to index (must contain GeoJSON values). |
| `index_name` | Name for the new index. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

:::note

Raises `IndexFoundError` An index with that name already exists.

:::

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
client.index_geo2dsphere_create("test", "demo", "location", "geo_idx")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
await client.index_geo2dsphere_create(
    "test", "demo", "location", "geo_idx"
)
```

  </TabItem>
</Tabs>

### `index_remove(namespace, index_name, policy=None)`

Remove a secondary index.

| Parameter | Description |
|-----------|-------------|
| `namespace` | Target namespace. |
| `index_name` | Name of the index to remove. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

:::note

Raises `IndexNotFound` The index does not exist.

:::

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

| Parameter | Description |
|-----------|-------------|
| `namespace` | Target namespace. |
| `set_name` | Target set. |
| `nanos` | Optional last-update cutoff in nanoseconds. |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

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

Register a Lua UDF module on the cluster.

| Parameter | Description |
|-----------|-------------|
| `filename` | Path to the Lua source file. |
| `udf_type` | UDF language type (only Lua ``0`` is supported). |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

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

| Parameter | Description |
|-----------|-------------|
| `module` | Module name to remove (without ``.lua`` extension). |
| `policy` | Optional [`AdminPolicy`](types.md#adminpolicy) dict. |

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

Execute a UDF on a single record.

| Parameter | Description |
|-----------|-------------|
| `key` | Record key as ``(namespace, set, primary_key)`` tuple. |
| `module` | Name of the registered UDF module. |
| `function` | Name of the function within the module. |
| `args` | Optional list of arguments to pass to the function. |
| `policy` | Optional [`WritePolicy`](types.md#writepolicy) dict. |

**Returns:** The return value of the UDF function.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
result = client.apply(
    ("test", "demo", "key1"),
    "my_udf",
    "my_function",
    [1, "hello"],
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
result = await client.apply(
    ("test", "demo", "key1"),
    "my_udf",
    "my_function",
    [1, "hello"],
)
```

  </TabItem>
</Tabs>

## Query Object

Secondary index query object.

Created via ``Client.query(namespace, set_name)``. Use ``where()``
to set a predicate filter, ``select()`` to choose bins, then
``results()`` or ``foreach()`` to execute.

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()
```

### `select()`

Select specific bins to return in query results.

```python
query = client.query("test", "demo")
query.select("name", "age")
```

### `where(predicate)`

Set a predicate filter for the query.

Requires a matching secondary index on the filtered bin.

| Parameter | Description |
|-----------|-------------|
| `predicate` | A predicate tuple created by ``aerospike_py.predicates`` helper functions. |

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.where(predicates.equals("name", "Alice"))
```

### `results(policy=None)`

Execute the query and return all matching records.

| Parameter | Description |
|-----------|-------------|
| `policy` | Optional [`QueryPolicy`](types.md#querypolicy) dict. |

**Returns:** A list of ``Record`` NamedTuples.

```python
records = query.results()
for record in records:
    print(record.bins)
```

### `foreach(callback, policy=None)`

Execute the query and invoke a callback for each record.

The callback receives a ``Record`` NamedTuple. Return ``False``
from the callback to stop iteration early.

| Parameter | Description |
|-----------|-------------|
| `callback` | Function called with each record. Return ``False`` to stop. |
| `policy` | Optional [`QueryPolicy`](types.md#querypolicy) dict. |

```python
def process(record):
    print(record.bins)

query.foreach(process)
```
