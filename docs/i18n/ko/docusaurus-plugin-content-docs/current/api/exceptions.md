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

| Exception | 설명 |
|-----------|-------------|
| `AerospikeError` | 모든 Aerospike exception 의 base |
| `ClientError` | client-side error (connection, config) |
| `ClusterError` | cluster 연결/discovery error |
| `InvalidArgError` | 잘못된 인자 |
| `AerospikeTimeoutError` | operation timeout |
| `ServerError` | server-side error |
| `RecordError` | record-level error |

### Record

| Exception | 설명 |
|-----------|-------------|
| `RecordNotFound` | record 없음 |
| `RecordExistsError` | record 이미 존재 (`CREATE_ONLY`) |
| `RecordGenerationError` | generation mismatch (optimistic lock) |
| `RecordTooBig` | record 가 크기 한도 초과 |
| `BinNameError` | 잘못된 bin name |
| `BinExistsError` | bin 이미 존재 |
| `BinNotFound` | bin 없음 |
| `BinTypeError` | bin type mismatch |
| `FilteredOut` | expression filter 로 제외 |

### Server

| Exception | 설명 |
|-----------|-------------|
| `AerospikeIndexError` | secondary index error |
| `IndexNotFound` | index 없음 |
| `IndexFoundError` | index 이미 존재 |
| `QueryError` | query 실행 error |
| `QueryAbortedError` | query 중단됨 |
| `AdminError` | admin operation error |
| `UDFError` | UDF error |

:::note
`TimeoutError` 와 `IndexError` 는 Python builtin shadow 방지를 위해 각각 `AerospikeTimeoutError` 와 `AerospikeIndexError` 의 deprecated alias.
:::

## 예제

```python
from aerospike_py.exception import (
    RecordNotFound,
    RecordExistsError,
    RecordGenerationError,
    AerospikeTimeoutError,
    AerospikeError,
)

# 기본 error handling
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

production 패턴은 [Error Handling Guide](../guides/admin/error-handling.md) 참조.
