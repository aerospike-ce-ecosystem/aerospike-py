use std::borrow::Cow;
use std::sync::{LazyLock, Mutex};
use std::time::Instant;

use aerospike_core::{Error as AsError, ResultCode};
use prometheus_client::encoding::EncodeLabelSet;
use prometheus_client::metrics::family::Family;
use prometheus_client::metrics::histogram::Histogram;
use prometheus_client::registry::Registry;

const HISTOGRAM_BUCKETS: &[f64] = &[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0];

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct OperationLabels {
    db_system_name: Cow<'static, str>,
    db_namespace: Cow<'static, str>,
    db_collection_name: Cow<'static, str>,
    db_operation_name: Cow<'static, str>,
    error_type: Cow<'static, str>,
}

struct MetricsState {
    registry: Mutex<Registry>,
    op_duration: Family<OperationLabels, Histogram>,
}

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
    MetricsState {
        registry: Mutex::new(registry),
        op_duration,
    }
});

pub struct OperationTimer {
    start: Instant,
    op_name: String,
    namespace: String,
    set_name: String,
}

impl OperationTimer {
    pub fn start(op_name: &str, namespace: &str, set_name: &str) -> Self {
        Self {
            start: Instant::now(),
            op_name: op_name.to_string(),
            namespace: namespace.to_string(),
            set_name: set_name.to_string(),
        }
    }

    pub fn finish(self, error_type: &str) {
        let duration = self.start.elapsed().as_secs_f64();
        let labels = OperationLabels {
            db_system_name: Cow::Borrowed("aerospike"),
            db_namespace: Cow::Owned(self.namespace),
            db_collection_name: Cow::Owned(self.set_name),
            db_operation_name: Cow::Owned(self.op_name),
            error_type: if error_type.is_empty() {
                Cow::Borrowed("")
            } else {
                Cow::Owned(error_type.to_string())
            },
        };
        METRICS.op_duration.get_or_create(&labels).observe(duration);
    }
}

pub fn error_type_from_aerospike_error(err: &AsError) -> String {
    match err {
        AsError::Connection(_) => "Connection".to_string(),
        AsError::Timeout(_) => "Timeout".to_string(),
        AsError::InvalidArgument(_) => "InvalidArgument".to_string(),
        AsError::ServerError(rc, _, _) => match rc {
            ResultCode::KeyNotFoundError => "KeyNotFoundError".to_string(),
            ResultCode::KeyExistsError => "KeyExistsError".to_string(),
            ResultCode::GenerationError => "GenerationError".to_string(),
            ResultCode::RecordTooBig => "RecordTooBig".to_string(),
            ResultCode::BinTypeError => "BinTypeError".to_string(),
            ResultCode::BinNotFound => "BinNotFound".to_string(),
            ResultCode::FilteredOut => "FilteredOut".to_string(),
            ResultCode::Timeout => "Timeout".to_string(),
            _ => format!("{:?}", rc),
        },
        AsError::InvalidNode(_) => "InvalidNode".to_string(),
        AsError::NoMoreConnections => "NoMoreConnections".to_string(),
        _ => "Unknown".to_string(),
    }
}

pub fn get_text() -> String {
    let mut buf = String::new();
    let registry = METRICS.registry.lock().unwrap_or_else(|e| e.into_inner());
    if let Err(e) = prometheus_client::encoding::text::encode(&mut buf, &registry) {
        log::warn!("Failed to encode Prometheus metrics: {e}");
    }
    buf
}

/// Instrument a data operation with metrics.
///
/// The expression must return `Result<T, AsError>`.
/// Returns `Result<T, PyErr>`.
#[macro_export]
macro_rules! timed_op {
    ($op:expr, $ns:expr, $set:expr, $body:expr) => {{
        let timer = $crate::metrics::OperationTimer::start($op, $ns, $set);
        let result = $body;
        match &result {
            Ok(_) => timer.finish(""),
            Err(e) => timer.finish(&$crate::metrics::error_type_from_aerospike_error(e)),
        }
        result.map_err($crate::errors::as_to_pyerr)
    }};
}
