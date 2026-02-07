---
title: Exceptions
sidebar_label: Exceptions
sidebar_position: 3
description: Exception hierarchy and error handling patterns for aerospike-py.
---

All exceptions are available from `aerospike` and `aerospike.exception`.

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordNotFound
```

## Exception Hierarchy

```
Exception
└── AerospikeError
    ├── ClientError
    ├── ClusterError
    ├── InvalidArgError
    ├── TimeoutError
    ├── ServerError
    │   ├── IndexError
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

## Base Exceptions

| Exception | Description |
|-----------|-------------|
| `AerospikeError` | Base for all Aerospike exceptions |
| `ClientError` | Client-side errors (connection, config) |
| `ClusterError` | Cluster connection/discovery errors |
| `InvalidArgError` | Invalid argument passed to a method |
| `TimeoutError` | Operation timed out |
| `ServerError` | Server-side errors |
| `RecordError` | Record-level operation errors |

## Record Exceptions

| Exception | Description |
|-----------|-------------|
| `RecordNotFound` | Record does not exist |
| `RecordExistsError` | Record already exists (CREATE_ONLY policy) |
| `RecordGenerationError` | Generation mismatch (optimistic locking) |
| `RecordTooBig` | Record exceeds size limit |
| `BinNameError` | Invalid bin name (too long, invalid chars) |
| `BinExistsError` | Bin already exists |
| `BinNotFound` | Bin does not exist |
| `BinTypeError` | Bin type mismatch |
| `FilteredOut` | Record filtered by expression |

## Server Exceptions

| Exception | Description |
|-----------|-------------|
| `IndexError` | Secondary index operation error |
| `IndexNotFound` | Index does not exist |
| `IndexFoundError` | Index already exists |
| `QueryError` | Query execution error |
| `QueryAbortedError` | Query was aborted |
| `AdminError` | Admin operation error |
| `UDFError` | UDF registration/execution error |

## Error Handling Examples

### Basic Error Handling

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordNotFound, AerospikeError

try:
    _, meta, bins = client.get(("test", "demo", "nonexistent"))
except RecordNotFound:
    print("Record not found")
except AerospikeError as e:
    print(f"Aerospike error: {e}")
```

### Optimistic Locking

```python
from aerospike_py.exception import RecordGenerationError

try:
    _, meta, bins = client.get(key)
    client.put(key, {"val": bins["val"] + 1},
               meta={"gen": meta["gen"]},
               policy={"gen": aerospike.POLICY_GEN_EQ})
except RecordGenerationError:
    print("Record was modified by another client")
```

### Create-Only

```python
from aerospike_py.exception import RecordExistsError

try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    print("Record already exists")
```

### Connection Errors

```python
from aerospike_py.exception import ClientError, ClusterError, TimeoutError

try:
    client = aerospike.client(config).connect()
except ClusterError:
    print("Cannot connect to cluster")
except TimeoutError:
    print("Connection timed out")
except ClientError as e:
    print(f"Client error: {e}")
```
