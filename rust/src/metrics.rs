//! Prometheus metrics collection for Aerospike operations.
//!
//! Tracks `db_client_operation_duration_seconds` as a histogram, labeled by
//! system, namespace, collection (set), operation name, and error type.
//! Metrics are exposed in Prometheus text format via [`get_text`].

use std::borrow::Cow;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{LazyLock, Mutex};
use std::time::Instant;

/// Global toggle for metrics collection.
/// When `false`, `timed_op!` skips timer creation entirely (~1ns atomic load).
static METRICS_ENABLED: AtomicBool = AtomicBool::new(true);

/// Enable or disable metrics collection.
#[inline]
pub fn set_metrics_enabled(enabled: bool) {
    METRICS_ENABLED.store(enabled, Ordering::Release);
}

/// Check if metrics collection is currently enabled.
#[inline]
pub fn is_metrics_enabled() -> bool {
    METRICS_ENABLED.load(Ordering::Acquire)
}

use aerospike_core::{Error as AsError, ResultCode};
use prometheus_client::encoding::EncodeLabelSet;
use prometheus_client::metrics::family::Family;
use prometheus_client::metrics::histogram::Histogram;
use prometheus_client::registry::Registry;

/// Histogram bucket boundaries (in seconds) for operation duration.
const HISTOGRAM_BUCKETS: &[f64] = &[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0];

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct OperationLabels {
    db_system_name: Cow<'static, str>,
    db_namespace: Cow<'static, str>,
    db_collection_name: Cow<'static, str>,
    db_operation_name: Cow<'static, str>,
    error_type: Cow<'static, str>,
}

/// Internal stage labels for batch_read breakdown metrics.
#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct InternalStageLabels {
    stage: Cow<'static, str>,
    db_operation_name: Cow<'static, str>,
}

struct MetricsState {
    registry: Mutex<Registry>,
    op_duration: Family<OperationLabels, Histogram>,
    internal_stage: Family<InternalStageLabels, Histogram>,
}

/// Fine-grained bucket boundaries for sub-millisecond internal stages.
const INTERNAL_BUCKETS: &[f64] = &[
    0.000_01, 0.000_05, 0.000_1, 0.000_5, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0,
];

static METRICS: LazyLock<MetricsState> = LazyLock::new(|| {
    let mut registry = Registry::default();
    let op_duration = Family::<OperationLabels, Histogram>::new_with_constructor(|| {
        Histogram::new(HISTOGRAM_BUCKETS.iter().cloned())
    });
    registry.register(
        "db_client_operation_duration_seconds",
        "Duration of database client operations",
        op_duration.clone(),
    );
    let internal_stage = Family::<InternalStageLabels, Histogram>::new_with_constructor(|| {
        Histogram::new(INTERNAL_BUCKETS.iter().cloned())
    });
    registry.register(
        "db_client_internal_stage_seconds",
        "Internal stage durations within a database operation (key_parse, limiter_wait, io, into_pyobject, as_dict)",
        internal_stage.clone(),
    );
    MetricsState {
        registry: Mutex::new(registry),
        op_duration,
        internal_stage,
    }
});

/// A RAII timer that records operation duration on [`finish`](Self::finish).
///
/// Created via [`OperationTimer::start`]; must be explicitly finished
/// (not dropped) to record the metric with the correct error type.
///
/// Uses borrowed references to avoid heap allocations at start time.
/// String conversion only happens in `finish()` for label creation.
pub struct OperationTimer<'a> {
    start: Instant,
    op_name: &'a str,
    namespace: &'a str,
    set_name: &'a str,
}

impl<'a> OperationTimer<'a> {
    pub fn start(op_name: &'a str, namespace: &'a str, set_name: &'a str) -> Self {
        Self {
            start: Instant::now(),
            op_name,
            namespace,
            set_name,
        }
    }

