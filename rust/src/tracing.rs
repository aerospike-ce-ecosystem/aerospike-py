// OpenTelemetry tracing integration for aerospike-py.
//
// When the `otel` feature is enabled, this module provides:
// - Lazy initialization of an OTLP trace exporter (controlled by OTEL_* env vars)
// - W3C TraceContext propagation from Python → Rust
// - `traced_op!` macro that wraps each DB operation in a span **and** records metrics
//
// When the `otel` feature is disabled, `traced_op!` falls back to `timed_op!`.

use std::borrow::Cow;
use std::sync::Arc;

/// Connection metadata attached to every OTel span and used for metric labels.
///
/// Populated during `connect()` from the first host in the config.
/// Uses `Arc<str>` for server_address and cluster_name to avoid heap allocations
/// when cloning for OTel attributes (atomic ref-count increment only).
#[derive(Clone, Debug)]
pub struct ConnectionInfo {
    /// Address of the first seed host (e.g. `"127.0.0.1"`).
    pub server_address: Arc<str>,
    /// Port of the first seed host (e.g. `18710`).
    pub server_port: i64,
    /// Cluster name from the client config (empty string if unset).
    pub cluster_name: Arc<str>,
}

impl Default for ConnectionInfo {
    fn default() -> Self {
        Self {
            server_address: Arc::from(""),
            server_port: 0,
            cluster_name: Arc::from(""),
        }
    }
}

/// Map a known operation name to its uppercase equivalent.
///
/// Returns `Cow::Borrowed` for known operations (zero alloc) and
/// `Cow::Owned` for unknown operations (runtime `to_uppercase()`).
#[inline]
pub fn op_to_upper(op: &str) -> Cow<'static, str> {
    match op {
        "put" => Cow::Borrowed("PUT"),
        "get" => Cow::Borrowed("GET"),
        "select" => Cow::Borrowed("SELECT"),
        "exists" => Cow::Borrowed("EXISTS"),
        "delete" => Cow::Borrowed("DELETE"),
        "remove" => Cow::Borrowed("REMOVE"),
        "remove_bin" => Cow::Borrowed("REMOVE_BIN"),
        "append" => Cow::Borrowed("APPEND"),
        "prepend" => Cow::Borrowed("PREPEND"),
        "increment" => Cow::Borrowed("INCREMENT"),
        "touch" => Cow::Borrowed("TOUCH"),
        "operate" => Cow::Borrowed("OPERATE"),
        "operate_ordered" => Cow::Borrowed("OPERATE_ORDERED"),
        "batch_read" => Cow::Borrowed("BATCH_READ"),
        "batch_operate" => Cow::Borrowed("BATCH_OPERATE"),
        "batch_remove" => Cow::Borrowed("BATCH_REMOVE"),
        "batch_write" => Cow::Borrowed("BATCH_WRITE"),
        "batch_write_retry" => Cow::Borrowed("BATCH_WRITE_RETRY"),
        "batch_write_numpy" => Cow::Borrowed("BATCH_WRITE_NUMPY"),
        "batch_write_numpy_retry" => Cow::Borrowed("BATCH_WRITE_NUMPY_RETRY"),
        "query" => Cow::Borrowed("QUERY"),
        other => {
            log::warn!("Unknown operation name for uppercase mapping: {other}");
            Cow::Owned(other.to_uppercase())
        }
    }
}

// ── Feature-gated implementation ────────────────────────────────────────────

#[cfg(feature = "otel")]
pub(crate) mod otel_impl {
    use std::collections::HashMap;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::{LazyLock, Mutex, OnceLock};

    use log::warn;
    use opentelemetry::propagation::TextMapPropagator;
    use opentelemetry::trace::Status;
    use opentelemetry::{global, Context, KeyValue};
    use opentelemetry_sdk::propagation::TraceContextPropagator;
    use opentelemetry_sdk::trace::SdkTracerProvider;
    use opentelemetry_sdk::Resource;
    use pyo3::intern;
    use pyo3::prelude::*;

    const INSTRUMENTATION_NAME: &str = "aerospike-py";

    /// Global tracer provider – initialised lazily on first use.
    static TRACER_PROVIDER: LazyLock<Mutex<Option<SdkTracerProvider>>> =
        LazyLock::new(|| Mutex::new(None));

