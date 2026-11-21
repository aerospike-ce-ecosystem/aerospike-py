---
title: 예외
sidebar_label: 예외
sidebar_position: 3
description: 예외 계층 구조와 오류 처리 패턴
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

## Attribute

계층의 모든 exception에는 다음 attribute가 있습니다.

| Attribute | Type | 설명 |
|-----------|------|------|
| `result_code` | `int` | Server가 응답했으면 server의 result code(예: `2` record 없음, `5` record 이미 존재, `100` UDF 실패)이며 `AEROSPIKE_ERR_*` 상수와 일치합니다. 어떤 server도 응답하지 않았으면 `-1`: client timeout, connection 실패, 잘못된 인자. |
| `error_type` | `str` | 실패의 종류. Prometheus `error_type` label, OpenTelemetry `error.type` attribute와 같은 이름입니다. Server code는 code 이름을 따르고(`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, `"DeviceOverload"`, ...), server가 알린 timeout은 `"ServerTimeout"`입니다. Client 쪽 실패는 `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"`, `"Client"`입니다. `-1`인 경우들은 이 값으로 구분합니다. |
| `in_doubt` | `bool` | Write를 보냈지만 확정된 응답을 받지 못해 server가 적용했을 수 있으면 `True`. server가 실패라고 응답한 경우(record 존재, UDF 실패, `KEY_BUSY` 같은 거절 등)와 읽기에서는 항상 `False`. Write에 `max_retries > 0`을 주었다면 `RecordNotFound`를 발생시킨 `remove()`도 in doubt입니다. 앞선 전송이 record를 지웠을 수 있기 때문입니다([다시 보낸 write와 `in_doubt`](../guides/admin/error-handling.md#re-sent-writes-and-in_doubt) 참고). 전체가 실패한 batch 호출의 exception은 `partial_result`의 row 중 하나라도 in doubt이면 in doubt입니다. |
| `partial_result` | `BatchWriteResult \| None` | 전체가 실패한 batch 호출의 record별 row: 요청한 record마다 `BatchRecord` 하나를 요청 순서대로 담습니다. 그 밖의 실패에서는 `None`. 호출이 여러 node에서 실패했다면 exception은 그중 한 node의 오류(몫이 처음 실패한 node)이므로 type과 `result_code`가 record 순서에 따라 달라질 수 있습니다. 각 record에 무슨 일이 있었는지는 row가 알려 줍니다. |

```python
import aerospike_py

try:
    client.put(key, bins)
except aerospike_py.AerospikeError as exc:
    if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS:
        ...
    elif exc.error_type == "Timeout" and exc.in_doubt:
        ...  # write가 적용되었을 수 있음; 다시 쓰기 전에 읽어서 확인

try:
    client.batch_write(records)
except aerospike_py.AerospikeError as exc:
    if exc.partial_result is not None:
        done = [br.key for br in exc.partial_result.batch_records if br.result == 0]
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
| `UDFError` | server가 실행하지 못한 UDF (`result_code == 100`, `AEROSPIKE_ERR_UDF`). 0.14.x까지는 `-1`인 `ClientError`로 나타났습니다. |

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
