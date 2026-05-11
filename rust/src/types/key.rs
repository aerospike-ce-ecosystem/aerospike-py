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

    build_key(namespace, set_name, &key_item, &tuple)
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
///
/// Fast path for batches whose keys share `(namespace, set)`: caches the
/// most recently seen Python string objects by pointer identity. When the
/// next key's namespace or set is the same Python object as the previous
/// one (the typical case — callers usually pass interned set names), the
/// `PyString` cast and UTF-8 validation runs once and subsequent keys
/// reuse the cached `String` via `clone()` instead.
///
/// `aerospike_core::Key` requires owned `String` fields so we still pay
/// one allocation per key, but skip the PyString round-trip.
pub fn py_to_keys(keys: &Bound<'_, PyList>) -> PyResult<Vec<Key>> {
    let mut last_ns: Option<(*const pyo3::ffi::PyObject, String)> = None;
    let mut last_set: Option<(*const pyo3::ffi::PyObject, String)> = None;
    keys.iter()
        .map(|k| py_to_key_with_cache(&k, &mut last_ns, &mut last_set))
        .collect()
}

/// Single-key conversion with caller-provided `(ns, set)` caches.
///
/// Each cache slot tracks the Python pointer of the most recently extracted
/// `PyString` plus its owned `String`. A cache hit (pointer match) clones
/// the cached `String`; a miss falls back to a full PyString extraction
/// and overwrites the slot.
fn py_to_key_with_cache(
    key_tuple: &Bound<'_, PyAny>,
    last_ns: &mut Option<(*const pyo3::ffi::PyObject, String)>,
    last_set: &mut Option<(*const pyo3::ffi::PyObject, String)>,
) -> PyResult<Key> {
    let tuple = key_tuple.cast::<PyTuple>()?;
    if tuple.len() < 3 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Key tuple must have at least 3 elements: (namespace, set, key)",
        ));
    }

    let ns_item = tuple.get_item(0)?;
    let namespace = extract_cached_str(&ns_item, last_ns)?;
    let set_item = tuple.get_item(1)?;
    let set_name = extract_cached_str(&set_item, last_set)?;
    let key_item = tuple.get_item(2)?;

    build_key(namespace, set_name, &key_item, &tuple)
}

/// Resolve a `PyString` to an owned `String`, reusing the cached value
/// when the input is the same Python object as the previous extraction.
fn extract_cached_str(
    item: &Bound<'_, PyAny>,
    last: &mut Option<(*const pyo3::ffi::PyObject, String)>,
) -> PyResult<String> {
    let ptr = item.as_ptr() as *const _;
    if let Some((cached_ptr, cached_str)) = last.as_ref() {
        if *cached_ptr == ptr {
            return Ok(cached_str.clone());
        }
    }
    let owned = item.cast::<PyString>()?.to_str()?.to_owned();
    *last = Some((ptr, owned.clone()));
    Ok(owned)
}

/// Common key construction shared between `py_to_key` and the cached path.
/// Handles bytes keys (digest computed with STRING particle type for C
/// client compatibility), explicit 4-element digest tuples, and the
/// fallback `Key::new` path for typed user keys.
fn build_key(
    namespace: String,
    set_name: String,
    key_item: &Bound<'_, PyAny>,
    tuple: &Bound<'_, PyTuple>,
) -> PyResult<Key> {
    if let Ok(b) = key_item.cast::<PyBytes>() {
        let bytes_data = b.as_bytes();

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

    let user_key = py_to_value(key_item)?;

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

    /// `py_to_keys` caches `(ns, set)` Python strings by pointer identity
    /// — verify that passing the same Python `str` for `ns` across many
    /// tuples produces correctly-extracted `Key`s without divergence.
    #[test]
    fn test_py_to_keys_caches_repeated_ns_set() {
        Python::initialize();
        Python::attach(|py| {
            // Use a single interned Python string for `ns` shared across all
            // tuples — exercises the pointer-identity cache hit path.
            let ns = pyo3::types::PyString::new(py, "test");
            let set_a = pyo3::types::PyString::new(py, "set_a");
            let keys: Vec<Bound<'_, pyo3::types::PyAny>> = (0..5)
                .map(|i| {
                    PyTuple::new(
                        py,
                        [
                            ns.as_any().clone(),
                            set_a.as_any().clone(),
                            pyo3::types::PyString::new(py, &format!("k{i}"))
                                .as_any()
                                .clone(),
                        ],
                    )
                    .unwrap()
                    .into_any()
                })
                .collect();
            let list = PyList::new(py, &keys).unwrap();

            let result = py_to_keys(&list).unwrap();
            assert_eq!(result.len(), 5);
            for (i, k) in result.iter().enumerate() {
                assert_eq!(k.namespace, "test");
                assert_eq!(k.set_name, "set_a");
                let expected_key = format!("k{i}");
                match &k.user_key {
                    Some(Value::String(s)) => assert_eq!(s, &expected_key),
                    other => panic!("unexpected user_key: {other:?}"),
                }
            }
        });
    }

    /// Cache must invalidate when the `ns` Python object changes between
    /// keys — verify that mixing two namespaces in one batch produces
    /// the correct `Key.namespace` for each entry.
    #[test]
    fn test_py_to_keys_cache_invalidates_on_change() {
        Python::initialize();
        Python::attach(|py| {
            let ns_a = pyo3::types::PyString::new(py, "ns_a");
            let ns_b = pyo3::types::PyString::new(py, "ns_b");
            let set = pyo3::types::PyString::new(py, "set");
            let keys: Vec<Bound<'_, pyo3::types::PyAny>> = (0..4)
                .map(|i| {
                    let ns = if i % 2 == 0 { &ns_a } else { &ns_b };
                    PyTuple::new(
                        py,
                        [
                            ns.as_any().clone(),
                            set.as_any().clone(),
                            pyo3::types::PyString::new(py, &format!("k{i}"))
                                .as_any()
                                .clone(),
                        ],
                    )
                    .unwrap()
                    .into_any()
                })
                .collect();
            let list = PyList::new(py, &keys).unwrap();

            let result = py_to_keys(&list).unwrap();
            assert_eq!(result.len(), 4);
            assert_eq!(result[0].namespace, "ns_a");
            assert_eq!(result[1].namespace, "ns_b");
            assert_eq!(result[2].namespace, "ns_a");
            assert_eq!(result[3].namespace, "ns_b");
        });
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
}