    /// Fast-path flag: true only when tracer provider is successfully initialized.
    /// Avoids Python calls and OTel span creation when tracing is not active.
    static OTEL_ACTIVE: AtomicBool = AtomicBool::new(false);

    /// Cached Python module for `opentelemetry.propagate` (process-lifetime).
    static PROPAGATE_MODULE: OnceLock<Py<pyo3::types::PyModule>> = OnceLock::new();

    /// Check if OTel tracing is currently active.
    #[inline]
    pub fn is_otel_active() -> bool {
        OTEL_ACTIVE.load(Ordering::Acquire)
    }

    /// Initialise the OTLP tracer provider.
    ///
    /// Respects the standard OTEL environment variables:
    ///   OTEL_SDK_DISABLED=true          → no-op
    ///   OTEL_TRACES_EXPORTER=none       → no-op
    ///   OTEL_EXPORTER_OTLP_ENDPOINT     → gRPC endpoint (default localhost:4317)
    ///   OTEL_SERVICE_NAME               → resource service.name
    ///   … and many more (handled by the SDK / OTLP crate automatically)
    pub fn init_tracer_provider() {
        // Check kill-switches
        if std::env::var("OTEL_SDK_DISABLED")
            .map(|v| v.eq_ignore_ascii_case("true"))
            .unwrap_or(false)
        {
            log::info!("OTel SDK disabled via OTEL_SDK_DISABLED");
            return;
        }
        if std::env::var("OTEL_TRACES_EXPORTER")
            .map(|v| v.eq_ignore_ascii_case("none"))
            .unwrap_or(false)
        {
            log::info!("OTel traces exporter set to none");
            return;
        }

        // The tonic gRPC transport and batch exporter both require a Tokio runtime.
        // Enter the shared runtime so that Tokio reactor is available.
        let _rt_guard = crate::runtime::RUNTIME.enter();

        let exporter = match opentelemetry_otlp::SpanExporter::builder()
            .with_tonic()
            .build()
        {
            Ok(exp) => exp,
            Err(e) => {
                warn!("Failed to create OTLP span exporter: {e}. Tracing disabled.");
                return;
            }
        };

        let service_name =
            std::env::var("OTEL_SERVICE_NAME").unwrap_or_else(|_| "aerospike-py".to_string());

        let resource = Resource::builder().with_service_name(service_name).build();

        let provider = SdkTracerProvider::builder()
            .with_batch_exporter(exporter)
            .with_resource(resource)
            .build();

        global::set_tracer_provider(provider.clone());

        let mut guard = TRACER_PROVIDER.lock().unwrap_or_else(|e| e.into_inner());
        *guard = Some(provider);

        OTEL_ACTIVE.store(true, Ordering::Release);
        log::info!("OTel tracer provider initialised");
    }

    /// Shut down the tracer provider, flushing any pending spans.
    pub fn shutdown_tracer_provider() {
        OTEL_ACTIVE.store(false, Ordering::Release);

        let mut guard = TRACER_PROVIDER.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(provider) = guard.take() {
            // Shutdown flushes pending spans via the batch exporter which needs Tokio.
            let _rt_guard = crate::runtime::RUNTIME.enter();
            if let Err(e) = provider.shutdown() {
                warn!("OTel tracer provider shutdown error: {e}");
            } else {
                log::info!("OTel tracer provider shut down");
            }
        }
    }

    /// Return the global tracer for aerospike-py instrumentation.
    #[inline]
    pub fn get_tracer() -> opentelemetry::global::BoxedTracer {
        global::tracer(INSTRUMENTATION_NAME)
    }

    /// W3C `traceparent` 의 trace-flags 를 SAMPLED(0x01) 비트만 남기고 마스킹.
    ///
    /// opentelemetry-rust <= 0.31 의 `TraceContextPropagator` 는 version 00 에서
    /// flags > 0x02 인 traceparent (예: opentelemetry-python 이 내보내는
    /// 0x03 = SAMPLED | RANDOM, W3C Trace Context Level 2) 를 통째로 거부해
    /// 부모 컨텍스트가 유실된다 (스팬이 고아 root 로 빠짐). upstream 은 main 에서
    /// 해당 체크를 제거했으므로, otel crate 를 그 버전으로 올리면 이 마스킹은
    /// 제거 가능하다.
    pub(crate) fn sanitize_traceparent(value: &str) -> Option<String> {
        let parts: Vec<&str> = value.trim().split('-').collect();
        if parts.len() != 4 {
            return None;
        }
        let flags = u8::from_str_radix(parts[3], 16).ok()?;
        let masked = flags & 0x01;
        if masked == flags {
            return None; // 변경 불필요
        }
        Some(format!(
            "{}-{}-{}-{:02x}",
            parts[0], parts[1], parts[2], masked
        ))
    }

