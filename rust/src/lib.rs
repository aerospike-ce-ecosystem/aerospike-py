use pyo3::prelude::*;

mod async_client;
mod batch_types;
mod client;
mod constants;
mod errors;
pub mod expressions;
mod numpy_support;
mod operations;
mod policy;
pub mod query;
mod record_helpers;
mod runtime;
mod types;

/// Native Aerospike Python client module
#[pymodule]
fn _aerospike(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register classes
    m.add_class::<client::PyClient>()?;
    m.add_class::<async_client::PyAsyncClient>()?;
    m.add_class::<query::PyQuery>()?;
    m.add_class::<query::PyScan>()?;
    m.add_class::<batch_types::PyBatchRecord>()?;
    m.add_class::<batch_types::PyBatchRecords>()?;

    // Register exceptions
    errors::register_exceptions(m)?;

    // Register constants
    constants::register_constants(m)?;

    Ok(())
}
