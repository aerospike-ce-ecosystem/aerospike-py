---
title: Error Handling
sidebar_label: Error Handling
sidebar_position: 3
slug: /guides/error-handling
description: Best practices for handling Aerospike errors in production applications.
---

# Error Handling Guide

## Exception Hierarchy

All aerospike-py exceptions inherit from `AerospikeError`. See the
[Exceptions API reference](../../api/exceptions.md) for the full hierarchy and
descriptions.

```python
import aerospike_py as aerospike
from aerospike_py import exception
```

## Recommended Patterns

### Catch Specific, Then Broad

Always catch the most specific exception first:

```python
from aerospike_py.exception import (
    RecordNotFound,
    AerospikeTimeoutError,
    AerospikeError,
)

try:
    _, meta, bins = client.get(key)
except RecordNotFound:
    # Handle missing record (e.g., return default)
    bins = {}
except AerospikeTimeoutError:
    # Retry or circuit-break
    raise
except AerospikeError as e:
    # Unexpected Aerospike error
    logger.error("Aerospike error: %s", e)
    raise
```

### Retry with Backoff

Timeout and cluster errors are often transient:

```python
import time
from aerospike_py.exception import AerospikeTimeoutError, ClusterError

def get_with_retry(client, key, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.get(key)
        except (AerospikeTimeoutError, ClusterError):
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (2 ** attempt))  # exponential backoff
```

### Optimistic Locking (Check-and-Set)

Use generation checks to detect concurrent modifications:

```python
from aerospike_py.exception import RecordGenerationError

def increment_counter(client, key, bin_name):
    while True:
        try:
            _, meta, bins = client.get(key)
            new_val = bins.get(bin_name, 0) + 1
            client.put(
                key,
                {bin_name: new_val},
                meta={"gen": meta.gen},
                policy={"gen": aerospike.POLICY_GEN_EQ},
            )
            return new_val
        except RecordGenerationError:
            continue  # retry with fresh data
```

### Upsert vs Create-Only

```python
from aerospike_py.exception import RecordExistsError

# Create-only: fail if record exists
try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    print("Record already exists, skipping")

# Upsert (default): create or update
client.put(key, bins)  # never raises RecordExistsError
```

### Batch Error Handling

Batch operations return results per-key. Check individual record status:

```python
results = client.batch_read(keys)
for result in results:
    if result.result_code == aerospike.AEROSPIKE_OK:
        process(result.bins)
    elif result.result_code == aerospike.AEROSPIKE_ERR_RECORD_NOT_FOUND:
        handle_missing(result.key)
    else:
        logger.warning("Batch key error: code=%d", result.result_code)
```

### Connection Lifecycle

```python
from aerospike_py.exception import ClientError, ClusterError

client = aerospike.client(config)
try:
    client.connect()
except ClusterError as e:
    print(f"Cannot reach cluster: {e}")
    raise SystemExit(1)

try:
    # ... application logic ...
    pass
finally:
    client.close()
```

### Async Error Handling

Async errors work the same way, just with `await`:

```python
from aerospike_py.exception import RecordNotFound

async def get_user(client, user_id):
    key = ("app", "users", user_id)
    try:
        _, _, bins = await client.get(key)
        return bins
    except RecordNotFound:
        return None
```

## Result Codes

Common Aerospike result codes mapped to exceptions:

| Code | Constant | Exception |
|------|----------|-----------|
| 0 | `AEROSPIKE_OK` | (success) |
| 2 | `AEROSPIKE_ERR_RECORD_NOT_FOUND` | `RecordNotFound` |
| 5 | `AEROSPIKE_ERR_RECORD_EXISTS` | `RecordExistsError` |
| 9 | `AEROSPIKE_ERR_TIMEOUT` | `AerospikeTimeoutError` |
| 3 | (generation error) | `RecordGenerationError` |
| 13 | (record too big) | `RecordTooBig` |
| 27 | (filtered out) | `FilteredOut` |

See the [Constants reference](../../api/constants.md) for the full list.
