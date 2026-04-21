//! Prometheus metrics collection for Aerospike operations.
//!
//! Tracks `db_client_operation_duration_seconds` as a histogram, labeled by
//! system, namespace, collection (set), operation name, and error type.
//! Metrics are exposed in Prometheus text format via [`get_text`].

use std::borrow::Cow;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{LazyLock, Mutex};
use std::time::Instant;

/// Global toggle for operational metrics collection (`db_client_operation_duration_seconds`).
///
/// When `false`, `timed_op!` / `traced_op!` skip timer creation entirely (~1ns atomic load).
/// Separate from `INTERNAL_STAGE_ENABLED` which gates fine-grained stage profiling.
static METRICS_ENABLED: AtomicBool = AtomicBool::new(true);

/// Global toggle for internal stage profiling metrics (`db_client_internal_stage_seconds`).
///
/// Default: `false` — stage profiling is a debug feature with non-zero overhead
/// (many `Instant::now()` calls on batch hot paths). Enable via
/// [`set_internal_stage_enabled`], the `AEROSPIKE_PY_INTERNAL_METRICS=1` env var,
/// or the `internal_stage_profiling()` Python context manager.
///
/// When `false`, [`stage_timer!`](crate::stage_timer) and related paths skip
/// `Instant::now()` entirely — single `Ordering::Relaxed` atomic load (~1ns).
static INTERNAL_STAGE_ENABLED: AtomicBool = AtomicBool::new(false);

/// Enable or disable operational metrics collection.
#[inline]
pub fn set_metrics_enabled(enabled: bool) {
    METRICS_ENABLED.store(enabled, Ordering::Release);
}

/// Check if operational metrics collection is currently enabled.
#[inline]
pub fn is_metrics_enabled() -> bool {
    METRICS_ENABLED.load(Ordering::Acquire)
}

/// Enable or disable internal stage profiling metrics.
///
/// Runtime toggle. Safe to call from any thread. When disabled, all stage
/// timing call sites skip `Instant::now()` calls — zero heap and near-zero CPU
/// overhead.
#[inline]
pub fn set_internal_stage_enabled(enabled: bool) {
    INTERNAL_STAGE_ENABLED.store(enabled, Ordering::Relaxed);
}

/// Check if internal stage profiling is currently enabled. Hot path.
#[inline]
pub fn is_internal_stage_enabled() -> bool {
    INTERNAL_STAGE_ENABLED.load(Ordering::Relaxed)
}

/// Initialize internal stage profiling from the `AEROSPIKE_PY_INTERNAL_METRICS`
/// environment variable. Called once during native module init.
///
/// Truthy values (case-insensitive: `1`, `true`, `yes`, `on`) enable profiling at
/// startup. Surrounding whitespace is trimmed. Anything else (including missing)
/// leaves the flag at its default `false`.
pub fn init_internal_stage_from_env() {
    let enabled = std::env::var("AEROSPIKE_PY_INTERNAL_METRICS")
        .map(|v| {
            matches!(
                v.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(false);
    INTERNAL_STAGE_ENABLED.store(enabled, Ordering::Relaxed);
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
///
/// Extended range starting at 1μs to precisely capture sub-microsecond stages
/// like `key_parse` and `into_pyobject` that touch only a handful of pointers.
const INTERNAL_BUCKETS: &[f64] = &[
    0.000_001, 0.000_005, 0.000_01, 0.000_05, 0.000_1, 0.000_5, 0.001, 0.002, 0.005, 0.01, 0.02,
    0.05, 0.1, 0.5, 1.0,
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
/// Gated by [`is_internal_stage_enabled`]. Prefer the [`stage_timer!`](crate::stage_timer)
/// macro at call sites so that the flag check also elides the surrounding
/// `Instant::now()` / `.elapsed()` work.
///
/// Stages include (non-exhaustive): `key_parse`, `tokio_schedule_delay`,
/// `limiter_wait`, `io`, `spawn_blocking_delay`, `into_pyobject`,
/// `event_loop_resume_delay`, `as_dict`, `merge_as_dict`, `future_into_py_setup`.
pub fn record_internal_stage(stage: &'static str, op_name: &str, duration_secs: f64) {
    if !is_internal_stage_enabled() {
        return;
    }
    record_internal_stage_unchecked(stage, op_name, duration_secs);
}

/// Record an internal stage without re-checking the toggle flag.
///
/// For use inside [`stage_timer!`](crate::stage_timer) and `if let Some(t) = ...`
/// blocks where the caller has already verified [`is_internal_stage_enabled`].
/// Avoids a redundant atomic load on the recording path.
#[inline]
pub fn record_internal_stage_unchecked(stage: &'static str, op_name: &str, duration_secs: f64) {
    let labels = InternalStageLabels {
        stage: Cow::Borrowed(stage),
        db_operation_name: Cow::Owned(op_name.to_string()),
    };
    METRICS
        .internal_stage
        .get_or_create(&labels)
        .observe(duration_secs);
}

/// Capture `Instant::now()` only when internal stage profiling is enabled.
///
/// Returns `Some(Instant)` if profiling is ON, `None` otherwise. Use this at
/// the start of a cross-boundary timing window (one that can't be wrapped in
/// a single `stage_timer!` block, e.g. timestamps that travel through `async`
/// boundaries or struct fields).
#[inline]
pub fn maybe_now() -> Option<Instant> {
    if is_internal_stage_enabled() {
        Some(Instant::now())
    } else {
        None
    }
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

/// Wrap a code block with internal-stage timing.
///
/// When [`is_internal_stage_enabled`] is `false`, the expression runs with no
/// timing overhead (single atomic load). When `true`, wraps the expression in
/// `Instant::now()` / `.elapsed()` and emits a `db_client_internal_stage_seconds`
/// observation with `stage` and `op_name` labels.
///
/// Works with both sync and `async` expressions — use inside an `async` block
/// as `stage_timer!("io", "batch_read", { foo.await? })`.
///
/// ```ignore
/// stage_timer!("key_parse", "batch_read", {
///     parse_keys(py, keys)?
/// })
/// ```
#[macro_export]
macro_rules! stage_timer {
    ($stage:expr, $op:expr, $body:expr) => {{
        if $crate::metrics::is_internal_stage_enabled() {
            let __stage_start = ::std::time::Instant::now();
            let __stage_result = $body;
            $crate::metrics::record_internal_stage_unchecked(
                $stage,
                $op,
                __stage_start.elapsed().as_secs_f64(),
            );
            __stage_result
        } else {
            $body
        }
    }};
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
