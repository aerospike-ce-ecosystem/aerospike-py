//! Conversion from `aerospike_core::Record` to the Python `(key, meta, bins)` tuple.

use aerospike_core::{Key, Record};
use log::trace;
use pyo3::intern;
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
///
/// If `pre_key_py` is provided, it is used directly as the key tuple
/// instead of converting `fallback_key` again (avoids double conversion).
pub fn record_to_py(
    py: Python<'_>,
    record: &Record,
    fallback_key: Option<&Key>,
) -> PyResult<Py<PyAny>> {
    record_to_py_inner(py, record, fallback_key, None)
}

/// Like `record_to_py` but accepts a pre-converted Python key to avoid
/// redundant Rust→Python key conversion.
pub fn record_to_py_with_key(
    py: Python<'_>,
    record: &Record,
    pre_key_py: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    record_to_py_inner(py, record, None, Some(pre_key_py))
}

fn record_to_py_inner(
    py: Python<'_>,
    record: &Record,
    fallback_key: Option<&Key>,
    pre_key_py: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    trace!("Converting Rust record to Python");
    // Key tuple: prefer the key returned by the server (honours POLICY_KEY_SEND),
    // then the pre-converted key (avoids re-conversion), fall back to the original request key.
    let key_py = match &record.key {
        Some(key) => key_to_py(py, key)?,
        None => match pre_key_py {
            Some(k) => k,
            None => match fallback_key {
                Some(key) => key_to_py(py, key)?,
                None => py.None(),
            },
        },
    };

    // Meta dict — use interned keys to avoid repeated string allocation
    let meta = PyDict::new(py);
    meta.set_item(intern!(py, "gen"), record.generation)?;
    let ttl = match record.time_to_live() {
        Some(duration) => duration.as_secs() as u32,
        None => 0xFFFFFFFF_u32,
    };
    meta.set_item(intern!(py, "ttl"), ttl)?;

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
