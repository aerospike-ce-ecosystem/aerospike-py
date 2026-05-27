---
sidebar_position: 99
title: FAQ
description: Frequently asked questions about aerospike-py.
---

## aerospike-py 는 왜 Rust 로 작성되었나요?

aerospike-py 는 [PyO3](https://pyo3.rs/) bindings 으로 [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust) 를 wrap 합니다. 순수 Python 이나 C-extension 접근 대비 다음 이점이 있습니다:

- **Performance** — Rust 는 native code 로 컴파일됩니다. 벤치마크에 따르면 throughput 이 공식 C 기반 client 와 동등하거나 그 이상, 특히 batch 와 async workload 에서 두드러집니다.
- **Memory safety** — Rust 의 ownership 모델이 use-after-free, buffer overflow, data race 같은 광범위한 버그 종류를 garbage collector 없이 제거합니다.
- **Native async** — 내부 client 가 production-grade async runtime 인 Tokio 위에 빌드됩니다. `AsyncClient` 가 후순위가 아닌 first-class 시민입니다.
- **Zero Python dependencies** — base install (`pip install aerospike-py`) 은 외부 Python dependency 가 없습니다. NumPy 와 OpenTelemetry 는 선택적 extras 입니다.

## GIL 처리는 어떻게 되나요?

aerospike-py 는 모든 데이터베이스 I/O 동안 Python GIL (Global Interpreter Lock) 을 release 하므로, 한 request 가 in-flight 인 동안 다른 Python thread 들이 진행할 수 있습니다.

| Client | Mechanism |
|--------|-----------|
| **Sync `Client`** | `py.detach()` 가 GIL 을 release 한 뒤 `RUNTIME.block_on()` 이 내부 Tokio runtime 위에서 async Rust operation 을 실행. 결과 반환 시 GIL 재획득. |
| **Async `AsyncClient`** | `future_into_py()` 가 Python awaitable 을 반환. 실제 작업은 Tokio runtime 위에서 GIL 없이 실행. future 완료 시 `Python::attach()` 가 GIL 을 재획득해 결과 전달. |

두 경우 모두, request 가 Aerospike cluster 로 이동하는 동안 GIL 이 **유지되지 않습니다** — 즉 Python thread (또는 다른 async task) 가 자유롭게 동시 실행 가능.

## aerospike-py 는 thread-safe 한가요?

네. 단일 `Client` 인스턴스를 여러 thread 에서 안전하게 공유할 수 있습니다. Rust client 가 내부적으로 connection pool 을 관리하며, 모든 공유 상태는 lock-free 또는 mutex-guarded 구조로 보호됩니다.

```python
import threading
import aerospike_py

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment

def worker(thread_id: int) -> None:
    key = ("test", "demo", f"thread_{thread_id}")
    client.put(key, {"tid": thread_id})
    record = client.get(key)
    assert record.bins["tid"] == thread_id

threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
for t in threads:
    t.start()
for t in threads:
    t.join()
client.close()
```

## Python free-threaded mode (3.14t) 를 지원하나요?

네. aerospike-py 는 experimental free-threaded CPython (PEP 703) 위에서 빌드되고 실행됩니다. CI 가 Python 3.14t 에서 unit test **및** concurrency stress test 를 돌려 GIL 없이도 정확성을 검증합니다.

핵심 로직이 Rust 에 있기 때문에 — Rust 자체 memory safety 보장 덕에 — GIL 이 완전히 제거되어도 라이브러리는 본질적으로 안전합니다.

## NumPy 는 필수인가요?

아니요. NumPy 는 **선택적** dependency 입니다.

```bash
# Base install — NumPy 불필요
pip install aerospike-py

# NumPy 지원 포함
pip install aerospike-py[numpy]
```

NumPy 가 설치되어 있으면 `LazyBatchRecords.to_numpy(dtype)` (즉 `batch_read()` 반환값) 사용 가능 — NumPy structured array 로 backed 된 `NumpyBatchRecords` 를 생성하며, buffer fill 이 GIL released 상태로 실행되므로 결과를 `torch.from_numpy(...)` 에 zero-copy 로 바로 넘길 수 있습니다. `batch_write_numpy()` 가 structured array 로부터의 bulk write 방향 (역방향) 을 처리합니다. 다른 모든 기능은 NumPy 없이도 동일하게 동작합니다.

## 공식 C client 에서 migrate 가능한가요?

네. aerospike-py 는 near-drop-in replacement 로 설계되었습니다. import alias 패턴으로 전환이 직관적:

```python
# Before
import aerospike

# After
import aerospike_py as aerospike
```

대부분의 API 시그니처, 상수, exception class, policy dict 가 호환됩니다. 단계별 walkthrough 는 [Migration Guide](/docs/guides/migration), 자세한 비교표는 [API Comparison](/docs/guides/api-comparison) 참조.

## OpenTelemetry tracing 은 어떻게 활성화하나요?

Tracing 지원은 모든 빌드에 컴파일되어 있습니다. 활성화:

```bash
pip install aerospike-py[otel]   # context propagation 을 위한 opentelemetry-api 추가
```

```python
import aerospike_py

# client 생성 전 초기화
aerospike_py.init_tracing()

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment
# ... 모든 operation 이 자동으로 traced ...
client.close()

# exit 전 pending span flush
aerospike_py.shutdown_tracing()
```

Span 은 OTLP gRPC 로 export (기본 endpoint `http://localhost:4317`). 표준 `OTEL_*` 환경변수로 설정. 자세한 내용은 [Tracing guide](/docs/integrations/observability/tracing) 참조.

## Prometheus metrics 는 어떻게 활성화하나요?

aerospike-py 는 내장 Prometheus metrics HTTP server 를 ships 합니다:

```python
import aerospike_py

# port 9464 에서 metrics server 시작
aerospike_py.start_metrics_server(9464)

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment
# ... operation 이 자동으로 metered ...
client.close()

aerospike_py.stop_metrics_server()
```

Prometheus 에서 `http://localhost:9464/metrics` 를 scrape. operation type 별 latency histogram 이 기록됩니다. 자세한 내용은 [Metrics guide](/docs/integrations/observability/metrics) 참조.

## 어떤 Aerospike server 버전을 지원하나요?

aerospike-py 는 **Aerospike Server 6.x 와 7.x** (Community 및 Enterprise) 에 대해 테스트됩니다. Aerospike Rust Client v2.0.0-alpha.9 위에 빌드됨.

## bug 신고 또는 기능 요청은 어떻게 하나요?

GitHub 저장소에 issue 를 등록하세요:

- **Bug report:** [github.com/aerospike-ce-ecosystem/aerospike-py/issues/new](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/new)
- **Feature request:** 같은 링크 — 가능하면 "Feature Request" template 사용.

bug 신고 시 Python 버전, OS, aerospike-py 버전 (`aerospike_py.__version__`), 그리고 minimal reproduction 을 포함해 주세요.
