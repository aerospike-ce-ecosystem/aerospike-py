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

### `async_client(config)`

Create a new async Aerospike client instance.

| Parameter | Description |
|-----------|-------------|
| `config` | [`ClientConfig`](types.md#clientconfig) dictionary. Must contain a ``"hosts"`` key with a list of ``(host, port)`` tuples. |

**Returns:** A new ``AsyncClient`` instance (not yet connected).

```python
import aerospike_py

client = aerospike_py.async_client({
    "hosts": [("127.0.0.1", 3000)],
})
await client.connect()
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
# Without authentication
client = await aerospike_py.AsyncClient(config).connect()

# With authentication
client = await aerospike_py.AsyncClient(config).connect("admin", "admin")
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

### `ping()`

Lightweight health check that verifies cluster liveness.

Sends an ``info("build")`` command to a random cluster node and
returns whether the node responded successfully. Unlike
``is_connected()`` which only checks local state, this method
performs an actual network round-trip.

Useful for Kubernetes readiness probes, load-balancer health
checks, and connection-pool validation.

**Returns:** ``True`` if a cluster node responded, ``False`` otherwise
(including when the client is not connected).

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
if client.ping():
    print("Cluster is reachable")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
if await client.ping():
    print("Cluster is reachable")
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
nodes = client.get_node_names()
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
| `ops` | List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys. For an ``OPERATOR_INCR`` op the ``"val"`` must be an ``int`` or ``float`` (a non-numeric ``val`` raises ``TypeError``). |
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
| `ops` | List of operation dicts with ``"op"``, ``"bin"``, ``"val"`` keys. For an ``OPERATOR_INCR`` op the ``"val"`` must be an ``int`` or ``float`` (a non-numeric ``val`` raises ``TypeError``). |
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

### `batch_read(keys, bins=None, policy=None)`

Read multiple records in a single batch call.

Returns a [`LazyBatchRecords`](types.md#lazybatchrecords) — a zero-conversion
wrapper around the raw Rust results. Call one of the handle methods
to materialise the result:

* ``lazy_records.to_dict()`` → ``dict[UserKey, AerospikeRecord]``
* ``lazy_records.to_numpy(dtype)`` → ``NumpyBatchRecords`` (GIL released
  during the structured-array fill — ideal for FastAPI/PyTorch
  inference workers)
* ``lazy_records.batch_records`` → ``list[BatchRecord]`` (compat)

| Parameter | Description |
|-----------|-------------|
| `keys` | List of ``(namespace, set, primary_key)`` tuples. |
| `bins` | Optional list of bin names to read. ``None`` reads all bins; an empty list performs an existence check only. |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |

**Returns:** ``LazyBatchRecords``.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]
lazy_records = client.batch_read(keys, bins=["name", "age"])
for user_key, bins_dict in lazy_records.to_dict().items():
    print(user_key, bins_dict)

# numpy/torch path
np_batch = lazy_records.to_numpy(dtype)
tensor = torch.from_numpy(np_batch.batch_records["score"])
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]
lazy_records = await client.batch_read(keys, bins=["name", "age"])
for user_key, bins_dict in lazy_records.to_dict().items():
    print(user_key, bins_dict)
```

  </TabItem>
</Tabs>

### `batch_write(records, policy=None, retry=0)`

Write multiple records with per-record bins in a single batch call.

Each record is a ``(key, bins)`` or ``(key, bins, meta)`` tuple where
key is ``(namespace, set, primary_key)``, bins is a dict of bin
name-to-value mappings, and meta is an optional
[`WriteMeta`](types.md#writemeta) dict (e.g. ``{"ttl": 300}``).
Unlike ``batch_operate`` (which applies the same operations to all
keys), each record can have different bins.

Write fields can be set at two levels and follow a uniform precedence
rule — **per-record meta always overrides the batch-level policy**.
The fields below mirror the corresponding [`WritePolicy`](types.md#writepolicy)
keys used by `put()`:

| Field            | Batch-level (``policy``) | Per-record (``meta``) | Notes                                            |
|------------------|--------------------------|-----------------------|--------------------------------------------------|
| ``ttl``          | ✅                       | ✅                    | Seconds, or ``TTL_NEVER_EXPIRE`` / ``TTL_DONT_UPDATE``. |
| ``key``          | ✅                       | ✅                    | ``POLICY_KEY_DIGEST`` (default) / ``POLICY_KEY_SEND``. |
| ``exists``       | ✅                       | ✅                    | ``POLICY_EXISTS_*`` (UPDATE / CREATE_ONLY / etc.). |
| ``gen``          | ✅ (enum index)          | ✅ (expected value)   | Batch-level: ``POLICY_GEN_*``. Per-record: int forces ``POLICY_GEN_EQ`` with this generation. |
| ``commit_level`` | ✅                       | ✅                    | ``POLICY_COMMIT_LEVEL_ALL`` (default) / ``_MASTER``. |
| ``durable_delete`` | ✅                     | ✅                    | EE 3.10+ tombstone semantics.                    |

| Parameter | Description |
|-----------|-------------|
| `records` | List of ``(key, bins)`` or ``(key, bins, meta)`` tuples. |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. Accepts the write fields above plus standard batch transport keys (``socket_timeout``, ``total_timeout``, ``max_retries``, ``filter_expression``, ``allow_inline``, ``allow_inline_ssd``, ``respond_all_keys``). |
| `retry` | Maximum number of retries for failed records (default ``0``). When > 0, records that fail with transient errors (timeout, device overload, key busy) are automatically retried with exponential backoff (Full Jitter, max 500ms). Retries stop early if the elapsed time approaches ``total_timeout``. **Note:** If a transport error occurs during retry, retries stop and partial results are returned. Always check each ``BatchRecord.result`` code. Total wall-clock time may exceed ``total_timeout`` by up to one additional timeout window. |

**Returns:** A ``BatchWriteResult`` containing per-record result codes in
``batch_records: list[BatchRecord]``.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
# Basic usage
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]
results = client.batch_write(records)

# With batch-level TTL (30 days)
results = client.batch_write(records, policy={"ttl": 2592000})

# With per-record TTL
records_with_ttl = [
    (("test", "demo", "user1"), {"name": "Alice"}, {"ttl": 3600}),
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 86400}),
]
results = client.batch_write(records_with_ttl)

