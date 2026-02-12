// OpenTelemetry tracing integration for aerospike-py.
//
// When the `otel` feature is enabled, this module provides:
// - Lazy initialization of an OTLP trace exporter (controlled by OTEL_* env vars)
// - W3C TraceContext propagation from Python → Rust
// - `traced_op!` macro that wraps each DB operation in a span **and** records metrics
//
// When the `otel` feature is disabled, `traced_op!` falls back to `timed_op!`.

/// Connection metadata attached to every span.
#[derive(Clone, Debug, Default)]
pub struct ConnectionInfo {
    pub server_address: String,
    pub server_port: i64,
    pub cluster_name: String,
}

// ── Feature-gated implementation ────────────────────────────────────────────

#[cfg(feature = "otel")]
pub(crate) mod otel_impl {
    use std::collections::HashMap;
    use std::sync::{LazyLock, Mutex};

    use log::warn;
    use opentelemetry::propagation::TextMapPropagator;
    use opentelemetry::trace::Status;
    use opentelemetry::{global, Context, KeyValue};
    use opentelemetry_sdk::propagation::TraceContextPropagator;
    use opentelemetry_sdk::trace::SdkTracerProvider;
    use opentelemetry_sdk::Resource;
    use pyo3::prelude::*;

    const INSTRUMENTATION_NAME: &str = "aerospike-py";

    /// Global tracer provider – initialised lazily on first use.
    static TRACER_PROVIDER: LazyLock<Mutex<Option<SdkTracerProvider>>> =
        LazyLock::new(|| Mutex::new(None));

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

        let mut guard = TRACER_PROVIDER.lock().unwrap();
        *guard = Some(provider);

        log::info!("OTel tracer provider initialised");
    }

    /// Shut down the tracer provider, flushing any pending spans.
    pub fn shutdown_tracer_provider() {
        let mut guard = TRACER_PROVIDER.lock().unwrap();
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

    /// Extract W3C TraceContext from the Python `opentelemetry` context.
    ///
    /// Must be called **while the GIL is held** (before `py.detach()` / `future_into_py`).
    /// Falls back to a root context if the Python SDK is not installed or no active span exists.
    pub fn extract_python_context(py: Python<'_>) -> Context {
        // Try: from opentelemetry import propagate; carrier = {}; propagate.inject(carrier)
        let result: PyResult<HashMap<String, String>> = (|| {
            let propagate = py.import("opentelemetry.propagate")?;
            let carrier = pyo3::types::PyDict::new(py);
            propagate.call_method1("inject", (carrier.clone(),))?;
            carrier.extract()
        })();

        match result {
            Ok(carrier) if !carrier.is_empty() => {
                let propagator = TraceContextPropagator::new();
                propagator.extract(&carrier)
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
        span.set_attribute(KeyValue::new("error.type", error_type));
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
/// Signature: `traced_op!(op, ns, set, parent_ctx, { async_body })`
///
/// The expression must return `Result<T, aerospike_core::Error>`.
/// Returns `Result<T, PyErr>`.
#[cfg(feature = "otel")]
#[macro_export]
macro_rules! traced_op {
    ($op:expr, $ns:expr, $set:expr, $parent_ctx:expr, $conn_info:expr, $body:expr) => {{
        use opentelemetry::trace::{SpanKind, TraceContextExt, Tracer};
        use opentelemetry::KeyValue;

        let tracer = $crate::tracing::otel_impl::get_tracer();
        let span_name = format!("{} {}.{}", $op.to_uppercase(), $ns, $set);
        let conn = &$conn_info;
        let span = tracer
            .span_builder(span_name)
            .with_kind(SpanKind::Client)
            .with_attributes(vec![
                KeyValue::new("db.system.name", "aerospike"),
                KeyValue::new("db.namespace", $ns.to_string()),
                KeyValue::new("db.collection.name", $set.to_string()),
                KeyValue::new("db.operation.name", $op.to_uppercase()),
                KeyValue::new("server.address", conn.server_address.clone()),
                KeyValue::new("server.port", conn.server_port),
                KeyValue::new("db.aerospike.cluster_name", conn.cluster_name.clone()),
            ])
            .start_with_context(&tracer, &$parent_ctx);
        let _cx = $parent_ctx.with_span(span);

        // Metrics (existing logic preserved)
        let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
        let result = $body;
        match &result {
            Ok(_) => timer.finish(""),
            Err(e) => timer.finish(&$crate::metrics::error_type_from_aerospike_error(e)),
        }

        // Tracing: record error + end span
        {
            let span_ref = opentelemetry::trace::TraceContextExt::span(&_cx);
            if let Err(e) = &result {
                $crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
            }
            span_ref.end();
        }

        result.map_err($crate::errors::as_to_pyerr)
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
