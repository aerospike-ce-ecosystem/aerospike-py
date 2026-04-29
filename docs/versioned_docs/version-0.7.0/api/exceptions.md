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
| `UDFError` | UDF error |

:::note
`TimeoutError` and `IndexError` are deprecated aliases for `AerospikeTimeoutError` and `AerospikeIndexError` to avoid shadowing Python builtins.
:::

## Examples

```python
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
