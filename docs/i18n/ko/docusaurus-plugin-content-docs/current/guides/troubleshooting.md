---
sidebar_position: 10
title: 문제 해결
description: aerospike-py 사용 중 발생하는 일반적인 문제와 해결 방법
---

# 문제 해결

이 문서에서는 자주 발생하는 aerospike-py error의 원인을 확인하고 해결 방법을 안내합니다.

## 연결 문제

### ClusterError: Failed to connect

**증상:**

```python
aerospike_py.ClusterError: Failed to connect to host(s)
```

**원인:**
- Aerospike server 가 실행 중이 아님
- client 설정의 host 또는 port 가 틀림
- 방화벽이 연결을 차단
- cluster name mismatch

**해결책:**

1. Aerospike server 가 실행 중인지 확인:
   ```bash
   # Podman 사용 시
   podman ps | grep aerospike

   # port 가 열려 있는지 확인
   nc -zv 127.0.0.1 3000
   ```

2. 설정 재확인:
   ```python
   client = aerospike_py.client({
       "hosts": [("127.0.0.1", 3000)],     # host 와 port 확인
       "cluster_name": "my-cluster",         # server 설정과 일치해야 함
   }).connect()
   ```

3. Aerospike를 container에서 실행한다면 service port가 올바르게 mapping되었고 host에서 접근할 수 있는지 확인하세요.

### AerospikeTimeoutError

**증상:**

```python
aerospike_py.AerospikeTimeoutError: Operation timed out
```

**원인:**
- client 와 server 사이 네트워크 latency
- server 가 과부하 또는 응답 없음
- workload 에 비해 default timeout 이 너무 짧음

**해결책:**

1. Timeout이 필요한 호출에 operation policy를 지정합니다.
   ```python
   read_policy = {
       "socket_timeout": 5_000,
       "total_timeout": 5_000,
   }
   record = client.get(key, policy=read_policy)
   ```

   `ClientConfig.timeout`은 최초 connection timeout을 제어합니다. Read와 write
   timeout은 각 operation의 policy에 지정해야 하며, `ClientConfig`에는 전역
   `policies` field가 없습니다.

2. server 상태 확인:
   ```python
   info = client.info_all("status")
   print(info)  # (node_name, error_code, response) tuple 의 list 반환
   ```

### BackpressureError

**증상:**

```python
aerospike_py.BackpressureError: Operation queue timeout after 5000ms: max_concurrent_operations=64 exceeded
```

**원인:**
- workload 에 비해 `max_concurrent_operations` 가 너무 낮게 설정
- `operation_queue_timeout_ms` 가 너무 짧음
- server 가 느려서 operation 이 slot 을 더 오래 점유

**해결책:**

1. 동시성 한도 증가:
   ```python
   config = {
       "hosts": [("127.0.0.1", 3000)],
       "max_concurrent_operations": 128,  # 64 에서 증가
   }
   ```

2. timeout 증가:
   ```python
   config = {
       "hosts": [("127.0.0.1", 3000)],
       "max_concurrent_operations": 64,
       "operation_queue_timeout_ms": 10000,  # 10초
   }
   ```

3. `operation_queue_timeout_ms` 를 `0` 으로 설정해 무기한 대기 (timeout error 없음, 다만 operation 이 block 될 수 있음):
   ```python
   config = {
       "hosts": [("127.0.0.1", 3000)],
       "max_concurrent_operations": 64,
       "operation_queue_timeout_ms": 0,  # 영원히 대기
   }
   ```

### "Client not connected" 오류

**증상:**

```python
aerospike_py.ClientError: Client is not connected
```

**원인:**
- `connect()` 가 호출된 적 없음
- 연결이 끊어진 (예: server 재시작) 뒤 재연결되지 않음
- operation 전에 `close()` 가 호출됨

**해결책:**

1. operation 수행 전 항상 `connect()` 호출:
   ```python
   client = aerospike_py.client(config).connect()
   ```

2. context manager 로 적절한 lifecycle 보장:
   ```python
   with aerospike_py.client(config).connect() as client:
       record = client.get(key)
   # client.close() 가 자동 호출
   ```

3. async 코드의 경우:
   ```python
   client = aerospike_py.AsyncClient(config)
   await client.connect()
   try:
       record = await client.get(key)
   finally:
       await client.close()
   ```

   또는 `close()` 를 자동 await 해주는 async context manager:
   ```python
   async with aerospike_py.AsyncClient(config) as client:
       await client.connect()
       record = await client.get(key)
   ```

## Build / Installation 문제

### Build 실패 (maturin)

**증상:**

```
error: can't find Rust compiler
# 또는
ERROR: Failed building wheel for aerospike-py
```

**원인:**
- Rust toolchain 미설치
- 호환되지 않는 Rust 버전
- 시스템 dependency 누락

**해결책:**

1. 대부분의 사용자는 PyPI의 pre-built wheel을 설치하면 됩니다.
   ```bash
   pip install aerospike-py
   ```

