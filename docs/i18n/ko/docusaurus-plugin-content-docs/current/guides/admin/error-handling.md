---
title: 오류 처리
sidebar_label: 오류 처리
sidebar_position: 3
slug: /guides/error-handling
description: aerospike-py를 위한 운영 환경 오류 처리 패턴
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

## Exception Hierarchy

모든 aerospike-py exception은 `AerospikeError`를 상속합니다. `AerospikeError`는 Python builtin `Exception`을 상속합니다.

```
Exception
└── AerospikeError                   # 모든 Aerospike error 의 base
    ├── ClientError                  # client-side (connection, config, 내부)
    ├── ClusterError                 # cluster 연결 / node error
    ├── InvalidArgError              # operation 에 잘못된 인자
    ├── AerospikeTimeoutError        # operation timeout
    ├── ServerError                  # server-side error
    │   ├── AerospikeIndexError      # secondary index error
    │   │   ├── IndexNotFound        # index 없음 (201)
    │   │   └── IndexFoundError      # index 이미 존재 (200)
    │   ├── QueryError               # query 실행 error
    │   │   └── QueryAbortedError    # server 가 query 중단 (210)
    │   ├── AdminError               # admin / security operation error
    │   └── UDFError                 # UDF 실행 error
    └── RecordError                  # record-level error
        ├── RecordNotFound           # record 없음 (2)
        ├── RecordExistsError        # record 이미 존재 (5)
        ├── RecordGenerationError    # generation mismatch (3)
        ├── RecordTooBig             # record 크기 한도 초과 (13)
        ├── BinNameError             # bin name 너무 김 (21)
        ├── BinExistsError           # bin 이미 존재 (6)
        ├── BinNotFound              # bin 없음 (17)
        ├── BinTypeError             # bin type mismatch (12)
        └── FilteredOut              # expression filter 로 제외 (27)
```

`aerospike_py.exception` 에서 import:

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

## 기본 error handling

구체적인 exception을 먼저 catch하고, 더 넓은 exception은 나중에 처리하세요.

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
    # missing record 처리
    bins = {}
except AerospikeTimeoutError:
    # retry 또는 circuit-break
    raise
except ClusterError:
    # 연결 끊김 — 재연결 또는 빠른 실패
    raise
except AerospikeError as e:
    # 기타 Aerospike error 의 catch-all
    logger.error("Aerospike error: %s", e)
    raise
```

## Batch error handling

Batch operation은 개별 record가 실패해도 exception을 발생시키지 않습니다. 대신 각 `BatchRecord`에 result code가 들어 있습니다.

```python
keys = [("test", "demo", f"id-{i}") for i in range(100)]

# batch_read 는 `LazyBatchRecords` 반환. `user_key` 를 가진 성공한 read 가
# dict view 를 populate; missing key 와 per-record 실패는 필터링됨
# (모든 entry 가 필요하면 `batch.batch_records` 또는 `batch.iter_records()` 사용).
batch = client.batch_read(keys)

# 성공한 record 가 dict view 에 있음; missing key 는 없음.
# dict-like `.values()` / `.keys()` accessor 는 cached `to_dict()`
# materialisation 으로 backed, 추가 변환 불필요.
succeeded = list(batch.values())
all_user_keys = {k[2] for k in keys}
present_keys = set(batch.keys())
missing_keys = all_user_keys - present_keys

if missing_keys:
    logger.warning("Batch had %d missing keys", len(missing_keys))
```

`batch_operate` 의 경우 개별 key 실패가 전체 batch 를 abort 하지 않음:

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_operate(keys, operations)
except AerospikeError:
    # 전체 batch 실패 (예: cluster 도달 불가)
    raise

for br in results.batch_records:
    if br.result != 0:
        logger.warning("Key %s failed (code=%d)", br.key, br.result)
```

### `batch_write` 와 `in_doubt` flag

`batch_write`는 record별 결과에 `in_doubt` flag를 포함합니다. 이 값이 `True`이면 transient error가 발생했어도 server에서 write를 완료했을 수 있습니다. Write를 보낸 뒤 timeout이 난 경우가 한 예입니다. Non-idempotent operation을 두 번 적용하지 않도록 retry 전에 `in_doubt`를 확인하세요.

```python
from aerospike_py.exception import AerospikeError

records = [
    (("test", "demo", "user1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "user2"), {"name": "Bob", "age": 25}),
]

try:
    results = client.batch_write(records)
except AerospikeError:
    # 전체 batch 실패 (예: cluster 도달 불가)
    raise

# retry 용 lookup 빌드 (입력 형식에 맞추기 위해 3-tuple key 사용)
records_by_key = {k: bins for k, bins in records}
retry_records = []

for br in results.batch_records:
    if br.result != 0:
        # br.key 는 4-tuple AerospikeKey(namespace, set_name, user_key, digest);
        # 원본 입력 key 에 맞추기 위해 3-tuple 추출.
        input_key = (br.key[0], br.key[1], br.key[2]) if br.key else None
        if br.in_doubt:
            # write 가 성공했을 수 있음 — retry 전 검증
            logger.warning("Key %s in doubt (code=%d), skipping retry", br.key, br.result)
        elif input_key in records_by_key:
            # 확정 실패 — retry 안전
            retry_records.append((input_key, records_by_key[input_key]))

if retry_records:
    client.batch_write(retry_records)
```

