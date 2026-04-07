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

## Batch Error Handling

Batch operations do not raise exceptions for individual record failures. Instead, each `BatchRecord` carries its own result code:

```python
import aerospike_py as aerospike

keys = [("test", "demo", f"id-{i}") for i in range(100)]
batch = client.batch_read(keys)

succeeded = []
missing = []
errors = []

for br in batch.batch_records:
    if br.result == aerospike.AEROSPIKE_OK and br.record is not None:
        succeeded.append(br.record.bins)
    elif br.result == aerospike.AEROSPIKE_ERR_RECORD_NOT_FOUND:
        missing.append(br.key)
    else:
        errors.append((br.key, br.result))

if errors:
    logger.warning("Batch had %d errors", len(errors))
```

For `batch_operate`, failures on individual keys do not abort the entire batch:

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_operate(keys, operations)
except AerospikeError:
    # Entire batch failed (e.g., cluster unavailable)
    raise

for br in results.batch_records:
    if br.result != 0:
        logger.warning("Key %s failed (code=%d)", br.key, br.result)
```

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

# Build lookup for retry
records_by_key = {k: bins for k, bins in records}
retry_records = []

for br in results.batch_records:
    if br.result != 0:
        if br.in_doubt:
            # Write may have succeeded -- verify before retrying
            logger.warning("Key %s in doubt (code=%d), skipping retry", br.key, br.result)
        elif br.key in records_by_key:
            # Definite failure -- safe to retry
            retry_records.append((br.key, records_by_key[br.key]))

if retry_records:
    client.batch_write(retry_records)
```

:::tip
Use the built-in `retry` parameter for automatic transient-failure retries with exponential backoff: `client.batch_write(records, retry=3)`. For non-idempotent operations where duplicates are unacceptable, keep `retry=0` (default) and handle retries manually using the `in_doubt` flag as shown above.
:::

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
| `max_retries` | `int` | `2` | Maximum number of retries |
| `sleep_between_retries` | `int` | `0` | Delay between retries (ms) |

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
| 21 | `AEROSPIKE_ERR_BIN_NAME` | `BinNameError` |
| 27 | `AEROSPIKE_ERR_FILTERED_OUT` | `FilteredOut` |
| 200 | `AEROSPIKE_ERR_INDEX_FOUND` | `IndexFoundError` |
| 201 | `AEROSPIKE_ERR_INDEX_NOT_FOUND` | `IndexNotFound` |
| 210 | `AEROSPIKE_ERR_QUERY_ABORTED` | `QueryAbortedError` |

See [Exceptions API Reference](../../api/exceptions.md) and [Constants](../../api/constants.md) for full lists.