# Persist user keys server-side (POLICY_KEY_SEND) — visible via
# ``scan`` / ``query`` / ``aql SELECT *``.
results = client.batch_write(
    records,
    policy={"key": aerospike_py.POLICY_KEY_SEND},
)

# Mix per-record overrides: only ``user1`` stores its key.
results = client.batch_write([
    (("test", "demo", "user1"), {"name": "Alice"},
     {"key": aerospike_py.POLICY_KEY_SEND}),
    (("test", "demo", "user2"), {"name": "Bob"}),
])

# CREATE_ONLY semantics — fail per-record if it already exists.
results = client.batch_write(
    records,
    policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]
results = await client.batch_write(records)

# Persist user keys server-side
results = await client.batch_write(
    records,
    policy={"key": aerospike_py.POLICY_KEY_SEND},
)

# Per-record overrides
records_with_meta = [
    (("test", "demo", "user1"), {"name": "Alice"},
     {"ttl": 3600, "key": aerospike_py.POLICY_KEY_SEND}),
    (("test", "demo", "user2"), {"name": "Bob"}, {"ttl": 86400}),
]
results = await client.batch_write(records_with_meta)
```

  </TabItem>
</Tabs>

### `batch_write_numpy(data, namespace, set_name, _dtype, key_field='_key', policy=None, retry=0)`

Write multiple records from a numpy structured array.

Each row of the structured array becomes a separate write operation.
The dtype must contain a key field (default ``_key``) for the record key.
Remaining non-underscore-prefixed fields become bins.

| Parameter | Description |
|-----------|-------------|
| `data` | numpy structured array with record data. |
| `namespace` | Target namespace. |
| `set_name` | Target set. |
| `_dtype` | numpy dtype describing the array layout. |
| `key_field` | Name of the dtype field to use as the user key (default ``"_key"``). |
| `policy` | Optional [`BatchPolicy`](types.md#batchpolicy) dict. |
| `retry` | Maximum number of retries for failed records (default ``0``). When > 0, records that fail with transient errors (timeout, device overload, key busy) are automatically retried with exponential backoff (Full Jitter, max 500ms). Retries stop early if the elapsed time approaches ``total_timeout``. **Note:** If a transport error occurs during retry, retries stop and partial results are returned. Always check each ``BatchRecord.result`` code. Total wall-clock time may exceed ``total_timeout`` by up to one additional timeout window. |

**Returns:** A ``BatchWriteResult`` with per-record result codes in
``batch_records: list[BatchRecord]``.

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import numpy as np

dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)
results = client.batch_write_numpy(data, "test", "demo", dtype, retry=10)
for br in results.batch_records:
    if br.result != 0:
        print(f"Failed: {br.key}, code={br.result}")
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import numpy as np

dtype = np.dtype([("_key", "i4"), ("score", "f8"), ("count", "i4")])
data = np.array([(1, 0.95, 10), (2, 0.87, 20)], dtype=dtype)
results = await client.batch_write_numpy(data, "test", "demo", dtype, retry=10)
for br in results.batch_records:
    if br.result != 0:
        print(f"Failed: {br.key}, code={br.result}")
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

**Returns:** A ``BatchWriteResult`` with per-record result codes in
``batch_records: list[BatchRecord]``.
Each ``BatchRecord`` also includes an ``in_doubt`` flag
(see `batch_write()` for details).

<Tabs>
  <TabItem value="sync" label="Sync Client" default>

```python
import aerospike_py

