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

## Exception이 알려 주는 것

모든 `AerospikeError`에는 attribute 네 개가 있습니다. Release마다 바뀔 수 있는 메시지 문자열 대신 이 attribute를 사용하세요.

| Attribute | 의미 |
|-----------|------|
| `result_code` | Server가 응답했으면 server의 result code(예: `2` record 없음, `5` record 이미 존재, `100` UDF 실패). 어떤 server도 응답하지 않았으면 `-1`: client timeout, connection 실패, 잘못된 인자. |
| `error_type` | 실패의 종류를 나타내는 이름. Server code는 code 이름을 따릅니다(`"KeyNotFoundError"`, `"KeyExistsError"`, `"GenerationError"`, `"FilteredOut"`, ...; server가 알린 timeout은 `"ServerTimeout"`). Client 쪽 실패는 `"Timeout"`, `"MaxRetriesExceeded"`, `"Connection"`, `"NoMoreConnections"`, `"MaxErrorRate"`, `"InvalidNode"`, `"InvalidArgument"`, `"UdfBadResponse"`, `"StreamTerminated"`, `"BadResponse"`, `"Backpressure"`, `"RustPanic"`, `"Client"` 중 하나입니다. `-1`인 경우들은 이 값으로 구분합니다. |
| `in_doubt` | Write를 보냈지만 확정된 응답을 받지 못해 server가 적용했을 수 있으면 `True`. server가 실패라고 응답한 경우(record 존재, UDF 실패 등)와 읽기에서는 항상 `False`. `max_retries > 0`으로 보낸 write는 예외입니다. [다시 보낸 write와 `in_doubt`](#re-sent-writes-and-in_doubt)를 참고하세요. 전체가 실패한 batch 호출의 exception은 `partial_result`의 row 중 하나라도 in doubt이면 in doubt입니다. |
| `partial_result` | 전체가 실패한 batch 호출이면 요청한 record마다 row 하나를 요청 순서대로 담은 `BatchWriteResult`. 그 밖의 실패에서는 `None`. 호출이 여러 node에서 실패했다면 exception은 그중 한 node의 오류(몫이 처음 실패한 node)이고, 각 record에 무슨 일이 있었는지는 row가 알려 줍니다. |

```python
import aerospike_py

try:
    client.put(key, bins)
except aerospike_py.AerospikeError as exc:
    if exc.result_code == aerospike_py.AEROSPIKE_ERR_RECORD_EXISTS:
        ...  # server가 응답함: record가 이미 있음
    elif exc.error_type == "Timeout" and exc.in_doubt:
        ...  # write가 적용되었을 수 있음; 다시 쓰기 전에 record를 읽어 확인
    else:
        raise
```

Prometheus `error_type` label과 OpenTelemetry `error.type` attribute는 `exc.error_type`과 같은 이름을 사용하므로, dashboard와 `except` 절이 실패를 같은 방식으로 분류합니다.

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
    # 전체 batch 실패 (예: cluster 도달 불가); 아래 참고
    raise

for br in results.batch_records:
    if br.result != 0:
        logger.warning("Key %s failed (code=%d, %s)", br.key, br.result, br.error_type)
```

### 각 row가 알려 주는 것

모든 `BatchRecord`에는 `result`, `error_type`, `in_doubt`가 있습니다.

| 결과 | `result` | `error_type` | `in_doubt` |
|------|----------|--------------|------------|
| 성공 | `0` | `None` | `False` |
| Record 없음 | `2` | `"KeyNotFoundError"` | `False` |
| `filter_expression`으로 제외됨 | `27` | `"FilteredOut"` | `False` |
| Server가 알린 그 밖의 실패 | 해당 code | code 이름 | `False` |
| Server가 timeout을 알림 | `9` | `"ServerTimeout"` | write면 `True` |
| 요청을 보냈지만 client가 기다리기를 멈춤 | `-1` | `"Timeout"` | write면 `True` |
| 전송 실패 | `-1` | `"Connection"`, `"InvalidNode"`, ... | 이미 보낸 write면 `True` |
| 그 record에 대해 어떤 node도 응답하지 않음 | `-1` | `"NoResponse"` | 아무것도 보내지 않았으면(key를 route하지 못함) `False`. 호출이 row를 돌려받지 못한 채 끝났고 이미 보냈을 수 있으면 write에 대해 `True` |

`result`는 server가 그 record의 성공을 알린 경우에만 `0`입니다. 아무 응답이 없었다는 이유로 row가 쓰인 것으로 취급되는 일은 없습니다.

Server가 retry할 만한 code인 `KEY_BUSY`(14), `DEVICE_OVERLOAD`(18), `PARTITION_UNAVAILABLE`(11)로 거절한 write는 응답입니다. 그 row는 해당 code와 `in_doubt == False`를 갖고, key가 하나뿐인 batch에서도 호출은 정상적으로 반환됩니다. 이렇게 거절된 단일 record write(예: hot key에 대한 `put()`)는 해당 `result_code`, `"KeyBusy"`·`"DeviceOverload"`·`"PartitionUnavailable"` 중 하나인 `error_type`, `in_doubt == False`를 가진 `ServerError`를 발생시킵니다. `max_retries > 0`으로 보낸 write batch의 `PARTITION_UNAVAILABLE` row는 in doubt일 수 있습니다. [다시 보낸 write와 `in_doubt`](#re-sent-writes-and-in_doubt)를 참고하세요.

### Batch 전체가 실패할 때

전체가 실패한 batch 호출(예: 일부 key를 가진 node가 응답을 멈춤)은 이전처럼 exception을 발생시키고, 그 exception이 row를 담고 있습니다. `exc.partial_result`는 요청한 record마다 `BatchRecord` 하나를 요청 순서대로 담은 `BatchWriteResult`입니다. 다른 node가 응답한 record는 결과를 그대로 갖고, 나머지는 결과가 없는 이유를 알려 줍니다. 모든 batch method가 이 값을 채웁니다: `batch_read`, `batch_write`, `batch_write_numpy`, `batch_operate`, `batch_remove`, `batch_apply`.

`partial_result`의 row 중 하나라도 in doubt이면 exception도 `in_doubt == True`입니다. 호출이 여러 node에서 실패했다면 exception은 그중 한 node의 오류(몫이 처음 실패한 node)이므로, exception의 type과 `result_code`는 record 순서에 따라 달라질 수 있습니다. 판단은 각 record에 무슨 일이 있었는지 알려 주는 row로 하세요.

```python
from aerospike_py.exception import AerospikeError

try:
    results = client.batch_write(records)
except AerospikeError as exc:
    if exc.partial_result is None:
        raise  # 아무것도 시도하기 전에 거부됨 (예: 잘못된 policy 값)
    rows = exc.partial_result.batch_records
    written = [br.key for br in rows if br.result == 0]
    unsure = [br.key for br in rows if br.in_doubt]           # 다시 보내기 전에 읽어서 확인
    not_sent = [br.key for br in rows if br.error_type == "NoResponse" and not br.in_doubt]
    logger.warning("batch failed: %d written, %d in doubt, %d never sent",
                   len(written), len(unsure), len(not_sent))
```

`batch_write(..., retry=N)`이 exception을 발생시키면 `exc.partial_result.retry`에 그 호출의 retry counter가 들어 있습니다.

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
Exponential backoff로 transient failure를 자동으로 retry하려면 내장 `retry` 파라미터를 사용하세요: `client.batch_write(records, retry=3)`. 실패한 record만 다시 보내며, 이미 성공한 record나 `in_doubt`인 `CREATE_ONLY`·generation 검사 record는 다시 보내지 않습니다. `total_timeout`(기본값 1000 ms)이 상한이고, 0이 아닌 `policy["max_retries"]`와 함께 쓰면 `InvalidArgError`가 발생합니다. Write batch(`batch_write`, `batch_write_numpy`, `batch_remove`, `batch_apply`, write가 있는 `batch_operate`)는 스스로 아무것도 다시 보내지 않습니다. 이들의 `max_retries` 기본값은 `0`입니다.
:::

### 다시 보낸 write와 `in_doubt` {#re-sent-writes-and-in_doubt}

기본적으로 write는 다시 보내지 않습니다. 모든 write의 `max_retries`는 `0`입니다. Write에 `max_retries > 0`을 주면, 응답이 유실되었을 때 Rust client가 write를 다시 보냅니다. 첫 전송이 이미 적용되었다면 두 번째 전송은 자기가 한 일을 만납니다. 다시 보낸 delete는 record를 찾지 못하고, 다시 보낸 filter 있는 write는 더 이상 조건에 맞지 않으며, 다시 보낸 UDF는 첫 실행이 남긴 상태 때문에 실패합니다. Rust client는 row가 두 번 전송되었는지 알려 주지 않으므로, 이런 policy에서는 다음과 같습니다.

- `batch_write`, write가 있는 `batch_operate`, `batch_remove`, `batch_apply`의 row가 `KEY_NOT_FOUND`(2), `FILTERED_OUT`(27), `UDF_BAD_RESPONSE`(100)로 끝나면 `in_doubt == True`입니다.
- 이 호출들의 row 중, node 몫을 다시 보낼 때가 되었는데 그 record의 node를 찾지 못해(그사이 node가 cluster에서 빠졌거나 client가 닫힘) client가 직접 `PARTITION_UNAVAILABLE`(11)을 준 row도 그렇습니다. 첫 전송이 적용되었을 수 있습니다. 첫 전송에서 server가 `PARTITION_UNAVAILABLE`로 거절한 row는 여전히 `in_doubt == False`입니다.
- `RecordNotFound`를 발생시킨 `remove()`는 `in_doubt == True`를 갖습니다.

호출이 record를 바꿨는지 알 수 없고, 그렇다고 알려 주는 것입니다. 이런 row가 있어도 호출은 정상적으로 반환됩니다. 기본 policy에서는 아무것도 바뀌지 않고, 읽기(`batch_read`)는 결코 in doubt가 아닙니다.

다루지 못하는 경우가 하나 있습니다. `max_retries > 0`인 단일 record write(`put()`, `remove()`, `operate()` 등)가 다시 보내지기를 기다리는 동안 client가 닫히면, 첫 전송이 적용되었을 수 있는데도 `in_doubt == False`인 `InvalidArgError`("Partition map empty")가 발생합니다. Node가 다운된 경우는 이 경로를 타지 않습니다. 이때는 시도 횟수가 다 소진되고 오류는 in doubt입니다. 진행 중인 write가 있는 client는 닫지 마세요.

```python
import aerospike_py

result = client.batch_remove(keys, policy={"max_retries": 2})
for br in result.batch_records:
    if br.result == aerospike_py.AEROSPIKE_ERR_RECORD_NOT_FOUND and br.in_doubt:
        ...  # 이 호출의 앞선 전송이 지웠거나, 원래 없었음: 읽어서 확인
```

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
| `max_retries` | `int` | read `2` / write `0` | 최대 retry 횟수. Write의 기본값은 `0`입니다. 아래 note를 참고하세요. Batch도 같은 규칙을 따릅니다: `batch_read`와 읽기만 하는 `batch_operate`는 `2`, write·삭제·UDF를 실행하는 batch는 모두 `0`. |
| `sleep_between_retries` | `int` | `0` | retry 간 지연 (ms) |

:::warning[Write는 기본적으로 retry하지 않습니다]
`ReadPolicy`의 `max_retries` 기본값은 `2`이지만 `WritePolicy`의 기본값은 **`0`** 입니다. `increment()`, `append()`, `prepend()`, increment op가 있는 `operate()`, 임의의 UDF를 실행하는 `apply()`는 **idempotent하지 않습니다**. Server가 이미 commit한 write에 client 쪽 timeout이 잘못 발생해 retry하면, counter가 더 많이 증가하거나 문자열이 두 번 붙습니다. 아무 알림 없이 일어납니다.

`0` 기본값은 idempotent한 `put()`, `remove()`, `touch()`, `remove_bin()`을 포함해 `WritePolicy`를 받는 *모든* operation에 적용됩니다. Operation별 표보다 하나의 기본값이 이해하기 쉽기 때문입니다. 이 네 operation에서 복원력이 필요하면 명시적으로 켜세요.

```python
client.remove(key, policy={"max_retries": 2})
client.put(key, bins, policy={"max_retries": 2})  # 전체 bin 덮어쓰기는 idempotent
```

`max_retries > 0`일 때 `RecordNotFound`를 발생시킨 `remove()`는 `in_doubt == True`를 갖습니다. 앞선 전송이 record를 지웠을 수 있기 때문입니다. [다시 보낸 write와 `in_doubt`](#re-sent-writes-and-in_doubt)를 참고하세요.
:::

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
| 20 | `AEROSPIKE_ERR_INVALID_NAMESPACE` | (cluster에 없는 namespace에 속한 key의 batch row. 단일 record 명령은 `InvalidArgError` 발생) |
| 21 | `AEROSPIKE_ERR_BIN_NAME` | `BinNameError` |
| 27 | `AEROSPIKE_ERR_FILTERED_OUT` | `FilteredOut` |
| 100 | `AEROSPIKE_ERR_UDF` | `UDFError` |
| 200 | `AEROSPIKE_ERR_INDEX_FOUND` | `IndexFoundError` |
| 201 | `AEROSPIKE_ERR_INDEX_NOT_FOUND` | `IndexNotFound` |
| 210 | `AEROSPIKE_ERR_QUERY_ABORTED` | `QueryAbortedError` |
| -1 | — | 어떤 server도 응답하지 않음. `error_type` 참고 |

전체 list 는 [Exceptions API Reference](../../api/exceptions.md) 와 [Constants](../../api/constants.md) 참조.
