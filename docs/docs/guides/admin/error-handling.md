---
title: Error Handling
sidebar_label: Error Handling
sidebar_position: 3
slug: /guides/error-handling
description: Production error handling patterns for aerospike-py.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Exception Hierarchy

All aerospike-py exceptions inherit from `AerospikeError`, which itself inherits from Python's built-in `Exception`:

```
Exception
└── AerospikeError                   # Base for all Aerospike errors
    ├── ClientError                  # Client-side (connection, config, internal)
    ├── ClusterError                 # Cluster connectivity / node errors
    ├── InvalidArgError              # Invalid argument passed to an operation
    ├── AerospikeTimeoutError        # Operation timed out
    ├── ServerError                  # Server-side errors
    │   ├── AerospikeIndexError      # Secondary index errors
    │   │   ├── IndexNotFound        # Index does not exist (201)
    │   │   └── IndexFoundError      # Index already exists (200)
    │   ├── QueryError               # Query execution error
    │   │   └── QueryAbortedError    # Query aborted by server (210)
    │   ├── AdminError               # Admin / security operation error
    │   └── UDFError                 # UDF execution error
    └── RecordError                  # Record-level errors
        ├── RecordNotFound           # Record does not exist (2)
        ├── RecordExistsError        # Record already exists (5)
        ├── RecordGenerationError    # Generation mismatch (3)
        ├── RecordTooBig             # Record exceeds size limit (13)
        ├── BinNameError             # Bin name too long (21)
        ├── BinExistsError           # Bin already exists (6)
        ├── BinNotFound              # Bin does not exist (17)
        ├── BinTypeError             # Bin type mismatch (12)
        └── FilteredOut              # Excluded by expression filter (27)
```

Import exceptions from `aerospike_py.exception`:

```python
from aerospike_py.exception import (
    AerospikeError,
    ClientError,
    ClusterError,
    AerospikeTimeoutError,
    RecordNotFound,
    RecordExistsError,
    RecordGenerationError,
)
```

## Basic Error Handling

Always catch specific exceptions before broader ones:

```python
from aerospike_py.exception import (
    RecordNotFound,
    AerospikeTimeoutError,
    ClusterError,
    AerospikeError,
)

try:
    record = client.get(key)
except RecordNotFound:
    # Handle missing record
    bins = {}
except AerospikeTimeoutError:
    # Retry or circuit-break
    raise
except ClusterError:
    # Connection lost -- reconnect or fail fast
    raise
except AerospikeError as e:
    # Catch-all for any other Aerospike errors
    logger.error("Aerospike error: %s", e)
    raise
```

## What an Exception Tells You

Every `AerospikeError` carries four attributes. Use them instead of the message text, which can change between releases.

