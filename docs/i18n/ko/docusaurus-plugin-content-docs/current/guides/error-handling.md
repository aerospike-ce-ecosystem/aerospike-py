---
title: 에러 처리
sidebar_label: 에러 처리
sidebar_position: 7
description: 프로덕션 애플리케이션에서 Aerospike 에러를 처리하는 모범 사례
---

# 에러 처리 가이드

## 예외 계층 구조

모든 aerospike-py 예외는 `AerospikeError`를 상속합니다. 전체 계층 구조와
설명은 [Exceptions API 레퍼런스](../api/exceptions.md)를 참고하세요.

```python
import aerospike_py as aerospike
from aerospike_py import exception
```

## 권장 패턴

### 구체적 예외를 먼저, 그다음 포괄적 예외

항상 가장 구체적인 예외부터 캐치하세요:

```python
from aerospike_py.exception import (
    RecordNotFound,
    AerospikeTimeoutError,
    AerospikeError,
)

try:
    _, meta, bins = client.get(key)
except RecordNotFound:
    # 레코드 미존재 처리 (예: 기본값 반환)
    bins = {}
except AerospikeTimeoutError:
    # 재시도 또는 서킷 브레이커
    raise
except AerospikeError as e:
    # 예상치 못한 Aerospike 에러
    logger.error("Aerospike error: %s", e)
    raise
```

### 백오프를 적용한 재시도

타임아웃 및 클러스터 에러는 일시적인 경우가 많습니다:

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
            time.sleep(0.1 * (2 ** attempt))  # 지수 백오프
```

### Optimistic Locking (Check-and-Set)

세대(generation) 검사를 사용하여 동시 수정을 감지합니다:

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
                meta={"gen": meta["gen"]},
                policy={"gen": aerospike.POLICY_GEN_EQ},
            )
            return new_val
        except RecordGenerationError:
            continue  # 최신 데이터로 재시도
```

### Upsert vs Create-Only

```python
from aerospike_py.exception import RecordExistsError

# Create-only: 레코드가 존재하면 실패
try:
    client.put(key, bins, policy={"exists": aerospike.POLICY_EXISTS_CREATE_ONLY})
except RecordExistsError:
    print("레코드가 이미 존재합니다, 건너뜁니다")

# Upsert (기본값): 생성 또는 업데이트
client.put(key, bins)  # RecordExistsError가 발생하지 않음
```

### 배치 에러 처리

배치 작업은 키별로 결과를 반환합니다. 개별 레코드 상태를 확인하세요:

```python
results = client.batch_read(keys)
for result in results:
    if result.result_code == aerospike.AEROSPIKE_OK:
        process(result.bins)
    elif result.result_code == aerospike.AEROSPIKE_ERR_RECORD_NOT_FOUND:
        handle_missing(result.key)
    else:
        logger.warning("배치 키 에러: code=%d", result.result_code)
```

### 연결 라이프사이클

```python
from aerospike_py.exception import ClientError, ClusterError

client = aerospike.client(config)
try:
    client.connect()
except ClusterError as e:
    print(f"클러스터에 연결할 수 없습니다: {e}")
    raise SystemExit(1)

try:
    # ... 애플리케이션 로직 ...
    pass
finally:
    client.close()
```

### 비동기 에러 처리

비동기 에러도 동일한 방식으로 작동하며, `await`만 추가됩니다:

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

## 결과 코드

예외에 매핑되는 주요 Aerospike 결과 코드:

| 코드 | 상수 | 예외 |
|------|----------|-----------|
| 0 | `AEROSPIKE_OK` | (성공) |
| 2 | `AEROSPIKE_ERR_RECORD_NOT_FOUND` | `RecordNotFound` |
| 5 | `AEROSPIKE_ERR_RECORD_EXISTS` | `RecordExistsError` |
| 9 | `AEROSPIKE_ERR_TIMEOUT` | `AerospikeTimeoutError` |
| 3 | (세대 에러) | `RecordGenerationError` |
| 13 | (레코드 너무 큼) | `RecordTooBig` |
| 27 | (필터링됨) | `FilteredOut` |

전체 목록은 [상수 레퍼런스](../api/constants.md)를 참고하세요.
