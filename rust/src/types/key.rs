//! Bidirectional conversion between Python key tuples and `aerospike_core::Key`.

use aerospike_core::{Key, Value};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList, PyString, PyTuple};
use ripemd::{Digest, Ripemd160};

use super::value::{py_to_value, value_to_py};

/// Compute a RIPEMD-160 digest for a bytes key using STRING particle type (3).
///
/// The official Python C client uses STRING particle type for bytes keys,
/// while the Rust client uses BLOB particle type (4). To ensure cross-client
/// compatibility, we compute the digest with STRING particle type.
fn compute_bytes_key_digest(set_name: &str, bytes_data: &[u8]) -> [u8; 20] {
    let mut hash = Ripemd160::new();
    hash.update(set_name.as_bytes());
    hash.update([3u8]); // ParticleType::STRING = 3
    hash.update(bytes_data);
    hash.finalize().into()
}

/// Convert a Python key tuple (namespace, set, key) to Rust Key
pub fn py_to_key(key_tuple: &Bound<'_, PyAny>) -> PyResult<Key> {
    trace!("Converting Python key to Rust key");
    let tuple = key_tuple.cast::<PyTuple>()?;

    if tuple.len() < 3 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Key tuple must have at least 3 elements: (namespace, set, key)",
        ));
    }

    let namespace: String = tuple.get_item(0)?.cast::<PyString>()?.to_str()?.to_owned();
    let set_name: String = tuple.get_item(1)?.cast::<PyString>()?.to_str()?.to_owned();
    let key_item = tuple.get_item(2)?;

    // For bytes keys, compute digest with STRING particle type (3) to match
    // the official Python C client behavior for cross-client compatibility.
    // Check this before py_to_value() to avoid a redundant Vec<u8> allocation.
    if let Ok(b) = key_item.cast::<PyBytes>() {
        let bytes_data = b.as_bytes();

        // Handle 4-element tuple with explicit digest
        if tuple.len() == 4 && !tuple.get_item(3)?.is_none() {
            let digest_bytes: Vec<u8> = tuple.get_item(3)?.extract()?;
            if digest_bytes.len() == 20 {
                let mut digest = [0u8; 20];
                digest.copy_from_slice(&digest_bytes);
                return Ok(Key {
                    namespace,
                    set_name,
                    user_key: Some(Value::Blob(bytes_data.to_vec())),
                    digest,
                });
            }
        }

        let digest = compute_bytes_key_digest(&set_name, bytes_data);
        return Ok(Key {
            namespace,
            set_name,
            user_key: Some(Value::Blob(bytes_data.to_vec())),
            digest,
        });
    }

    let user_key = py_to_value(&key_item)?;

    // Handle 4-element tuple with explicit digest
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

/// Convert a Python list of key tuples to a `Vec<Key>`.
pub fn py_to_keys(keys: &Bound<'_, PyList>) -> PyResult<Vec<Key>> {
    keys.iter().map(|k| py_to_key(&k)).collect()
}
