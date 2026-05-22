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
pub(crate) fn compute_bytes_key_digest(set_name: &str, bytes_data: &[u8]) -> [u8; 20] {
    let mut hash = Ripemd160::new();
    hash.update(set_name.as_bytes());
    hash.update([3u8]); // ParticleType::STRING = 3
    hash.update(bytes_data);
    hash.finalize().into()
}

/// Extract an explicit 20-byte digest from element 3 of a key tuple.
///
/// Returns `Ok(Some(digest))` when a non-`None` 20-byte digest is present,
/// `Ok(None)` when element 3 is absent or `None`, and `Err(ValueError)` when
/// a digest is supplied but is not exactly 20 bytes.
///
/// A wrong-length digest was previously *silently ignored*: the client fell
/// back to recomputing the digest from the user key, so a caller that passed
/// a malformed digest (e.g. an off-by-one slice) addressed a different record
/// than intended with no error. Surfacing the error here makes that mistake
/// fail loudly instead of corrupting which record is read/written.
fn extract_explicit_digest(tuple: &Bound<'_, PyTuple>) -> PyResult<Option<[u8; 20]>> {
    if tuple.len() < 4 {
        return Ok(None);
    }
    let item = tuple.get_item(3)?;
    if item.is_none() {
        return Ok(None);
    }
    let digest_bytes: Vec<u8> = item.extract()?;
    if digest_bytes.len() != 20 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Key digest must be exactly 20 bytes, got {}",
            digest_bytes.len()
        )));
    }
    let mut digest = [0u8; 20];
    digest.copy_from_slice(&digest_bytes);
    Ok(Some(digest))
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
    if tuple.len() > 4 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Key tuple must have 3 or 4 elements (namespace, set, key[, digest]), got {}",
            tuple.len()
        )));
    }

    let namespace: String = tuple.get_item(0)?.cast::<PyString>()?.to_str()?.to_owned();
    let set_name: String = tuple.get_item(1)?.cast::<PyString>()?.to_str()?.to_owned();
    let key_item = tuple.get_item(2)?;
    let explicit_digest = extract_explicit_digest(tuple)?;

    // For bytes keys, compute digest with STRING particle type (3) to match
    // the official Python C client behavior for cross-client compatibility.
    // Check this before py_to_value() to avoid a redundant Vec<u8> allocation.
    if let Ok(b) = key_item.cast::<PyBytes>() {
        let bytes_data = b.as_bytes();
        let digest =
            explicit_digest.unwrap_or_else(|| compute_bytes_key_digest(&set_name, bytes_data));
        return Ok(Key {
            namespace,
            set_name,
            user_key: Some(Value::Blob(bytes_data.to_vec())),
            digest,
        });
    }

    let user_key = py_to_value(&key_item)?;

    if let Some(digest) = explicit_digest {
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Verify that `compute_bytes_key_digest` produces the expected RIPEMD-160
    /// output for a known input. The expected values were derived by computing
    /// RIPEMD-160(set_name + [3u8] + bytes_data) with OpenSSL and cross-checked
    /// against the official Aerospike Python C client digest for the same key.
    #[test]
    fn test_bytes_key_digest_known_value() {
        // RIPEMD-160("compat_edge" + [3] + b"\xde\xad\xbe\xef")
        let digest = compute_bytes_key_digest("compat_edge", &[0xde, 0xad, 0xbe, 0xef]);
        assert_eq!(
            digest,
            [
                0x9a, 0x34, 0x10, 0x64, 0xe9, 0x9c, 0xdf, 0x47, 0x32, 0xc5, 0xfc, 0x53, 0x8a, 0x47,
                0x84, 0x6b, 0x59, 0x87, 0x0f, 0x70,
            ]
        );
    }

    #[test]
    fn test_bytes_key_digest_empty_bytes() {
        // RIPEMD-160("compat_edge" + [3] + b"")
        let digest = compute_bytes_key_digest("compat_edge", &[]);
        assert_eq!(
            digest,
            [
                0x94, 0xbc, 0x78, 0x3d, 0x99, 0x12, 0xca, 0x79, 0x0f, 0x3e, 0x31, 0x88, 0x29, 0xd3,
                0xcc, 0x6a, 0xfd, 0xba, 0xef, 0x4d,
            ]
        );
    }

    #[test]
    fn test_bytes_key_digest_uses_string_particle_type() {
        // STRING particle type is 3; BLOB is 4. The two must produce different digests.
        let digest_string = compute_bytes_key_digest("myset", b"hello");
        // Manually compute BLOB variant (particle type 4) for comparison.
        let mut hash = ripemd::Ripemd160::new();
        ripemd::Digest::update(&mut hash, b"myset");
        ripemd::Digest::update(&mut hash, [4u8]); // BLOB
        ripemd::Digest::update(&mut hash, b"hello");
        let digest_blob: [u8; 20] = ripemd::Digest::finalize(hash).into();

        assert_ne!(
            digest_string, digest_blob,
            "STRING and BLOB particle types must yield different digests"
        );
    }

    /// Build a key tuple from a fixed namespace/set, a user key, and an
    /// optional 4th element (the explicit digest).
    fn make_key_tuple<'py>(
        py: Python<'py>,
        user_key: &Bound<'py, PyAny>,
        digest: Option<&Bound<'py, PyAny>>,
    ) -> Bound<'py, PyTuple> {
        let ns = PyString::new(py, "test").into_any();
        let set = PyString::new(py, "demo").into_any();
        match digest {
            Some(d) => PyTuple::new(py, [ns, set, user_key.clone(), d.clone()]).unwrap(),
            None => PyTuple::new(py, [ns, set, user_key.clone()]).unwrap(),
        }
    }

    /// A 3-element key tuple (no explicit digest) parses and gets a derived digest.
    #[test]
    fn py_to_key_three_element_tuple_parses() {
        Python::initialize();
        Python::attach(|py| {
            let user_key = PyString::new(py, "pk1").into_any();
            let tuple = make_key_tuple(py, &user_key, None);
            let key = py_to_key(tuple.as_any()).expect("3-element tuple should parse");
            assert_eq!(key.namespace, "test");
            assert_eq!(key.set_name, "demo");
        });
    }

    /// A 4-element key tuple with an explicit 20-byte digest is honored verbatim.
    #[test]
    fn py_to_key_accepts_explicit_20_byte_digest() {
        Python::initialize();
        Python::attach(|py| {
            let user_key = PyString::new(py, "pk1").into_any();
            let digest = PyBytes::new(py, &[7u8; 20]).into_any();
            let tuple = make_key_tuple(py, &user_key, Some(&digest));
            let key = py_to_key(tuple.as_any()).expect("explicit 20-byte digest should parse");
            assert_eq!(key.digest, [7u8; 20]);
        });
    }

    /// A 4-element tuple with a `None` digest falls back to the derived digest
    /// (no explicit digest supplied).
    #[test]
    fn py_to_key_none_digest_falls_back_to_derived() {
        Python::initialize();
        Python::attach(|py| {
            let user_key = PyString::new(py, "pk1").into_any();
            let none = py.None().into_bound(py);
            let tuple = make_key_tuple(py, &user_key, Some(&none));
            let key = py_to_key(tuple.as_any()).expect("None digest should parse");
            // The digest is derived, not all-zero.
            assert_ne!(key.digest, [0u8; 20]);
        });
    }

    /// A wrong-length explicit digest must raise `ValueError` instead of being
    /// silently ignored and replaced by a recomputed digest (data-targeting bug).
    #[test]
    fn py_to_key_rejects_malformed_digest_length() {
        Python::initialize();
        Python::attach(|py| {
            let user_key = PyString::new(py, "pk1").into_any();
            for bad_len in [0usize, 19, 21, 40] {
                let digest = PyBytes::new(py, &vec![0u8; bad_len]).into_any();
                let tuple = make_key_tuple(py, &user_key, Some(&digest));
                let err = py_to_key(tuple.as_any())
                    .expect_err("malformed digest length must be rejected");
                assert!(
                    err.is_instance_of::<pyo3::exceptions::PyValueError>(py),
                    "expected ValueError for {bad_len}-byte digest"
                );
                assert!(err.to_string().contains("20 bytes"));
            }
        });
    }

    /// A bytes user key with a wrong-length explicit digest is also rejected
    /// (the bytes path previously fell through and recomputed the digest).
    #[test]
    fn py_to_key_rejects_malformed_digest_for_bytes_key() {
        Python::initialize();
        Python::attach(|py| {
            let user_key = PyBytes::new(py, b"\x01\x02\x03").into_any();
            let digest = PyBytes::new(py, &[0u8; 10]).into_any();
            let tuple = make_key_tuple(py, &user_key, Some(&digest));
            let err = py_to_key(tuple.as_any())
                .expect_err("malformed digest for bytes key must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }

    /// A key tuple longer than 4 elements is a caller mistake and must be
    /// rejected rather than having the extra elements silently ignored.
    #[test]
    fn py_to_key_rejects_oversized_tuple() {
        Python::initialize();
        Python::attach(|py| {
            let ns = PyString::new(py, "test").into_any();
            let set = PyString::new(py, "demo").into_any();
            let user_key = PyString::new(py, "pk1").into_any();
            let digest = PyBytes::new(py, &[0u8; 20]).into_any();
            let extra = PyString::new(py, "extra").into_any();
            let tuple = PyTuple::new(py, [ns, set, user_key, digest, extra]).unwrap();
            let err = py_to_key(tuple.as_any()).expect_err("5-element key tuple must be rejected");
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
            assert!(err.to_string().contains("3 or 4 elements"));
        });
    }
}
