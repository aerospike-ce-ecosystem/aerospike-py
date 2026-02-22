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

/// Native Aerospike Python client module
#[pymodule(gil_used = true)]
fn _aerospike(m: &Bound<'_, PyModule>) -> PyResult<()> {
    logging::init();

    // Register classes
    m.add_class::<client::PyClient>()?;
    m.add_class::<async_client::PyAsyncClient>()?;
    m.add_class::<query::PyQuery>()?;
    m.add_class::<batch_types::PyBatchRecord>()?;
    m.add_class::<batch_types::PyBatchRecords>()?;

    // Register functions
    m.add_function(wrap_pyfunction!(get_metrics_text, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::init_tracing, m)?)?;
    m.add_function(wrap_pyfunction!(tracing::shutdown_tracing, m)?)?;

    // Register exceptions
    errors::register_exceptions(m)?;

    // Register constants
    constants::register_constants(m)?;

    info!("aerospike-py native module initialized");
    Ok(())
}
