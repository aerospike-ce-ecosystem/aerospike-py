# Goal 3: Observability

## Logging

Rust `log` 크레이트 → Python `logging` 브릿지.
`Python::try_attach`로 GIL 획득 후 `logging.getLogger(target)` 전달.

## OTel Tracing

- `otel` feature (maturin build에 항상 활성화) — cargo feature gate
- `traced_op!` 매크로: OTel span + Prometheus 타이머 동시 기록
- fast-path: OTel 비활성 시 `timed_op!`만 실행 (Python 호출 없음)
- W3C TraceContext 전파: `opentelemetry.propagate.inject()` 경유
- Python optional dep: `pip install aerospike-py[otel]` → `opentelemetry-api>=1.20`

## Prometheus Metrics

- `db_client_operation_duration_seconds` 히스토그램 (라벨: namespace, set, operation, error_type)
- 내장 HTTP 서버: `start_metrics_server(port)` / `stop_metrics_server()`
- `METRICS_ENABLED` AtomicBool로 전역 토글 가능

## 주요 파일

- `rust/src/logging.rs`
- `rust/src/tracing.rs`
- `rust/src/metrics.rs`
- `tests/unit/test_tracing.py`, `tests/unit/test_metrics.py`