:::tip
exponential backoff 으로 자동 transient-failure retry 를 원하면 내장 `retry` 파라미터 사용: `client.batch_write(records, retry=3)`. 중복이 허용 안 되는 non-idempotent operation 의 경우 `retry=0` (기본값) 유지하고 위와 같이 `in_doubt` flag 로 retry 를 수동 처리.
:::

### Async Batch Read

`AsyncClient.batch_read()` 는 sync 버전과 동일한 `LazyBatchRecords` 반환. dict view 는 missing/failed record 를 제외; 모든 entry 가 필요하면 `lazy_records.batch_records` / `lazy_records.iter_records()`:

```python
batch = await client.batch_read(keys)

# cached Mapping view 통한 dict-style 순회
for user_key, bins in batch.items():
    print(user_key, bins)

# 어떤 key 가 missing 인지 확인
all_user_keys = {k[2] for k in keys}
missing_keys = all_user_keys - set(batch.keys())
```

## Async error handling

Exception 타입은 sync 와 async client 동일. `await` 와 표준 `try`/`except`:

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

### `asyncio.gather` 로 concurrent read

`return_exceptions=True` 로 모든 task 를 abort 하지 않고 per-key error 처리:

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
            raise result  # 예상치 못한 error
        else:
            records.append(result.bins)
    return records
```

## Write conflict 처리

### CREATE_ONLY (Insert-Only)

Record가 이미 있으면 `RecordExistsError`가 발생합니다.

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

compare-and-swap update 를 위해 `POLICY_GEN_EQ` 사용:

```python
import aerospike_py as aerospike
from aerospike_py.exception import RecordGenerationError

def safe_update(client, key, bin_name: str, transform):
    """generation check 가 있는 read-modify-write."""
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
            continue  # fresh read 로 retry
```

## Connection error 처리

### 초기 연결

```python
import aerospike_py as aerospike
from aerospike_py.exception import ClusterError

try:
    client = aerospike.client(config).connect()
except ClusterError as e:
    logger.critical("Cannot reach Aerospike cluster: %s", e)
    raise SystemExit(1)
```

### Reconnection 패턴

Node가 중단되면 client는 정상 node로 자동 재연결합니다. 전체 cluster에 연결할 수 없으면 operation에서 `ClusterError`나 `AerospikeTimeoutError`가 발생합니다. Transient failure는 retry와 backoff로 처리할 수 있습니다.

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

### Async reconnection

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

## Timeout 설정

Timeout 은 두 수준에서 설정 가능:

### Client-Level (Connection Timeout)

```python
config = {
    "hosts": [("127.0.0.1", 3000)],
    "timeout": 5000,  # 5s connection timeout
}
```

### Per-Operation Timeout

policy dict 통한 세분화된 제어:

```python
from aerospike_py.types import ReadPolicy, WritePolicy

# 넉넉한 timeout + retry 의 read
read_policy: ReadPolicy = {
    "socket_timeout": 5000,    # socket 호출당 5s
    "total_timeout": 15000,    # retry 포함 총 15s
    "max_retries": 3,
    "sleep_between_retries": 500,  # retry 간 500ms
}
record = client.get(key, policy=read_policy)

# 엄격한 timeout 의 write
write_policy: WritePolicy = {
    "socket_timeout": 2000,
    "total_timeout": 5000,
    "max_retries": 1,
}
client.put(key, bins, policy=write_policy)
```

| Field | Type | Default | 설명 |
|-------|------|---------|-------------|
| `socket_timeout` | `int` | `30000` | socket 호출당 timeout (ms) |
| `total_timeout` | `int` | `1000` | retry 포함 총 timeout (ms) |
| `max_retries` | `int` | `2` | 최대 retry 횟수 |
| `sleep_between_retries` | `int` | `0` | retry 간 지연 (ms) |

:::warning[기본 timeout 상호작용]
기본값에서는 `total_timeout`(1,000 ms)이 `socket_timeout`(30,000 ms)보다 **짧습니다**. 따라서 개별 socket timeout보다 total deadline이 먼저 끝납니다. Client는 30초 socket timeout과 관계없이 1초 뒤에 진행 중인 socket I/O를 포함한 전체 operation을 중단합니다. `socket_timeout`을 늘릴 때는 `total_timeout`도 예상 latency와 retry 횟수를 수용하는지 확인하세요.
:::

:::tip
모든 retry 가 total deadline 전에 완료되도록 `total_timeout` 을 `socket_timeout * (max_retries + 1)` 보다 높게 설정.
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

전체 list 는 [Exceptions API Reference](../../api/exceptions.md) 와 [Constants](../../api/constants.md) 참조.
