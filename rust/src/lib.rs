//! Native Aerospike client for Python, implemented in Rust via PyO3.
//!
//! This crate provides both synchronous ([`client::PyClient`]) and asynchronous
//! ([`async_client::PyAsyncClient`]) wrappers around `aerospike_core`, exposing
//! them as Python classes through the `_aerospike` native module.

use log::info;
use pyo3::prelude::*;

mod async_client;
mod batch_types;
mod bug_report;
mod client;
mod client_common;
mod constants;
mod errors;
pub mod expressions;
mod logging;
pub mod metrics;
mod numpy_support;
mod operations;
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

/// Native Aerospike Python client module
#[pymodule(gil_used = true)]
fn _aerospike(m: &Bound<'_, PyModule>) -> PyResult<()> {
    logging::init();

    // Configure the async Tokio runtime BEFORE any future_into_py() call.
    // Limits worker threads to reduce GIL contention in AsyncClient.
    runtime::init_async_runtime();

    // Register classes
    m.add_class::<client::PyClient>()?;
    m.add_class::<async_client::PyAsyncClient>()?;
    m.add_class::<query::PyQuery>()?;
    m.add_class::<batch_types::PyBatchRecord>()?;
    m.add_class::<batch_types::PyBatchRecords>()?;

    // Register functions
    m.add_function(wrap_pyfunction!(get_metrics_text, m)?)?;
    m.add_function(wrap_pyfunction!(set_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(is_metrics_enabled, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::init_tracing, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::shutdown_tracing, m)?)?;

    // Register exceptions
    errors::register_exceptions(m)?;

    // Register constants
    constants::register_constants(m)?;

    info!("aerospike-py native module initialized");
    Ok(())
}