| Attribute | Meaning |
|-----------|---------|
| `result_code` | The server's result code when a server answered (for example `2` record not found, `5` record exists, `100` UDF failed). `-1` when no server answered: a client timeout, a connection failure, an invalid argument. |
| `error_type` | The kind of failure, by name. A server code is named after the code (`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, ...; `"ServerTimeout"` for a timeout the server reported). Client-side failures are `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"` or `"Client"`. This is what tells the `-1` cases apart. |
| `in_doubt` | `True` when a write was sent and no definite answer came back, so the server may have applied it. `False` when the server answered with a failure (record exists, a failed UDF, ...), and always for reads. A write sent with `max_retries > 0` is the exception, see [Re-sent writes and `in_doubt`](#re-sent-writes-and-in_doubt). The exception of a batch call that failed as a whole is in doubt whenever any row of its `partial_result` is. |
| `partial_result` | For a batch call that failed as a whole: a `BatchWriteResult` with one row per requested record, in request order. `None` for every other failure. When the call failed on several nodes, the exception is the error of one of them (the first whose share failed); the rows say what happened to each record. |

```python
import aerospike_py

try:
    client.put(key, bins)
except aerospike_py.AerospikeError as exc:
    if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS:
        ...  # the server answered: the record is there
    elif exc.error_type == "Timeout" and exc.in_doubt:
        ...  # the write may be in; read the record before writing again
    else:
        raise
```

The Prometheus `error_type` label and the OpenTelemetry `error.type` attribute use the same names as `exc.error_type`, so a dashboard and an `except` clause classify a failure the same way.

## Batch Error Handling

Batch operations do not raise exceptions for individual record failures. Instead, each `BatchRecord` carries its own result code:

```python
keys = [("test", "demo", f"id-{i}") for i in range(100)]

# batch_read returns a `LazyBatchRecords`. Successful reads with
# a `user_key` populate the dict view; missing keys and per-record
# failures are filtered out (use `batch.batch_records` or
# `batch.iter_records()` if you need every entry, including failures).
batch = client.batch_read(keys)

# Succeeded records are in the dict view; missing keys are absent.
# The dict-like `.values()` / `.keys()` accessors are backed by a
# cached `to_dict()` materialisation, so no extra conversion is needed.
succeeded = list(batch.values())
all_user_keys = {k[2] for k in keys}
present_keys = set(batch.keys())
missing_keys = all_user_keys - present_keys

if missing_keys:
    logger.warning("Batch had %d missing keys", len(missing_keys))
```

For `batch_operate`, failures on individual keys do not abort the entire batch:

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_operate(keys, operations)
except AerospikeError:
    # Entire batch failed (e.g., cluster unavailable); see below
    raise

for br in results.batch_records:
    if br.result != 0:
        logger.warning("Key %s failed (code=%d, %s)", br.key, br.result, br.error_type)
```

### What Each Row Says

Every `BatchRecord` has `result`, `error_type` and `in_doubt`:

| Outcome | `result` | `error_type` | `in_doubt` |
|---------|----------|--------------|------------|
| Success | `0` | `None` | `False` |
| Record not found | `2` | `"KeyNotFoundError"` | `False` |
| Excluded by `filter_expression` | `27` | `"FilteredOut"` | `False` |
| Other failure the server reported | its code | named after the code | `False` |
| Server reported a timeout | `9` | `"ServerTimeout"` | `True` for a write |
| Request sent, the client stopped waiting | `-1` | `"Timeout"` | `True` for a write |
| Transport failure | `-1` | `"Connection"`, `"InvalidNode"`, ... | `True` for a write that had been sent |
| No node answered for the record | `-1` | `"NoResponse"` | `False` when nothing was sent for it (the key could not be routed). `True` for a write when the call gave up without its rows after it may have sent them |

`result` is `0` only when a server reported success for that record. A row is never counted as written because nothing came back.

A write the server refused with a code worth a retry, `KEY_BUSY` (14), `DEVICE_OVERLOAD` (18) or `PARTITION_UNAVAILABLE` (11), is an answer: the row carries that code with `in_doubt == False`, and the call returns normally, also for a batch of one key. A single-record write refused this way (`put()` on a hot key, for example) raises `ServerError` with that `result_code`, an `error_type` of `"KeyBusy"`, `"DeviceOverload"` or `"PartitionUnavailable"`, and `in_doubt == False`. A `PARTITION_UNAVAILABLE` row of a write batch sent with `max_retries > 0` can be in doubt; see [Re-sent writes and `in_doubt`](#re-sent-writes-and-in_doubt).

### When the Whole Batch Fails

A batch call that fails as a whole (for example, the node that owns some of the keys stops answering) raises an exception as before, and the exception carries the rows: `exc.partial_result` is a `BatchWriteResult` with one `BatchRecord` per requested record, in request order. Records that other nodes answered keep their results; the rest say why they have none. Every batch method sets it: `batch_read`, `batch_write`, `batch_write_numpy`, `batch_operate`, `batch_remove` and `batch_apply`.

The exception has `in_doubt == True` whenever any row of its `partial_result` is in doubt. When the call failed on several nodes, the exception is the error of one of them (the first whose share failed), so its type and `result_code` can differ with the order of the records. Decide from the rows, which say what happened to each record.

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_write(records)
except AerospikeError as exc:
    if exc.partial_result is None:
        raise  # refused before anything was attempted (e.g. a bad policy value)
    rows = exc.partial_result.batch_records
    written = [br.key for br in rows if br.result == 0]
    unsure = [br.key for br in rows if br.in_doubt]           # read before re-sending
    not_sent = [br.key for br in rows if br.error_type == "NoResponse" and not br.in_doubt]
    logger.warning("batch failed: %d written, %d in doubt, %d never sent",
                   len(written), len(unsure), len(not_sent))
```

When `batch_write(..., retry=N)` raises, `exc.partial_result.retry` holds the retry counters of the call.

### `batch_write` and the `in_doubt` Flag

`batch_write` returns per-record results that include an `in_doubt` flag. When `in_doubt` is `True`, the write may have completed on the server despite a transient error (e.g., timeout after the write was sent). Check `in_doubt` before retrying to avoid duplicate writes on non-idempotent operations:

```python
from aerospike_py.exception import AerospikeError

records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]

try:
    results = client.batch_write(records)
except AerospikeError:
    # Entire batch failed (e.g., cluster unavailable)
    raise

# Build lookup for retry (use 3-tuple keys to match input format)
records_by_key = {k: bins for k, bins in records}
retry_records = []

for br in results.batch_records:
    if br.result != 0:
        # br.key is a 4-tuple AerospikeKey(namespace, set_name, user_key, digest);
        # extract the 3-tuple to match the original input keys.
        input_key = (br.key[0], br.key[1], br.key[2]) if br.key else None
        if br.in_doubt:
            # Write may have succeeded -- verify before retrying
            logger.warning("Key %s in doubt (code=%d), skipping retry", br.key, br.result)
        elif input_key in records_by_key:
            # Definite failure -- safe to retry
            retry_records.append((input_key, records_by_key[input_key]))

if retry_records:
    client.batch_write(retry_records)
```

:::tip
Use the built-in `retry` parameter for automatic transient-failure retries with exponential backoff: `client.batch_write(records, retry=3)`. It re-sends only the records that failed, never one that succeeded, and never a `CREATE_ONLY` or generation-checked record that is in doubt. It is bounded by `total_timeout` (default 1000 ms), and it cannot be combined with a non-zero `policy["max_retries"]` (that raises `InvalidArgError`). Write batches (`batch_write`, `batch_write_numpy`, `batch_remove`, `batch_apply`, a writing `batch_operate`) do not re-send anything by themselves: their `max_retries` defaults to `0`.
:::

A batch containing writes rejects `POLICY_REPLICA_MASTER` with a positive `max_retries` before sending any row. With Rust client 3.0 that combination can resend rows already acknowledged by the server if the final batch trailer is lost. Use the default of zero retries for non-idempotent writes. A read-only batch accepts this replica policy.

The per-row retry loop also stops after an uncertain write that uses a filter expression, sets an explicit relative TTL or only removes bins. A second send could fail a predicate the first write changed, extend the requested expiry or report a missing record after deleting its last bin. For ordinary overwrites using the namespace default, opting into `retry=N` can still update generation and restart the server's default TTL. The public batch duration and error label describe the settled call, including retries. Extra attempts have separate `_retry` measurements.

A writing `batch_operate()` applies `exists`, `commit_level`, `ttl`, `key` and `durable_delete` to its rows. Generation comparisons require an expected generation, which this API does not take. Use `operate(..., meta={"gen": expected})` for a generation-checked operation. A read-only `batch_operate()` rejects `exists`, `gen` and `commit_level`. A delete has no `exists` policy, so `batch_remove()` rejects this field in both its policy and per-record meta.

### Re-sent Writes and `in_doubt`

Writes are not re-sent by default: `max_retries` is `0` for every write. When you set `max_retries > 0` on a write, the Rust client sends it again when its answer is lost. If the first send was applied, the second one meets its own work: a re-sent delete finds no record, a re-sent filtered write no longer matches, a re-sent UDF fails on what the first run left behind. The Rust client does not say whether a row was sent twice, so under such a policy:

- a row of `batch_write`, `batch_operate` (with a write), `batch_remove` or `batch_apply` that ends in `KEY_NOT_FOUND` (2), `FILTERED_OUT` (27) or `UDF_BAD_RESPONSE` (100) has `in_doubt == True`;
- so does a row of these calls with `PARTITION_UNAVAILABLE` (11) that the client gave the row itself, because it found no node for the record when the node's share was due to be sent again (the node was dropped from the cluster meanwhile, or the client was closed). The first send may have been applied. A row that a server refused with `PARTITION_UNAVAILABLE` at the first send is still `in_doubt == False`;
- `remove()` that raises `RecordNotFound` carries `in_doubt == True`.

The call does not know whether it changed the record, and says so; it still returns normally with such rows. With the default policy nothing changes, and reads (`batch_read`) are never in doubt.

Closing a connection while a retry-enabled single-record write is in progress can clear its partition map before the next send. When the namespace was routable as the call started and the operation then fails on that closed map, the exception carries `in_doubt=True`: a previous send may have applied. Reads, writes with zero retries, and a namespace already missing at the start do not acquire this flag from closing.

```python
import aerospike_py

result = client.batch_remove(keys, policy={"max_retries": 2})
for br in result.batch_records:
    if br.result == aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND and br.in_doubt:
        ...  # deleted by an earlier send of this call, or missing before it: read to find out
```

### Async Batch Read

`AsyncClient.batch_read()` returns the same `LazyBatchRecords` as the sync version. The dict view excludes missing or failed records; call `lazy_records.batch_records` / `lazy_records.iter_records()` if you need every entry:

```python
batch = await client.batch_read(keys)

# Dict-style iteration via the cached Mapping view
for user_key, bins in batch.items():
    print(user_key, bins)

# Check which keys are missing
all_user_keys = {k[2] for k in keys}
missing_keys = all_user_keys - set(batch.keys())
```

## Async Error Handling

Exception types are identical for sync and async clients. Use standard `try`/`except` with `await`:

```python
from aerospike_py.exception import RecordNotFound, AerospikeTimeoutError

async def get_user(client, user_id: str) -> dict | None:
    try:
        record = await client.get(("app", "users", user_id))
        return record.bins
    except RecordNotFound:
        return None
    except AerospikeTimeoutError:
        raise
```

### Concurrent Reads with `asyncio.gather`

Use `return_exceptions=True` to handle per-key errors without aborting all tasks:

```python
import asyncio
from aerospike_py.exception import RecordNotFound, AerospikeError

async def fetch_many(client, keys: list) -> list[dict | None]:
    tasks = [client.get(k) for k in keys]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    records = []
    for key, result in zip(keys, results):
        if isinstance(result, RecordNotFound):
            records.append(None)
        elif isinstance(result, AerospikeError):
            logger.error("Failed to get %s: %s", key, result)
            records.append(None)
        elif isinstance(result, Exception):
            raise result  # unexpected error
        else:
            records.append(result.bins)
    return records
```

## Write Conflict Handling

### CREATE_ONLY (Insert-Only)

Raises `RecordExistsError` if the record already exists:

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordExistsError

try:
    client.put(
        key,
        {"username": "alice"},
        policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY},
    )
except RecordExistsError:
    logger.info("User already exists, skipping insert")
```

### Optimistic Locking (Generation Check)

Use `POLICY_GEN_EQ` to perform compare-and-swap updates:

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordGenerationError

def safe_update(client, key, bin_name: str, transform):
    """Read-modify-write with generation check."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            record = client.get(key)
            new_val = transform(record.bins.get(bin_name))
            client.put(
                key,
                {bin_name: new_val},
                meta={"gen": record.meta.gen},
                policy={"gen": aerospike.POLICY_GEN_EQ},
            )
            return new_val
        except RecordGenerationError:
            if attempt == max_retries - 1:
                raise
            continue  # retry with fresh read
```

## Connection Error Handling

### Initial Connection

```python
import aerospike_py as aerospike
from aerospike_py.exception import ClusterError

try:
    client = aerospike.client(config).connect()
except ClusterError as e:
    logger.critical("Cannot reach Aerospike cluster: %s", e)
    raise SystemExit(1)
```

### Reconnection Pattern

The client automatically reconnects to surviving nodes when a node goes down. However, if the entire cluster is unreachable, operations will raise `ClusterError` or `AerospikeTimeoutError`. A retry-with-backoff pattern handles transient failures:

```python
import time
from aerospike_py.exception import AerospikeTimeoutError, ClusterError

TRANSIENT_ERRORS = (AerospikeTimeoutError, ClusterError)

def resilient_get(client, key, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return client.get(key)
        except TRANSIENT_ERRORS:
            if attempt == max_retries - 1:
                raise
            backoff = 0.1 * (2 ** attempt)  # 100ms, 200ms, 400ms
            time.sleep(backoff)
```

### Async Reconnection

```python
import asyncio
from aerospike_py.exception import AerospikeTimeoutError, ClusterError

async def resilient_get_async(client, key, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return await client.get(key)
        except (AerospikeTimeoutError, ClusterError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.1 * (2 ** attempt))
```

## Timeout Configuration

Timeouts can be set at two levels:

### Client-Level (Connection Timeout)

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "timeout": 5000,  # 5s connection timeout
}
```

### Per-Operation Timeouts

Fine-grained control via policy dicts:

```python
from aerospike_py.types import ReadPolicy, WritePolicy