2. 소스에서 빌드 시 Rust toolchain 설치:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   rustup default stable
   ```

3. 호환 Python 버전 확인 (3.10+, CPython only):
   ```bash
   python --version  # 3.10 이상
   ```

4. 개발 빌드:
   ```bash
   pip install maturin
   maturin develop --release
   ```

### ImportError: Native Module Not Found

**증상:**

```python
ImportError: cannot import name '_aerospike' from 'aerospike_py'
# 또는
ModuleNotFoundError: No module named 'aerospike_py._aerospike'
```

**원인:**
- 패키지가 제대로 설치되지 않음
- `maturin develop` 없이 소스에서 빌드
- CPython 대신 PyPy 사용 (미지원)

**해결책:**

1. PyPI 에서 설치:
   ```bash
   pip install aerospike-py
   ```

2. 로컬 개발 시 native module 재빌드:
   ```bash
   maturin develop --release
   ```

3. CPython 사용 중인지 확인:
   ```bash
   python -c "import platform; print(platform.python_implementation())"
   # CPython 출력되어야 함
   ```

## 런타임 문제

### NumPy 관련 오류

**증상:**

```python
ImportError: numpy is required for batch_read_numpy
# 또는
TypeError: numpy dtype mismatch
```

**원인:**
- NumPy 미설치
- NumPy 버전 비호환 (>= 2.0 필요)

**해결책:**

1. NumPy extra 설치:
   ```bash
   pip install "aerospike-py[numpy]"
   ```

2. NumPy 버전 확인:
   ```bash
   python -c "import numpy; print(numpy.__version__)"
   # 2.0 이상
   ```

3. dtype field 가 Aerospike 에 저장된 bin 타입과 일치하는지 확인:
   ```python
   import numpy as np

   dtype = np.dtype([
       ("_key", "U64"),    # string key
       ("score", "f8"),    # float bin
       ("count", "i4"),    # integer bin
   ])
   results = client.batch_read(keys, bins=["score", "count"]).to_numpy(dtype)
   ```

### OpenTelemetry Tracing 동작 안 함

**증상:**
- collector (Jaeger, Zipkin 등) 에 trace 안 보임
- `init_tracing()` 이 error 없이 실행되지만 span 이 export 안 됨

**원인:**
- OpenTelemetry SDK 미설치
- OTLP exporter 미설정
- collector 가 실행 중이 아니거나 도달 불가

**해결책:**

1. OTel extra 설치:
   ```bash
   pip install "aerospike-py[otel]"
   ```

2. application 에서 tracing 초기화:
   ```python
   from aerospike_py import init_tracing, shutdown_tracing

   init_tracing()
   ```

3. 환경변수로 OTLP endpoint 설정:
   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
   export OTEL_SERVICE_NAME="my-service"
   ```

4. collector (예: Jaeger, Grafana Tempo) 가 실행 중이고 설정된 port 의 OTLP gRPC 를 수락하는지 확인.

5. application exit 전 항상 `shutdown_tracing()` 호출해 pending span flush.

### Prometheus Metric 안 나타남

**증상:**
- `get_metrics()` 가 비어있거나 histogram 데이터 없음
- metric server 가 데이터 반환 안 함

**해결책:**

1. metric 활성 여부 확인:
   ```python
   from aerospike_py import is_metrics_enabled, set_metrics_enabled

   print(is_metrics_enabled())  # True 이어야 함
   set_metrics_enabled(True)    # 비활성이면 활성화
   ```

2. operation 을 먼저 수행 — metric 은 operation 실행 후에만 기록됨.

3. 내장 metric server 사용 시:
   ```python
   from aerospike_py import start_metrics_server

   start_metrics_server(9090)
   # 그 다음 http://localhost:9090/metrics 방문
   ```

## Python 3.14t (Free-Threaded) 노트

aerospike-py는 Python 3.14t free-threaded build를 지원합니다. 다음 사항을 확인하세요.

- **Experimental 지원**: Free-threaded Python은 아직 CPython의 experimental 기능입니다. 일부 third-party library가 올바르게 동작하지 않을 수 있습니다.
- **Thread safety**: aerospike-py의 `Client`와 `AsyncClient`는 thread-safe합니다. Rust client가 내부 synchronization을 처리합니다.
- **Performance 특성**: GIL이 없으면 Python thread를 병렬로 실행할 수 있습니다. Workload에 따라 Tokio runtime worker 수(`AEROSPIKE_RUNTIME_WORKERS`)를 조정해야 할 수 있습니다.

free-threaded Python 특화 문제 발생 시:

1. 표준 CPython 빌드로 fallback 해 문제 isolate.
2. 알려진 free-threaded 호환성 문제는 [GitHub issue](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues) 확인.

## 도움 요청

이 문서에 없는 문제는:

1. 기존 신고는 [GitHub Issues](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues) 에서 확인.
2. 새 issue 등록 시 포함:
   - Python 버전 (`python --version`)
   - aerospike-py 버전 (`python -c "import aerospike_py; print(aerospike_py.__version__)"`)
   - OS 와 architecture
   - 전체 error traceback
   - 최소 재현 코드