keys = [("test", "demo", f"user_{i}") for i in range(10)]
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results = client.batch_operate(keys, ops)
for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)
```

  </TabItem>
  <TabItem value="async" label="Async Client">

```python
import aerospike_py

keys = [("test", "demo", f"user_{i}") for i in range(10)]
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}]
results = await client.batch_operate(keys, ops)
for br in results.batch_records:
    if br.result == 0 and br.record is not None:
        print(br.record.bins)
```

  </TabItem>
</Tabs>

### `batch_remove(keys, policy=None)`

Delete multiple records in a single batch call.

| Parameter | Description |
|-----------|-------------|
| `keys` | Either a list of bare ``Key`` tuples (back-compat) or a list mixing bare keys and ``(key, meta)`` pairs where ``meta`` is a [`BatchDeleteMeta`](types.md#batchdeletemeta) dict for per-record overrides (CAS deletes, durable_delete per record, etc.). |
| `policy` | Optional dict combining a transport-level [`BatchPolicy`](types.md#batchpolicy) with batch-level [`BatchDeletePolicy`](types.md#batchdeletepolicy) defaults: ``gen``, ``key`` (send_key), ``commit_level``, ``durable_delete``, ``filter_expression``. |

**Returns:** A ``BatchWriteResult`` with per-record result codes in
``batch_records: list[BatchRecord]``.
Each ``BatchRecord`` also includes an ``in_doubt`` flag
(see `batch_write()` for details).

```python
# Legacy: bare keys.
keys = [("test", "demo", f"user_{i}") for i in range(10)]
results = client.batch_remove(keys)