# Read with generous timeout + retries
read_policy: ReadPolicy = {
    "socket_timeout": 5000,    # 5s per socket call
    "total_timeout": 15000,    # 15s total including retries
    "max_retries": 3,
    "sleep_between_retries": 500,  # 500ms between retries
}
record = client.get(key, policy=read_policy)

# Write with strict timeout
write_policy: WritePolicy = {
    "socket_timeout": 2000,
    "total_timeout": 5000,
    "max_retries": 1,
}
client.put(key, bins, policy=write_policy)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | Timeout per socket call (ms) |
| `total_timeout` | `int` | `1000` | Total timeout including retries (ms) |
| `max_retries` | `int` | `2` reads / `0` writes | Maximum number of retries. Writes default to `0` — see the note below. Batches follow the same rule: `2` for `batch_read` and a read-only `batch_operate`, `0` for every batch that writes, deletes or runs a UDF. |
| `sleep_between_retries` | `int` | `0` | Delay between retries (ms) |

:::warning[Writes do not retry by default]
`WritePolicy` defaults `max_retries` to **`0`**, while `ReadPolicy` defaults to `2`. `increment()`, `append()`, `prepend()`, `operate()` with an increment op, and `apply()` (an arbitrary UDF) are **not idempotent**: a spurious client-side timeout on a write the server already committed would, on retry, over-count the counter or append the string twice — silently.

