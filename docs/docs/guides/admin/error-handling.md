---
title: Error Handling
sidebar_label: Error Handling
sidebar_position: 3
slug: /guides/error-handling
description: Production error handling patterns for aerospike-py.
---

## Catch Specific, Then Broad

```python
from aerospike_py.exception import (
    RecordNotFound,
    AerospikeTimeoutError,
    AerospikeError,
)

try:
    record = client.get(key)
except RecordNotFound:
    bins = {}
except AerospikeTimeoutError:
    raise  # retry or circuit-break
except AerospikeError as e:
    logger.error("Aerospike error: %s", e)
    raise
```

## Retry with Backoff

```python
import time
from aerospike_py.exception import AerospikeTimeoutError, ClusterError

def get_with_retry(client, key, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return client.get(key)
        except (AerospikeTimeoutError, ClusterError):
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (2 ** attempt))
```

## Optimistic Locking (CAS)

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordGenerationError

def increment_counter(client, key, bin_name: str) -> int:
    while True:
        try:
            record = client.get(key)
            new_val = record.bins.get(bin_name, 0) + 1
            client.put(
                key,
                {bin_name: new_val},
                meta={"gen": record.meta.gen},
                policy={"gen": aerospike.POLICY_GEN_EQ},
            )
            return new_val
        except RecordGenerationError:
            continue
```

## Create-Only vs Upsert

```python
from aerospike_py.exception import RecordExistsError

# Create-only
try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    pass  # already exists

# Upsert (default) -- never raises RecordExistsError
client.put(key, bins)
```

## Batch Error Handling

```python
batch = client.batch_read(keys)
for br in batch.batch_records:
    if br.result == aerospike.AEROSPIKE_OK and br.record:
        process(br.record.bins)
    elif br.result == aerospike.AEROSPIKE_ERR_RECORD_NOT_FOUND:
        handle_missing(br.key)
    else:
        logger.warning("Batch error: code=%d", br.result)
```

## Connection Lifecycle

```python
from aerospike_py.exception import ClusterError

try:
    client = aerospike.client(config).connect()
except ClusterError as e:
    print(f"Cannot reach cluster: {e}")
    raise SystemExit(1)

try:
    # application logic
    pass
finally:
    client.close()
```

## Async

Error handling is identical, just add `await`:

```python
async def get_user(client, user_id: str) -> dict | None:
    try:
        record = await client.get(("app", "users", user_id))
        return record.bins
    except RecordNotFound:
        return None
```

## Result Code Reference

| Code | Constant | Exception |
|------|----------|-----------|
| 0 | `AEROSPIKE_OK` | (success) |
| 2 | `AEROSPIKE_ERR_RECORD_NOT_FOUND` | `RecordNotFound` |
| 5 | `AEROSPIKE_ERR_RECORD_EXISTS` | `RecordExistsError` |
| 9 | `AEROSPIKE_ERR_TIMEOUT` | `AerospikeTimeoutError` |
| 3 | `AEROSPIKE_ERR_RECORD_GENERATION` | `RecordGenerationError` |
| 13 | `AEROSPIKE_ERR_RECORD_TOO_BIG` | `RecordTooBig` |
| 27 | `AEROSPIKE_ERR_FILTERED_OUT` | `FilteredOut` |

See [Exceptions](../../api/exceptions.md) and [Constants](../../api/constants.md) for full lists.