# CAS delete: only delete user_1 if generation is still 3.
_, meta, _ = client.get(("test", "demo", "user_1"))
results = client.batch_remove([
    (("test", "demo", "user_1"), {"gen": meta.gen}),
    ("test", "demo", "user_2"),  # bare key, no CAS
])
```

### `batch_apply(keys, module, function, args=None, policy=None)`

Execute a UDF on multiple records in a single batch call.

| Parameter | Description |
|-----------|-------------|
| `keys` | Either a list of bare ``Key`` tuples or a list mixing bare keys and ``(key, meta)`` pairs where ``meta`` is a [`BatchUDFMeta`](types.md#batchudfmeta) flat dict that may override the UDF call shape (``module``, ``function``, ``args``) and policy fields (``ttl``, ``commit_level``, ``key``, ``durable_delete``) for that specific record. |
| `module` | Default UDF module to invoke when a record has no per-record ``module`` override. |
| `function` | Default UDF function name. |
| `args` | Optional default arguments. Per-record ``args`` in ``BatchUDFMeta`` (including ``[]`` for no args) overrides this default. |
| `policy` | Optional dict combining a transport-level [`BatchPolicy`](types.md#batchpolicy) with batch-level [`BatchUDFPolicy`](types.md#batchudfpolicy) defaults: ``commit_level``, ``ttl``, ``key`` (send_key), ``durable_delete``, ``filter_expression``. |

**Returns:** A ``BatchWriteResult`` with per-record result codes in
``batch_records: list[BatchRecord]``. UDF return values are
stored in the per-record bin map under the Lua-convention
``"SUCCESS"`` key when the call succeeded.

:::note

``batch_apply`` does **not** accept a ``retry`` parameter
(unlike `batch_write()`, which accepts ``retry: int = 0``).
Passing ``retry=`` to this method raises ``TypeError``.
UDF batches are not idempotent in the general case, so retries
must be driven by the caller. For per-record control over the
UDF call shape and policy fields, use ``(key, meta)`` tuples
with a ``BatchUDFMeta`` payload in ``keys``.

:::

```python
# Apply the same UDF to many keys.
keys = [("test", "demo", f"u_{i}") for i in range(10)]
results = client.batch_apply(keys, "test_udf", "add", [10, 20])

# Per-record overrides: different args for one record.
results = client.batch_apply(
    [
        ("test", "demo", "u_1"),  # uses default args
        (("test", "demo", "u_2"), {"args": [5, 5]}),
    ],
    "test_udf", "add", args=[1, 1],
)
```

## Query

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

## User Administration

### `admin_create_user(username, password, roles, policy=None)`

Create a user with the supplied password and roles.

### `admin_drop_user(username, policy=None)`

Delete a user.

### `admin_change_password(username, password, policy=None)`

Change a user's password.

### `admin_grant_roles(username, roles, policy=None)`

Grant roles to a user.

### `admin_revoke_roles(username, roles, policy=None)`

Revoke roles from a user.

### `admin_query_user_info(username, policy=None)`

Return information about one user.

### `admin_query_users_info(policy=None)`

Return information about all users.

## Role Administration

### `admin_create_role(role, privileges, policy=None, whitelist=None, read_quota=0, write_quota=0)`

Create a role with privileges and optional access limits.

### `admin_drop_role(role, policy=None)`

Delete a role.

### `admin_grant_privileges(role, privileges, policy=None)`

Grant privileges to a role.

### `admin_revoke_privileges(role, privileges, policy=None)`

Revoke privileges from a role.

### `admin_query_role(role, policy=None)`

Return information about one role.

### `admin_query_roles(policy=None)`

Return information about all roles.

### `admin_set_whitelist(role, whitelist, policy=None)`

Set the network allowlist for a role.

### `admin_set_quotas(role, read_quota=0, write_quota=0, policy=None)`

Set read and write quotas for a role.

## Query and AsyncQuery Objects

Secondary index query object.

Created via ``Client.query(namespace, set_name)``. Use ``where()``
to set a predicate filter, ``select()`` to choose bins, then
``results()`` or ``foreach()`` to execute.

<Tabs>
  <TabItem value="query" label="Query" default>

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = query.results()
```

  </TabItem>
  <TabItem value="async-query" label="AsyncQuery">

```python
from aerospike_py import predicates

query = client.query("test", "demo")
query.select("name", "age")
query.where(predicates.between("age", 20, 30))
records = await query.results()
```

  </TabItem>
</Tabs>

### `select(*bins)`

Select specific bins to return in query results.

| Parameter | Description |
|-----------|-------------|
| `*bins` | Bin names to include in the results. |

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

<Tabs>
  <TabItem value="sync" label="Query" default>

```python
records = query.results()
for record in records:
    print(record.bins)
```

  </TabItem>
  <TabItem value="async" label="AsyncQuery">

```python
records = await query.results()
for record in records:
    print(record.bins)
```

  </TabItem>
</Tabs>

### `foreach(callback, policy=None)`

Execute the query and invoke a callback for each record.