The `0` default applies to *every* operation that takes a `WritePolicy`, including the idempotent ones — `put()`, `remove()`, `touch()`, and `remove_bin()`. One uniform default is easier to reason about than a per-operation table, so for those four opt back in explicitly when you want the resilience:

```python
client.remove(key, policy={"max_retries": 2})
client.put(key, bins, policy={"max_retries": 2})  # full-bin overwrite is idempotent
```

With `max_retries > 0`, a `remove()` that raises `RecordNotFound` has `in_doubt == True`: an earlier send may have deleted the record. See [Re-sent writes and `in_doubt`](#re-sent-writes-and-in_doubt).
:::

:::warning[Default timeout interaction]
With the defaults, `total_timeout` (1000ms) is **shorter** than `socket_timeout` (30000ms). This means the total deadline will be reached before any individual socket timeout fires. In practice, the client will abort the entire operation (including any in-flight socket read/write) after 1 second, regardless of the 30-second socket timeout. If you increase `socket_timeout`, also verify that `total_timeout` accommodates your expected latency and retry count.
:::

:::tip
Set `total_timeout` higher than `socket_timeout * (max_retries + 1)` to allow all retries to complete before the total deadline.
:::

## Result Code Reference

| Code | Constant | Exception |
|------|----------|-----------|
| 0 | `AEROSPIKE_OK` | (success) |
| 2 | `AEROSPIKE_ERR_RECORD_NOT_FOUND` | `RecordNotFound` |
| 3 | `AEROSPIKE_ERR_RECORD_GENERATION` | `RecordGenerationError` |
| 5 | `AEROSPIKE_ERR_RECORD_EXISTS` | `RecordExistsError` |
| 6 | `AEROSPIKE_ERR_BIN_EXISTS` | `BinExistsError` |
| 9 | `AEROSPIKE_ERR_TIMEOUT` | `AerospikeTimeoutError` |
| 12 | `AEROSPIKE_ERR_BIN_TYPE` | `BinTypeError` |
| 13 | `AEROSPIKE_ERR_RECORD_TOO_BIG` | `RecordTooBig` |
| 17 | `AEROSPIKE_ERR_BIN_NOT_FOUND` | `BinNotFound` |
| 20 | `AEROSPIKE_ERR_INVALID_NAMESPACE` | (batch row of a key in a namespace the cluster does not have; a single-record command raises `InvalidArgError`) |
| 21 | `AEROSPIKE_ERR_BIN_NAME` | `BinNameError` |
| 27 | `AEROSPIKE_ERR_FILTERED_OUT` | `FilteredOut` |
| 100 | `AEROSPIKE_ERR_UDF` | `UDFError` |
| 200 | `AEROSPIKE_ERR_INDEX_FOUND` | `IndexFoundError` |
| 201 | `AEROSPIKE_ERR_INDEX_NOT_FOUND` | `IndexNotFound` |
| 210 | `AEROSPIKE_ERR_QUERY_ABORTED` | `QueryAbortedError` |
| -1 | — | No server answered; see `error_type` |

See [Exceptions API Reference](../../api/exceptions.md) and [Constants](../../api/constants.md) for full lists.
