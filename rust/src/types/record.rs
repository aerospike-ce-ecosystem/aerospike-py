use aerospike_core::{Key, Record};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use super::key::key_to_py;
use super::value::value_to_py;

/// Convert a Rust Record to a Python tuple: (key, meta, bins)
/// key = (namespace, set, user_key, digest)
/// meta = {"gen": generation, "ttl": ttl_seconds}
/// bins = {"bin_name": value, ...}
///
/// When the server does not return a key (e.g. POLICY_KEY_DIGEST),
/// `fallback_key` is used so the caller always gets a valid key tuple.
pub fn record_to_py(
    py: Python<'_>,
    record: &Record,
    fallback_key: Option<&Key>,
) -> PyResult<Py<PyAny>> {
    trace!("Converting Rust record to Python");
    // Key tuple: prefer the key from the record, fall back to the original request key.
    // The aerospike_core crate does not populate record.key from server responses,
    // so we use the caller-provided key to ensure a valid key tuple is always returned.
    let key_py = match &record.key {
        Some(key) => key_to_py(py, key)?,
        None => match fallback_key {
            Some(key) => key_to_py(py, key)?,
            None => py.None(),
        },
    };

    // Meta dict
    let meta = PyDict::new(py);
    meta.set_item("gen", record.generation)?;
    let ttl = match record.time_to_live() {
        Some(duration) => duration.as_secs() as u32,
        None => 0xFFFFFFFF_u32,
    };
    meta.set_item("ttl", ttl)?;

    // Bins dict
    let bins = PyDict::new(py);
    for (name, value) in &record.bins {
        bins.set_item(name, value_to_py(py, value)?)?;
    }

    let tuple = PyTuple::new(
        py,
        [key_py, meta.into_any().unbind(), bins.into_any().unbind()],
    )?;
    Ok(tuple.into_any().unbind())
}
