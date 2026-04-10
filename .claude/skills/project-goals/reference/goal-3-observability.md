# Goal 3: Observability

## Logging

Rust `log` crate → Python `logging` bridge.
Acquires GIL via `Python::try_attach` then forwards to `logging.getLogger(target)`.

## OTel Tracing

- `otel` feature (always enabled in maturin build) — cargo feature gate
- `traced_op!` macro: records OTel span + Prometheus timer simultaneously
- Fast path: when OTel is inactive, only `timed_op!` runs (no Python calls)
- W3C TraceContext propagation: via `opentelemetry.propagate.inject()`
- Python optional dep: `pip install aerospike-py[otel]` → `opentelemetry-api>=1.20`

## Prometheus Metrics

- `db_client_operation_duration_seconds` histogram (labels: namespace, set, operation, error_type)
- Built-in HTTP server: `start_metrics_server(port)` / `stop_metrics_server()`
- Global toggle via `METRICS_ENABLED` AtomicBool

## Key Files

- `rust/src/logging.rs`
- `rust/src/tracing.rs`
- `rust/src/metrics.rs`
- `tests/unit/test_tracing.py`, `tests/unit/test_metrics.py`
