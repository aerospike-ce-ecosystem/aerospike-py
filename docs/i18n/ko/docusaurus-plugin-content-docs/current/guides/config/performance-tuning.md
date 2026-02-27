---
title: 성능 튜닝
sidebar_label: 성능 튜닝
sidebar_position: 2
slug: /guides/performance-tuning
description: aerospike-py의 처리량과 지연 시간을 최적화하는 방법
---

## 커넥션 풀

```python
config = {
    "hosts": [("node1", 3000), ("node2", 3000)],
    "max_conns_per_node": 300,   # 기본값: 100
    "min_conns_per_node": 10,    # 사전 워밍
    "idle_timeout": 55,          # 서버 proto-fd-idle-ms(60초)보다 낮게 설정
}
```

## 읽기 최적화

### 특정 Bin만 선택

```python
# 서버에서 모든 bin을 읽음
record = client.get(key)

# 필요한 것만 읽음 (네트워크 I/O 감소)
record = client.select(key, ["name", "age"])
```

### 배치 읽기 사용

```python
# N번의 순차적 왕복
results = [client.get(k) for k in keys]

# 단일 왕복
batch = client.batch_read(keys, bins=["name", "age"])
```

### NumPy 배치 읽기

수치 워크로드의 경우, Python dict 오버헤드를 완전히 건너뛸 수 있습니다:

```python
import numpy as np

dtype = np.dtype([("score", "i8"), ("rating", "f8")])
batch = client.batch_read(keys, bins=["score", "rating"], _dtype=dtype)
# batch.batch_records는 numpy 구조화 배열입니다
```

자세한 내용은 [NumPy 배치 가이드](../crud/numpy-batch.md)를 참조하세요.

## 쓰기 최적화

### 연산 결합

```python
# 두 번의 왕복
client.put(key, {"counter": 1})
client.put(key, {"updated_at": now})

# 단일 왕복
ops = [
    {"op": aerospike.OPERATOR_WRITE, "bin": "counter", "val": 1},
    {"op": aerospike.OPERATOR_WRITE, "bin": "updated_at", "val": now},
]
client.operate(key, ops)
```

### TTL 전략

```python
client.put(key, bins, meta={"ttl": aerospike.TTL_NEVER_EXPIRE})     # 만료하지 않음
client.put(key, bins, meta={"ttl": aerospike.TTL_DONT_UPDATE})      # 기존 TTL 유지
client.put(key, bins, meta={"ttl": aerospike.TTL_NAMESPACE_DEFAULT}) # 네임스페이스 기본값 사용
```

## Async Client

고동시성 워크로드(웹 서버, 팬아웃 읽기)에 적합합니다:

```python
import asyncio

async def main() -> None:
    client = aerospike.AsyncClient({"hosts": [("127.0.0.1", 3000)]})
    await client.connect()

    keys = [("test", "demo", f"key{i}") for i in range(1000)]
    results = await asyncio.gather(*(client.get(k) for k in keys))

    await client.close()
```

## Expression 필터

필터링을 서버에 위임하여 네트워크 전송량을 줄입니다:

```python
from aerospike_py import exp

# 필터 없이: 모든 레코드를 전송 후 Python에서 필터링
results = client.query("test", "demo").results()
active = [r for r in results if r.bins.get("active")]

# 필터 사용: 서버에서 일치하는 레코드만 반환
expr = exp.eq(exp.bool_bin("active"), exp.bool_val(True))
results = client.query("test", "demo").results(policy={"filter_expression": expr})
```

## Tokio 런타임 워커

aerospike-py는 기본적으로 **워커 스레드 2개**의 내부 Tokio 비동기 런타임을 사용합니다.
I/O 바운드 데이터베이스 작업에는 이 설정으로 충분하며, CPU 집약적 워크로드(예: PyTorch 추론)와
함께 실행할 때 CPU 오버헤드를 최소화합니다.

```bash
# 대량 배치 작업에 더 많은 병렬성이 필요한 경우 조정
export AEROSPIKE_RUNTIME_WORKERS=4
```

| 워커 수 | 사용 사례 |
|---------|----------|
| 2 (기본값) | 대부분의 애플리케이션, ML 서빙, 웹 서버 |
| 4 | 대량 배치 작업, 고처리량 파이프라인 |
| 8+ | 거의 필요 없음; 먼저 프로파일링할 것 |

## 타임아웃 가이드라인

| 설정 | 권장 사항 |
|------|----------|
| `socket_timeout` | 1-5초. 응답 없는 연결을 감지합니다. |
| `total_timeout` | SLA에 맞게 설정. 재시도를 포함합니다. |
| `max_retries` | 읽기는 2-3회, 쓰기는 0회 (멱등성 고려). |
