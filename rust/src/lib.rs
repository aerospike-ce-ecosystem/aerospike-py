use pyo3::prelude::*;

mod async_client;
mod client;
mod constants;
mod errors;
pub mod expressions;
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

    // Register exceptions
    errors::register_exceptions(m)?;

    // Register constants
    constants::register_constants(m)?;

    Ok(())
}