    /// Extract W3C TraceContext from the Python `opentelemetry` context.
    ///
    /// Must be called **while the GIL is held** (before `py.detach()` / `future_into_py`).
    /// Falls back to a root context if the Python SDK is not installed or no active span exists.
    ///
    /// Optimizations:
    /// - Early return when OTel is not active (zero Python calls)
    /// - `OnceLock` caches the Python module lookup (once per process)
    /// - `intern!` caches method name PyString (pointer read on subsequent calls)
    pub fn extract_python_context(py: Python<'_>) -> Context {
        if !is_otel_active() {
            return Context::current();
        }

        let result: PyResult<HashMap<String, String>> = (|| {
            let propagate = match PROPAGATE_MODULE.get() {
                Some(module) => module.bind(py).clone(),
                None => {
                    let module = py.import(intern!(py, "opentelemetry.propagate"))?;
                    let _ = PROPAGATE_MODULE.set(module.unbind());
                    // Re-fetch from OnceLock (handles race where another thread set it first)
                    PROPAGATE_MODULE
                        .get()
                        .ok_or_else(|| {
                            pyo3::exceptions::PyRuntimeError::new_err(
                                "failed to initialize opentelemetry.propagate module cache",
                            )
                        })?
                        .bind(py)
                        .clone()
                }
            };
            let carrier = pyo3::types::PyDict::new(py);
            propagate.call_method1(intern!(py, "inject"), (carrier.clone(),))?;
            carrier.extract()
        })();

        match result {
            Ok(mut carrier) if !carrier.is_empty() => {
                if let Some(tp) = carrier.get("traceparent") {
                    if let Some(fixed) = sanitize_traceparent(tp) {
                        carrier.insert("traceparent".to_string(), fixed);
                    }
                }
                static PROPAGATOR: LazyLock<TraceContextPropagator> =
                    LazyLock::new(TraceContextPropagator::new);
                PROPAGATOR.extract(&carrier)
            }
            _ => Context::current(),
        }
    }

    /// Record an error on a span following OTel semantic conventions.
    pub fn record_error_on_span(
        span: &opentelemetry::trace::SpanRef<'_>,
        err: &aerospike_core::Error,
    ) {
        let error_type = crate::metrics::error_type_from_aerospike_error(err);
        span.set_attribute(KeyValue::new("error.type", error_type.into_owned()));
        span.set_status(Status::error(format!("{err}")));

        if let aerospike_core::Error::ServerError(rc, _, _) = err {
            span.set_attribute(KeyValue::new("db.response.status_code", format!("{rc:?}")));
        }
    }
}

// ── Python-exposed functions ────────────────────────────────────────────────

#[cfg(feature = "otel")]
use pyo3::prelude::*;

#[cfg(feature = "otel")]
#[pyfunction]
pub fn init_tracing() {
    otel_impl::init_tracer_provider();
}

#[cfg(feature = "otel")]
#[pyfunction]
pub fn shutdown_tracing() {
    otel_impl::shutdown_tracer_provider();
}

#[cfg(not(feature = "otel"))]
use pyo3::prelude::*;

#[cfg(not(feature = "otel"))]
#[pyfunction]
pub fn init_tracing() {
    log::info!("OTel tracing not available (compiled without 'otel' feature)");
}

#[cfg(not(feature = "otel"))]
#[pyfunction]
pub fn shutdown_tracing() {
    // no-op
}

// ── traced_op! macro ────────────────────────────────────────────────────────