    pub fn finish(self, error_type: &str) {
        let duration = self.start.elapsed().as_secs_f64();
        let labels = OperationLabels {
            db_system_name: Cow::Borrowed("aerospike"),
            db_namespace: Cow::Owned(self.namespace.to_string()),
            db_collection_name: Cow::Owned(self.set_name.to_string()),
            db_operation_name: Cow::Owned(self.op_name.to_string()),
            error_type: if error_type.is_empty() {
                Cow::Borrowed("")
            } else {
                Cow::Owned(error_type.to_string())
            },
        };
        METRICS.op_duration.get_or_create(&labels).observe(duration);
    }
}

/// Classify an `aerospike_core::Error` into a short error-type string for metric labels.
///
/// Returns `Cow::Borrowed` for known error types (zero alloc) and `Cow::Owned`
/// only for unknown `ResultCode` variants.
pub fn error_type_from_aerospike_error(err: &AsError) -> Cow<'static, str> {
    match err {
        AsError::Connection(_) => Cow::Borrowed("Connection"),
        AsError::Timeout(_) => Cow::Borrowed("Timeout"),
        AsError::InvalidArgument(_) => Cow::Borrowed("InvalidArgument"),
        AsError::ServerError(rc, _, _) => match rc {
            ResultCode::KeyNotFoundError => Cow::Borrowed("KeyNotFoundError"),
            ResultCode::KeyExistsError => Cow::Borrowed("KeyExistsError"),
            ResultCode::GenerationError => Cow::Borrowed("GenerationError"),
            ResultCode::RecordTooBig => Cow::Borrowed("RecordTooBig"),
            ResultCode::BinTypeError => Cow::Borrowed("BinTypeError"),
            ResultCode::BinNotFound => Cow::Borrowed("BinNotFound"),
            ResultCode::FilteredOut => Cow::Borrowed("FilteredOut"),
            ResultCode::Timeout => Cow::Borrowed("Timeout"),
            _ => Cow::Owned(format!("{:?}", rc)),
        },
        AsError::InvalidNode(_) => Cow::Borrowed("InvalidNode"),
        AsError::NoMoreConnections => Cow::Borrowed("NoMoreConnections"),
        _ => Cow::Borrowed("Unknown"),
    }
}

/// Record an internal stage duration for fine-grained profiling.
///
/// Stages: `key_parse`, `limiter_wait`, `io`, `into_pyobject`, `as_dict`
pub fn record_internal_stage(stage: &'static str, op_name: &str, duration_secs: f64) {
    if !is_metrics_enabled() {
        return;
    }
    let labels = InternalStageLabels {
        stage: Cow::Borrowed(stage),
        db_operation_name: Cow::Owned(op_name.to_string()),
    };
    METRICS.internal_stage.get_or_create(&labels).observe(duration_secs);
}

/// Encode all registered metrics in Prometheus text exposition format.
pub fn get_text() -> String {
    let mut buf = String::new();
    let registry = match METRICS.registry.lock() {
        Ok(r) => r,
        Err(_) => {
            log::error!(
                "Metrics registry mutex was poisoned — a prior panic corrupted metric state. \
                 Returning empty metrics to avoid exposing incomplete data."
            );
            return String::from(
                "# aerospike_py_metrics_unavailable: registry mutex poisoned\n# EOF\n",
            );
        }
    };
    if let Err(e) = prometheus_client::encoding::text::encode(&mut buf, &registry) {
        log::error!("Failed to encode Prometheus metrics: {e}");
    }
    buf
}

/// Instrument a data operation with metrics.
///
/// The expression must return `Result<T, AsError>`.
/// Returns `Result<T, PyErr>`.
///
/// When metrics are disabled via [`set_metrics_enabled(false)`], skips timer
/// creation entirely (single atomic load, ~1ns overhead).
#[macro_export]
macro_rules! timed_op {
    ($op:expr, $ns:expr, $set:expr, $body:expr) => {{
        if $crate::metrics::is_metrics_enabled() {
            let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
            let result = $body;
            match &result {
                Ok(_) => timer.finish(""),
                Err(e) => {
                    let err_type = $crate::metrics::error_type_from_aerospike_error(e);
                    timer.finish(&err_type);
                }
            }
            result.map_err($crate::errors::as_to_pyerr)
        } else {
            let result = $body;
            result.map_err($crate::errors::as_to_pyerr)
        }
    }};
}
