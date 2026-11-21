---
title: Exceptions
sidebar_label: Exceptions
sidebar_position: 3
description: Exception hierarchy and error handling patterns.
---

```python
from aerospike_py.exception import RecordNotFound, AerospikeError
```

## Hierarchy

```
Exception
└── AerospikeError
    ├── ClientError
    ├── ClusterError
    ├── InvalidArgError
    ├── AerospikeTimeoutError
    ├── ServerError
    │   ├── AerospikeIndexError
    │   │   ├── IndexNotFound
    │   │   └── IndexFoundError
    │   ├── QueryError
    │   │   └── QueryAbortedError
    │   ├── AdminError
    │   └── UDFError
    └── RecordError
        ├── RecordNotFound
        ├── RecordExistsError
        ├── RecordGenerationError
        ├── RecordTooBig
        ├── BinNameError
        ├── BinExistsError
        ├── BinNotFound
        ├── BinTypeError
        └── FilteredOut
```

## Attributes

Every exception in the hierarchy carries these attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `result_code` | `int` | The server's result code when a server answered (for example `2` record not found, `5` record exists, `100` UDF failed), matching the `AEROSPIKE_ERR_*` constants. `-1` when no server answered: a client timeout, a connection failure, an invalid argument. |
| `error_type` | `str` | The kind of failure, by the same name the Prometheus `error_type` label and the OpenTelemetry `error.type` attribute carry. A server code is named after the code (`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, `"DeviceOverload"`, ...), with `"ServerTimeout"` for a timeout the server reported. Client-side failures are `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"` and `"Client"`. This is what tells the `-1` cases apart. |
| `in_doubt` | `bool` | `True` when a write was sent and no definite answer came back, so the server may have applied it. `False` when the server answered with a failure (record exists, a failed UDF, a refusal such as `KEY_BUSY`, ...), and always for reads. With `max_retries > 0` on a write, `remove()` raising `RecordNotFound` is in doubt too: an earlier send may have deleted the record (see [Re-sent writes and `in_doubt`](../guides/admin/error-handling.md#re-sent-writes-and-in_doubt)). |
| `partial_result` | `BatchWriteResult \| None` | The per-record rows of a batch call that failed as a whole: one `BatchRecord` per requested record, in request order. `None` for every other failure. |

```python
import aerospike_py

try:
    client.put(key, bins)
except aerospike_py.AerospikeError as exc:
    if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS:
        ...
    elif exc.error_type == "Timeout" and exc.in_doubt:
        ...  # the write may be in; read before writing again

try:
    client.batch_write(records)
except aerospike_py.AerospikeError as exc:
    if exc.partial_result is not None:
        done = [br.key for br in exc.partial_result.batch_records if br.result == 0]
```

## Reference

### Base

| Exception | Description |
|-----------|-------------|
| `AerospikeError` | Base for all Aerospike exceptions |
| `ClientError` | Client-side errors (connection, config) |
| `ClusterError` | Cluster connection/discovery errors |
| `InvalidArgError` | Invalid argument |
| `AerospikeTimeoutError` | Operation timed out |
| `ServerError` | Server-side errors |
| `RecordError` | Record-level errors |

### Record

| Exception | Description |
|-----------|-------------|
| `RecordNotFound` | Record does not exist |
| `RecordExistsError` | Record already exists (`CREATE_ONLY`) |
| `RecordGenerationError` | Generation mismatch (optimistic lock) |
| `RecordTooBig` | Record exceeds size limit |
| `BinNameError` | Invalid bin name |
| `BinExistsError` | Bin already exists |
| `BinNotFound` | Bin does not exist |
| `BinTypeError` | Bin type mismatch |
| `FilteredOut` | Excluded by expression filter |

### Server

| Exception | Description |
|-----------|-------------|
| `AerospikeIndexError` | Secondary index error |
| `IndexNotFound` | Index does not exist |
| `IndexFoundError` | Index already exists |
| `QueryError` | Query execution error |
| `QueryAbortedError` | Query aborted |
| `AdminError` | Admin operation error |
| `UDFError` | A UDF the server could not run (`result_code == 100`, `AEROSPIKE_ERR_UDF`). Up to 0.14.x this surfaced as `ClientError` with `-1`. |

:::note
`TimeoutError` and `IndexError` are deprecated aliases for `AerospikeTimeoutError` and `AerospikeIndexError` to avoid shadowing Python builtins.
:::

## Examples

```python
import aerospike_py as aerospike
from aerospike_py.exception import (
    RecordNotFound,
    RecordExistsError,
    RecordGenerationError,
    AerospikeTimeoutError,
    AerospikeError,
)

# Basic error handling
try:
    record = client.get(("test", "demo", "nonexistent"))
except RecordNotFound:
    print("Not found")
except AerospikeError as e:
    print(f"Error: {e}")

# Optimistic locking
try:
    record = client.get(key)
    client.put(
        key,
        {"val": record.bins["val"] + 1},
        meta={"gen": record.meta.gen},
        policy={"gen": aerospike.POLICY_GEN_EQ},
    )
except RecordGenerationError:
    print("Concurrent modification detected")

# Create-only
try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    print("Already exists")
```

See the [Error Handling Guide](../guides/admin/error-handling.md) for production patterns.
