//! Native Aerospike client for Python, implemented in Rust via PyO3.
//!
//! This crate provides both synchronous ([`client::PyClient`]) and asynchronous
//! ([`async_client::PyAsyncClient`]) wrappers around `aerospike_core`, exposing
//! them as Python classes through the `_aerospike` native module.

use log::info;
use pyo3::prelude::*;

mod async_client;
mod backpressure;
mod batch_types;
mod bug_report;
mod client;
mod client_common;
mod client_ops;
mod constants;
mod errors;
pub mod expressions;
mod logging;
pub mod metrics;
#[deny(unsafe_op_in_unsafe_fn)]
mod numpy_support;
mod operations;
pub mod panic_safety;
mod policy;
pub mod query;
mod record_helpers;
mod runtime;
pub mod tracing;
mod types;

/// Return collected metrics in Prometheus text format.
#[pyfunction]
fn get_metrics_text() -> String {
    metrics::get_text()
}

/// Enable or disable Prometheus metrics collection.
///
/// When disabled, operation timers are skipped entirely (~1ns atomic check).
/// Useful for benchmarking without metrics overhead.
#[pyfunction]
fn set_metrics_enabled(enabled: bool) {
    metrics::set_metrics_enabled(enabled);
}

/// Check if Prometheus metrics collection is currently enabled.
#[pyfunction]
fn is_metrics_enabled() -> bool {
    metrics::is_metrics_enabled()
}

/// Enable or disable internal stage profiling metrics
/// (`db_client_internal_stage_seconds`).
///
/// Separate from `set_metrics_enabled` — this flag controls fine-grained
/// profiling spans like `key_parse`, `io`, `into_pyobject`, etc. Default is
/// `false`. When disabled, all stage timer call sites skip `Instant::now()`
/// entirely (single atomic load, ~1ns).
#[pyfunction]
fn set_internal_stage_metrics_enabled(enabled: bool) {
    metrics::set_internal_stage_enabled(enabled);
}

/// Check if internal stage profiling metrics are currently enabled.
#[pyfunction]
fn is_internal_stage_metrics_enabled() -> bool {
    metrics::is_internal_stage_enabled()
}

/// Return the number of log messages dropped because the Python GIL
/// was unavailable (e.g. during interpreter shutdown).
#[pyfunction]
fn dropped_log_count() -> u64 {
    logging::dropped_log_count()
}

/// Native Aerospike Python client module
#[pymodule(gil_used = true)]
fn _aerospike(m: &Bound<'_, PyModule>) -> PyResult<()> {
    logging::init();

    // Configure the async Tokio runtime BEFORE any future_into_py() call.
    // Limits worker threads to reduce GIL contention in AsyncClient.
    runtime::init_async_runtime();

    // Read AEROSPIKE_PY_INTERNAL_METRICS=1 / true to enable stage profiling
    // at process start. Runtime toggle remains available via
    // `set_internal_stage_metrics_enabled`.
    metrics::init_internal_stage_from_env();

    // Register classes
    m.add_class::<client::PyClient>()?;
    m.add_class::<async_client::PyAsyncClient>()?;
    m.add_class::<query::PyQuery>()?;
    m.add_class::<batch_types::PyBatchRecord>()?;
    m.add_class::<batch_types::PyBatchRecords>()?;
    m.add_class::<batch_types::PyBatchReadHandle>()?;

    // Register functions
    m.add_function(wrap_pyfunction!(get_metrics_text, m)?)?;
    m.add_function(wrap_pyfunction!(set_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(is_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(set_internal_stage_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(is_internal_stage_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(dropped_log_count, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::init_tracing, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::shutdown_tracing, m)?)?;

    // Register exceptions
    errors::register_exceptions(m)?;

    // Register constants
    constants::register_constants(m)?;

    info!("aerospike-py native module initialized");
    Ok(())
}
