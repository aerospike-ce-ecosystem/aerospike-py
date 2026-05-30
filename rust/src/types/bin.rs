//! Conversion from Python dicts to `aerospike_core::Bin` vectors.

use aerospike_core::Bin;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString};

use super::value::py_to_value;

/// Maximum bin name length in bytes, enforced by the Aerospike server.
const MAX_BIN_NAME_LEN: usize = 15;

/// Convert a Python dict of bins to a Vec<Bin>.
/// Bin values of None (Nil) are passed through — the server treats them
/// as bin deletion requests, matching the official Python client behavior.
pub fn py_dict_to_bins(dict: &Bound<'_, PyDict>) -> PyResult<Vec<Bin>> {
    let mut bins = Vec::with_capacity(dict.len());
    for (key, val) in dict.iter() {
        let name: String = key.cast::<PyString>()?.to_str()?.to_owned();
        // An empty bin name is invalid in Aerospike. Without this check it
        // used to fall through to `Bin::new("", ...)` and only fail at write
        // time with an opaque server-side parameter error, leaving the caller
        // unable to tell which bin was malformed. Reject it client-side with a
        // clear message, matching the over-length check below.
        if name.is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Bin name must not be empty",
            ));
        }
        if name.len() > MAX_BIN_NAME_LEN {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Bin name '{}' exceeds the {MAX_BIN_NAME_LEN}-byte limit ({} bytes)",
                name,
                name.len()
            )));
        }
        let value = py_to_value(&val)?;
        bins.push(Bin::new(name, value));
    }
    Ok(bins)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A normal bin name converts to a single `Bin`.
    #[test]
    fn py_dict_to_bins_accepts_valid_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("name", "alice").unwrap();
            let bins = py_dict_to_bins(&dict).expect("valid bin should convert");
            assert_eq!(bins.len(), 1);
            assert_eq!(bins[0].name, "name");
        });
    }

    /// A bin name of exactly 15 bytes is at the limit and accepted.
    #[test]
    fn py_dict_to_bins_accepts_15_byte_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            let name = "a".repeat(MAX_BIN_NAME_LEN);
            dict.set_item(&name, 1).unwrap();
            let bins = py_dict_to_bins(&dict).expect("15-byte name should convert");
            assert_eq!(bins.len(), 1);
            assert_eq!(bins[0].name, name);
        });
    }

    /// An empty bin name must be rejected client-side with a clear `ValueError`
    /// instead of being deferred to an opaque server-side parameter error.
    #[test]
    fn py_dict_to_bins_rejects_empty_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("", 1).unwrap();
            let err = py_dict_to_bins(&dict).expect_err("empty bin name must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
            assert!(err.to_string().contains("must not be empty"));
        });
    }

    /// A bin name longer than 15 bytes is rejected with the over-length error.
    #[test]
    fn py_dict_to_bins_rejects_oversized_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            let name = "a".repeat(MAX_BIN_NAME_LEN + 1);
            dict.set_item(&name, 1).unwrap();
            let err = py_dict_to_bins(&dict).expect_err("oversized bin name must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
            assert!(err.to_string().contains("exceeds the 15-byte limit"));
        });
    }
}