/// Instrument a data operation with **both** an OTel span and Prometheus metrics.
///
/// When OTel is active: creates a span, records attributes, and collects metrics.
/// When OTel is inactive: metrics-only fast path (zero Python calls, zero span alloc).
///
/// Signature: `traced_op!(op, ns, set, parent_ctx, conn_info, { async_body })`
///
/// The expression must return `Result<T, aerospike_core::Error>`.
/// Returns `Result<T, PyErr>`.
#[cfg(feature = "otel")]
#[macro_export]
macro_rules! traced_op {
    ($op:expr, $ns:expr, $set:expr, $parent_ctx:expr, $conn_info:expr, $body:expr) => {{
        if $crate::tracing::otel_impl::is_otel_active() {
            // Full OTel span + metrics path
            use opentelemetry::trace::{SpanKind, TraceContextExt, Tracer};
            use opentelemetry::KeyValue;

            let op_upper = $crate::tracing::op_to_upper($op);
            let tracer = $crate::tracing::otel_impl::get_tracer();
            let span_name = format!("{} {}.{}", op_upper, $ns, $set);
            let conn = &$conn_info;
            let span = tracer
                .span_builder(span_name)
                .with_kind(SpanKind::Client)
                .with_attributes(vec![
                    KeyValue::new("db.system.name", "aerospike"),
                    KeyValue::new("db.namespace", $ns.to_string()),
                    KeyValue::new("db.collection.name", $set.to_string()),
                    KeyValue::new("db.operation.name", op_upper.clone().into_owned()),
                    KeyValue::new(
                        "server.address",
                        opentelemetry::StringValue::from(std::sync::Arc::clone(
                            &conn.server_address,
                        )),
                    ),
                    KeyValue::new("server.port", conn.server_port),
                    KeyValue::new(
                        "db.aerospike.cluster_name",
                        opentelemetry::StringValue::from(std::sync::Arc::clone(&conn.cluster_name)),
                    ),
                ])
                .start_with_context(&tracer, &$parent_ctx);
            let _cx = $parent_ctx.with_span(span);

            let result = if $crate::metrics::is_metrics_enabled() {
                let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
                let result = $body;
                match &result {
                    Ok(_) => timer.finish(""),
                    Err(e) => {
                        let err_type = $crate::metrics::error_type_from_aerospike_error(e);
                        timer.finish(&err_type);
                    }
                }
                result
            } else {
                $body
            };

            {
                let span_ref = opentelemetry::trace::TraceContextExt::span(&_cx);
                if let Err(e) = &result {
                    $crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
                }
                span_ref.end();
            }

            result.map_err($crate::errors::as_to_pyerr)
        } else {
            // Metrics-only fast path: no span, no Python calls
            let _ = $parent_ctx;
            let _ = &$conn_info;
            $crate::timed_op!($op, $ns, $set, $body)
        }
    }};
}

/// When compiled without `otel`, fall back to plain metrics.
#[cfg(not(feature = "otel"))]
#[macro_export]
macro_rules! traced_op {
    ($op:expr, $ns:expr, $set:expr, $parent_ctx:expr, $conn_info:expr, $body:expr) => {{
        let _ = $parent_ctx;
        let _ = &$conn_info;
        $crate::timed_op!($op, $ns, $set, $body)
    }};
}

// ── traced_exists_op! macro ─────────────────────────────────────────────────