The callback receives a ``Record`` NamedTuple. Return ``False``
from the callback to stop iteration early.

| Parameter | Description |
|-----------|-------------|
| `callback` | Function called with each record. Return ``False`` to stop. |
| `policy` | Optional [`QueryPolicy`](types.md#querypolicy) dict. |

<Tabs>
  <TabItem value="sync" label="Query" default>

```python
def process(record):
    print(record.bins)

query.foreach(process)
```

  </TabItem>
  <TabItem value="async" label="AsyncQuery">

```python
def process(record):
    print(record.bins)

await query.foreach(process)
```

  </TabItem>
</Tabs>

## Partition Filter Helpers

### `partition_filter_all()`

Build a `PartitionFilter` covering all 4096 partitions.

Equivalent to omitting ``partition_filter`` from the policy entirely.

### `partition_filter_by_id(partition_id)`

Build a `PartitionFilter` targeting a single partition.

| Parameter | Description |
|-----------|-------------|
| `partition_id` | Partition index in ``[0, 4095]``. |

:::note

Raises `ValueError` If ``partition_id`` is outside the valid range.

:::

### `partition_filter_by_range(begin, count)`

Build a `PartitionFilter` targeting ``count`` partitions from ``begin``.

| Parameter | Description |
|-----------|-------------|
| `begin` | First partition (``[0, 4095]``). |
| `count` | Number of partitions; ``begin + count <= 4096``. ``0`` is allowed and yields an empty filter. |

:::note

Raises `ValueError` If the range overflows 4096.

:::

## Logging

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

### `dropped_log_count()`

Return the number of log messages dropped because the GIL was unavailable.

When the Rust logging bridge cannot acquire the Python GIL (e.g. during
interpreter shutdown), log messages are counted as dropped. WARN and ERROR
level messages are still emitted to stderr as a fallback.

**Returns:** Count of dropped messages since process start.

## Metrics

### `get_metrics()`

Return collected metrics in Prometheus text format.

**Returns:** A string in Prometheus exposition format.

```python
print(aerospike_py.get_metrics())
```

### `set_metrics_enabled(enabled)`

Enable or disable Prometheus metrics collection.

When disabled, operation timers are skipped entirely (~1ns atomic check).
Useful for benchmarking without metrics overhead.

| Parameter | Description |
|-----------|-------------|
| `enabled` | ``True`` to enable (default), ``False`` to disable. |

```python
aerospike_py.set_metrics_enabled(False)   # disable for benchmark
aerospike_py.set_metrics_enabled(True)     # re-enable
```

### `is_metrics_enabled()`

Check if Prometheus metrics collection is currently enabled.

**Returns:** ``True`` if metrics are enabled (default), ``False`` otherwise.

```python
if aerospike_py.is_metrics_enabled():
    print(aerospike_py.get_metrics())
```

### `set_internal_stage_metrics_enabled(enabled)`

Enable or disable internal stage profiling metrics.

Controls the ``db_client_internal_stage_seconds`` histogram that captures
fine-grained timing per batch_read stage. Disabled by default — zero
overhead when off. Set ``AEROSPIKE_PY_INTERNAL_METRICS=1`` to enable at
process start.

| Parameter | Description |
|-----------|-------------|
| `enabled` | ``True`` to enable, ``False`` to disable (default). |

### `is_internal_stage_metrics_enabled()`

Check if internal stage profiling metrics are currently enabled.

**Returns:** ``True`` if stage profiling is on, ``False`` otherwise (default).

### `internal_stage_profiling()`

Context manager that scopes internal stage profiling to a code block.

Enables profiling on entry and restores the previous state on exit.

```python
with aerospike_py.internal_stage_profiling():
    lazy_records = await client.batch_read(keys)
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

## Tracing

### `init_tracing()`

Initialize OpenTelemetry tracing.

Reads standard ``OTEL_*`` environment variables for configuration.

```python
aerospike_py.init_tracing()
```

### `shutdown_tracing()`

Shut down the tracer provider, flushing pending spans.

Call before process exit to ensure all spans are exported.

```python
aerospike_py.shutdown_tracing()
```
