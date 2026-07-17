---
sidebar_position: 99
title: FAQ
description: Frequently asked questions about aerospike-py.
---

## aerospike-py 는 왜 Rust 로 작성되었나요?

aerospike-py는 [PyO3](https://pyo3.rs/)를 사용해 [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust)를 Python에 제공합니다. 순수 Python client나 C extension과 비교하면 다음과 같은 장점이 있습니다.

- **Performance** — Rust는 native code로 컴파일됩니다. 벤치마크에서 공식 C 기반 client와 대등하거나 더 높은 throughput을 보이며, 특히 batch와 async workload에서 차이가 큽니다.
- **Memory safety** — Rust의 ownership 모델은 garbage collector 없이 use-after-free, buffer overflow, data race 같은 오류를 방지합니다.
- **Native async** — 내부 client가 Tokio 위에서 실행되므로 `AsyncClient`는 sync call을 감싸지 않고 native async I/O를 사용합니다.
- **Zero Python dependencies** — 기본 설치(`pip install aerospike-py`)에는 외부 Python dependency가 없습니다. NumPy와 OpenTelemetry는 선택 사항입니다.

## GIL 처리는 어떻게 되나요?

aerospike-py는 모든 database I/O 중에 Python GIL(Global Interpreter Lock)을 해제합니다. 요청을 처리하는 동안 다른 Python thread도 실행될 수 있습니다.

| Client | Mechanism |
|--------|-----------|
| **Sync `Client`** | `py.detach()`가 GIL을 해제한 뒤 `RUNTIME.block_on()`이 내부 Tokio runtime에서 async Rust operation을 실행합니다. 결과를 반환할 때 GIL을 다시 획득합니다. |
| **Async `AsyncClient`** | `future_into_py()`가 Python awaitable을 반환합니다. 실제 작업은 GIL을 잡지 않고 Tokio runtime에서 실행됩니다. future가 완료되면 `Python::attach()`가 GIL을 다시 획득해 결과를 전달합니다. |

두 방식 모두 Aerospike cluster와 통신하는 동안 GIL을 **잡지 않습니다**. 따라서 다른 Python thread나 async task가 동시에 실행될 수 있습니다.

## aerospike-py 는 thread-safe 한가요?

네. 하나의 `Client` 인스턴스를 여러 thread에서 안전하게 공유할 수 있습니다. Rust client가 connection pool을 관리하며, 공유 상태는 lock-free 또는 mutex로 보호되는 구조에 저장됩니다.

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

네. aerospike-py는 experimental free-threaded CPython(PEP 703)에서 빌드되고 실행됩니다. CI는 Python 3.14t에서 unit test와 concurrency stress test를 실행해 GIL이 없어도 올바르게 동작하는지 확인합니다.

핵심 로직은 Rust의 memory-safety 보장을 따릅니다. 따라서 Python에서 GIL을 완전히 제거해도 안전하게 동작합니다.

## NumPy 는 필수인가요?

아닙니다. NumPy는 **선택적 dependency**입니다.

```bash
# Base install — NumPy 불필요
pip install aerospike-py

# NumPy 지원 포함
pip install aerospike-py[numpy]
```

NumPy를 설치하면 `batch_read()`가 반환한 `LazyBatchRecords`에서 `to_numpy(dtype)`를 호출할 수 있습니다. 이 메서드는 NumPy structured array를 사용하는 `NumpyBatchRecords`를 만듭니다. Client가 GIL을 해제한 상태에서 buffer를 채우므로 결과를 복사하지 않고 `torch.from_numpy(...)`에 바로 전달할 수 있습니다. Structured array를 bulk write할 때는 `batch_write_numpy()`를 사용합니다. 그 밖의 기능은 NumPy 없이도 동일하게 동작합니다.

## 공식 C client 에서 migrate 가능한가요?

네. aerospike-py는 기존 client를 거의 그대로 대체할 수 있도록 설계되었습니다. 먼저 import를 바꾸세요.

```python
# Before
import aerospike

# After
import aerospike_py as aerospike
```

대부분의 API signature, 상수, exception class, policy dict가 호환됩니다. 단계별 절차는 [Migration Guide](/docs/guides/migration), 자세한 비교는 [API Comparison](/docs/guides/api-comparison)을 참고하세요.

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

Span은 OTLP gRPC로 export됩니다. 기본 endpoint는 `http://localhost:4317`입니다. 표준 `OTEL_*` 환경변수로 설정할 수 있으며, 자세한 내용은 [Tracing guide](/docs/integrations/observability/tracing)를 참고하세요.

## Prometheus metrics 는 어떻게 활성화하나요?

aerospike-py에는 Prometheus metrics를 제공하는 HTTP server가 내장되어 있습니다.

```python
import aerospike_py

# port 9464 에서 metrics server 시작
aerospike_py.start_metrics_server(9464)

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()  # port varies by deployment
# ... operation 이 자동으로 metered ...
client.close()

aerospike_py.stop_metrics_server()
```

Prometheus에서 `http://localhost:9464/metrics`를 scrape하세요. Operation type별 latency histogram이 기록됩니다. 자세한 내용은 [Metrics guide](/docs/integrations/observability/metrics)를 참고하세요.

## 어떤 Aerospike server 버전을 지원하나요?

aerospike-py는 **Aerospike Server 6.x와 7.x**의 Community 및 Enterprise edition을 대상으로 테스트합니다. 내부적으로 Aerospike Rust Client v2.0.0-alpha.9를 사용합니다.

## bug 신고 또는 기능 요청은 어떻게 하나요?

GitHub 저장소에 issue 를 등록하세요:

- **Bug report:** [github.com/aerospike-ce-ecosystem/aerospike-py/issues/new](https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/new)
- **Feature request:** 같은 링크 — 가능하면 "Feature Request" template 사용.

Bug를 신고할 때는 Python 버전, OS, aerospike-py 버전(`aerospike_py.__version__`), 최소 재현 코드를 포함해 주세요.