/// Like `traced_op!` but treats `KeyNotFoundError` as a non-error for both
/// metrics and OTel spans. Returns `Result<T, aerospike_core::Error>` (NOT PyErr).
#[cfg(feature = "otel")]
#[macro_export]
macro_rules! traced_exists_op {
    ($op:expr, $ns:expr, $set:expr, $parent_ctx:expr, $conn_info:expr, $body:expr) => {{
        if $crate::tracing::otel_impl::is_otel_active() {
            // Full OTel span + metrics path
            use opentelemetry::trace::{SpanKind, TraceContextExt, Tracer};
            use opentelemetry::KeyValue;

            let op_upper = $crate::tracing::op_to_upper($op);
            let tracer = $crate::tracing::otel_impl::get_tracer();
            let span_name = format!("{} {}.{}", op_upper, $ns, $set);
            let conn = &$conn_info;
            let span = tracer
                .span_builder(span_name)
                .with_kind(SpanKind::Client)
                .with_attributes(vec![
                    KeyValue::new("db.system.name", "aerospike"),
                    KeyValue::new("db.namespace", $ns.to_string()),
                    KeyValue::new("db.collection.name", $set.to_string()),
                    KeyValue::new("db.operation.name", op_upper.clone().into_owned()),
                    KeyValue::new(
                        "server.address",
                        opentelemetry::StringValue::from(std::sync::Arc::clone(
                            &conn.server_address,
                        )),
                    ),
                    KeyValue::new("server.port", conn.server_port),
                    KeyValue::new(
                        "db.aerospike.cluster_name",
                        opentelemetry::StringValue::from(std::sync::Arc::clone(&conn.cluster_name)),
                    ),
                ])
                .start_with_context(&tracer, &$parent_ctx);
            let _cx = $parent_ctx.with_span(span);

            let result = if $crate::metrics::is_metrics_enabled() {
                let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
                let result = $body;
                match &result {
                    Ok(_) => timer.finish(""),
                    Err(aerospike_core::Error::ServerError(
                        aerospike_core::ResultCode::KeyNotFoundError,
                        _,
                        _,
                    )) => timer.finish(""),
                    Err(e) => {
                        let err_type = $crate::metrics::error_type_from_aerospike_error(e);
                        timer.finish(&err_type);
                    }
                }
                result
            } else {
                $body
            };

            {
                let span_ref = opentelemetry::trace::TraceContextExt::span(&_cx);
                match &result {
                    Ok(_) => {}
                    Err(aerospike_core::Error::ServerError(
                        aerospike_core::ResultCode::KeyNotFoundError,
                        _,
                        _,
                    )) => {}
                    Err(e) => {
                        $crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
                    }
                }
                span_ref.end();
            }

            result
        } else {
            // Metrics-only fast path
            let _ = $parent_ctx;
            let _ = &$conn_info;

            if $crate::metrics::is_metrics_enabled() {
                let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
                let result = $body;
                match &result {
                    Ok(_) => timer.finish(""),
                    Err(aerospike_core::Error::ServerError(
                        aerospike_core::ResultCode::KeyNotFoundError,
                        _,
                        _,
                    )) => timer.finish(""),
                    Err(e) => {
                        let err_type = $crate::metrics::error_type_from_aerospike_error(e);
                        timer.finish(&err_type);
                    }
                }
                result
            } else {
                $body
            }
        }
    }};
}

/// When compiled without `otel`, fall back to plain metrics with exists handling.
#[cfg(not(feature = "otel"))]
#[macro_export]
macro_rules! traced_exists_op {
    ($op:expr, $ns:expr, $set:expr, $parent_ctx:expr, $conn_info:expr, $body:expr) => {{
        let _ = $parent_ctx;
        let _ = &$conn_info;

        if $crate::metrics::is_metrics_enabled() {
            let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
            let result = $body;
            match &result {
                Ok(_) => timer.finish(""),
                Err(aerospike_core::Error::ServerError(
                    aerospike_core::ResultCode::KeyNotFoundError,
                    _,
                    _,
                )) => timer.finish(""),
                Err(e) => {
                    let err_type = $crate::metrics::error_type_from_aerospike_error(e);
                    timer.finish(&err_type);
                }
            }
            result
        } else {
            $body
        }
    }};
}

#[cfg(all(test, feature = "otel"))]
mod tests {
    use super::otel_impl::sanitize_traceparent;

    #[test]
    fn masks_w3c_level2_random_flag() {
        // opentelemetry-python 이 내보내는 SAMPLED|RANDOM(0x03) → SAMPLED(0x01)
        assert_eq!(
            sanitize_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-03"),
            Some("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01".to_string())
        );
    }

    #[test]
    fn masks_unsampled_random_flag() {
        assert_eq!(
            sanitize_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-02"),
            Some("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00".to_string())
        );
    }

    #[test]
    fn passthrough_when_already_clean() {
        // 변경 불필요 → None (재할당 회피)
        assert_eq!(
            sanitize_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
            None
        );
        assert_eq!(
            sanitize_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"),
            None
        );
    }

    #[test]
    fn malformed_inputs_left_untouched() {
        // 형식이 다르면 건드리지 않고 propagator 의 자체 검증에 맡긴다
        assert_eq!(sanitize_traceparent("garbage"), None);
        assert_eq!(sanitize_traceparent("00-abc-def"), None);
        assert_eq!(
            sanitize_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-zz"),
            None
        );
        assert_eq!(sanitize_traceparent(""), None);
    }
}
