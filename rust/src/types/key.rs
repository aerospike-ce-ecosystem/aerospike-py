//! Bidirectional conversion between Python key tuples and `aerospike_core::Key`.

use aerospike_core::{Key, Value};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

use super::value::{py_to_value, value_to_py};

/// Convert a Python key tuple (namespace, set, key) to Rust Key
pub fn py_to_key(key_tuple: &Bound<'_, PyAny>) -> PyResult<Key> {
    trace!("Converting Python key to Rust key");
    let tuple = key_tuple.cast::<PyTuple>()?;

    if tuple.len() < 3 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Key tuple must have at least 3 elements: (namespace, set, key)",
        ));
    }

    let namespace: String = tuple.get_item(0)?.extract()?;
    let set_name: String = tuple.get_item(1)?.extract()?;
    let user_key = py_to_value(&tuple.get_item(2)?)?;

    // Handle 4-element tuple with digest
    if tuple.len() == 4 && !tuple.get_item(3)?.is_none() {
        let digest_bytes: Vec<u8> = tuple.get_item(3)?.extract()?;
        if digest_bytes.len() == 20 {
            let mut digest = [0u8; 20];
            digest.copy_from_slice(&digest_bytes);
            return Ok(Key {
                namespace,
                set_name,
                user_key: match &user_key {
                    Value::Nil => None,
                    _ => Some(user_key),
                },
                digest,
            });
        }
    }

    Key::new(namespace, set_name, user_key)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid key: {e}")))
}

/// Convert Rust Key to Python tuple (namespace, set, key, digest)
pub fn key_to_py(py: Python<'_>, key: &Key) -> PyResult<Py<PyAny>> {
    let ns = key.namespace.as_str().into_pyobject(py)?;
    let set = key.set_name.as_str().into_pyobject(py)?;
    let user_key = match &key.user_key {
        Some(v) => value_to_py(py, v)?,
        None => py.None(),
    };
    let digest = pyo3::types::PyBytes::new(py, &key.digest);

    let tuple = PyTuple::new(
        py,
        [
            ns.into_any().unbind(),
            set.into_any().unbind(),
            user_key,
            digest.into_any().unbind(),
        ],
    )?;
    Ok(tuple.into_any().unbind())
}
