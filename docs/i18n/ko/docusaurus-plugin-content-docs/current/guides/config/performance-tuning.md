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
    "max_conns_per_node": 300,   # 기본값: 256
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

## 동시성 및 Backpressure 튜닝

고동시성 Python 서비스(FastAPI, Gunicorn 워커, Celery 팬아웃)는
`aerospike-py` 하부의 두 계층을 포화시킬 수 있습니다:

1. Rust 비동기 클라이언트를 구동하는 **내부 Tokio 런타임**.
2. Aerospike 서버에 대한 **노드별 커넥션 풀**.

증상에 따라 적절한 튜닝 노브를 선택하세요. 두 노브는 독립적입니다.

### `AEROSPIKE_RUNTIME_WORKERS` (환경 변수)

내장 비동기 런타임이 사용하는 Tokio 워커 스레드 수를 제어합니다. **기본값: `2`**.
CPU 집약적 워크로드(PyTorch 추론, sklearn 등)와 함께 배치되었을 때
CPU 오버헤드를 낮게 유지합니다.

```bash
# 동시 FastAPI 요청 10개 이상이 각각 batch_read를 호출하고
# `spawn_blocking` 큐 정체가 관측될 때 워커 수를 늘리세요.
export AEROSPIKE_RUNTIME_WORKERS=4
```

| 워커 수 | 사용 사례 |
|---------|----------|
| `2` (기본값) | 대부분의 애플리케이션, ML 서빙, 단일 테넌트 웹 서버 |
| `4` | 동시 batch_read 팬아웃, 진행 중 요청이 많은 FastAPI |
| `4–8` | 고처리량 파이프라인, 프로세스당 `--workers >= 4`인 Gunicorn |
| `8+` | 거의 필요 없음 — 먼저 `py-spy`/`tokio-console`로 프로파일링하세요 |

**"워커를 늘리라"는 신호:**

- 클러스터 측 메트릭은 정상인데 진행 중 호출이 10개를 초과할 때
  `await client.batch_read(...)`의 p99 지연 시간이 급격히 상승.
- `tokio-console`(또는 Tokio 런타임 메트릭)에서 부하 시 큐 깊이가
  무한정 증가.

이 환경 변수는 **런타임 초기화 시점에 한 번만 읽힙니다**(첫
`AsyncClient.connect()`). 런타임이 기동된 뒤 변경해도 효과가
없으므로, `aerospike_py`를 import하기 전에 설정하세요.

### `max_concurrent_operations` (클라이언트 설정)

매 순간 Rust 클라이언트로 디스패치되는 진행 중 작업 수의 상한을 둡니다.
**기본값은 비활성화**(`0`, 오버헤드 없음). 값을 설정하면 초과 호출자는
실패하거나 커넥션 풀을 고갈시키는 대신 슬롯을 **대기**합니다.

```python
config = {
    # "aerospike" = Podman/compose 파일의 서비스 이름; 로컬 개발에서는 127.0.0.1을 사용하세요
    "hosts": [("aerospike", 3000)],
    "max_concurrent_operations": 64,    # 동시에 진행 중인 작업은 최대 64개
    "operation_queue_timeout_ms": 5000, # 5초 후 BackpressureError 발생
}
```

활성화 시 동작:

- 한도를 초과한 작업은 빈 슬롯을 **대기**합니다.
- 이전 작업이 완료되는 즉시 대기 중 작업이 재개됩니다.
- 슬롯이 비기 전에 `operation_queue_timeout_ms`가 만료되면
  `aerospike_py.BackpressureError`가 발생합니다.

**값 선정:** `max_conns_per_node`(기본값 `256`)에 가깝되 그 이상은
넘지 않도록 설정합니다. 3노드 클러스터의 경우 `64`가 풀 고갈을 막으면서
처리량을 유지하는 보수적인 출발점입니다.

**활성화 시점:** `spawn_blocking` 큐가 정체될 가능성이 있는 고-팬아웃
배치 읽기, 또는 상위 호출자(부하 테스트 중인 FastAPI)가 커넥션 풀이
처리할 수 있는 것보다 더 많은 동시 작업을 발생시킬 수 있을 때.

### 적용 전/후 비교

```python
# Before: 동시에 batch_read를 호출하는 100개의 FastAPI 요청은
# 기본 워커 2개와 캡 미설정 상태에서 Tokio 큐에 적체될 수 있습니다.

# After (환경 변수): export AEROSPIKE_RUNTIME_WORKERS=4
# 그리고 (코드):
import aerospike_py

client = aerospike_py.AsyncClient({
    # "aerospike" = Podman/compose 파일의 서비스 이름; 로컬 개발에서는 127.0.0.1을 사용하세요
    "hosts": [("aerospike", 3000)],
    "max_concurrent_operations": 64,    # 진행 중 작업 수 캡
    "operation_queue_timeout_ms": 5000,
})
await client.connect()
```

### FastAPI / Gunicorn 권장 설정

`uvicorn` 워커 위에서 Gunicorn으로 배포되는 FastAPI 서비스의 경우
(`examples/sample-fastapi/` 참조):

| 설정 | 권장 시작값 | 비고 |
|------|------------|------|
| `AEROSPIKE_RUNTIME_WORKERS` | `4` | 코드가 아닌 배포 환경 변수에 설정. |
| `max_concurrent_operations` | `64` | `AsyncClient` 인스턴스당, 워커 프로세스당. |
| `operation_queue_timeout_ms` | `5000` | FastAPI 요청 타임아웃과 짝을 이루도록 설정. |
| Gunicorn `--workers` | `2 * CPU` | 각 워커마다 자체 클라이언트 + Tokio 런타임. |
| `max_conns_per_node` | `256` | `max_concurrent_operations`보다 충분히 높게 유지. |

위 값을 사용한 단일 Gunicorn 워커는 풀을 고갈시키지 않고도 동시 진행
중인 Aerospike 작업 ~64개를 유지할 수 있습니다. 클러스터 전체 부하 =
`gunicorn_workers * max_concurrent_operations`이므로 이에 맞춰 사이징하세요.

## Async Client

고동시성 워크로드(웹 서버, 팬아웃 읽기)에 적합합니다:

```python
import asyncio

async def main() -> None:
    client = aerospike.AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "max_concurrent_operations": 64,  # 풀 고갈 방지
    })
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

## 타임아웃 가이드라인

| 설정 | 권장 사항 |
|------|----------|
| `socket_timeout` | 1-5초. 응답 없는 연결을 감지합니다. |
| `total_timeout` | SLA에 맞게 설정. 재시도를 포함합니다. |
| `max_retries` | 읽기는 2-3회, 쓰기는 0회 (멱등성 고려). |
