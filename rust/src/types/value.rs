//! Bidirectional conversion between Python objects and `aerospike_core::Value`.

use aerospike_core::{IndexMap, Value};
use log::{debug, warn};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyByteArray, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString};
use std::sync::atomic::{AtomicBool, Ordering};

/// Maximum recursion depth for nested list/dict values to prevent stack overflow.
const MAX_NESTING_DEPTH: usize = 64;

/// Whether a value of each particle type the client does not interpret has
/// already been announced in the log (indexed by the particle type).
static UNKNOWN_PARTICLE_ANNOUNCED: [AtomicBool; 256] = [const { AtomicBool::new(false) }; 256];

/// Convert a Python object to an Aerospike Value
pub fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    py_to_value_inner(obj, 0)
}

fn py_to_value_inner(obj: &Bound<'_, PyAny>, depth: usize) -> PyResult<Value> {
    if depth > MAX_NESTING_DEPTH {
        warn!(
            "Value nesting exceeds maximum depth of {}",
            MAX_NESTING_DEPTH
        );
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Value nesting exceeds maximum depth of {MAX_NESTING_DEPTH}"
        )));
    }
    if obj.is_none() {
        return Ok(Value::Nil);
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(Value::Bool(b.is_true()));
    }
    if let Ok(i) = obj.cast::<PyInt>() {
        // Aerospike's integer particle is a 64-bit two's-complement value.
        // Accept Python ints in [2^63, 2^64-1] (e.g. large unsigned values written
        // by the official C client) by bit-reinterpreting them as i64.
        match i.extract::<i64>() {
            Ok(val) => return Ok(Value::Int(val)),
            Err(i64_err) => match i.extract::<u64>() {
                Ok(u) => return Ok(Value::Int(u as i64)),
                Err(_) => return Err(i64_err),
            },
        }
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        let val: f64 = f.extract()?;
        return Ok(Value::Float(aerospike_core::FloatValue::from(val)));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        return Ok(Value::String(s.to_str()?.to_owned()));
    }
    if let Ok(b) = obj.cast::<PyBytes>() {
        return Ok(Value::Blob(b.as_bytes().to_vec()));
    }
    if let Ok(b) = obj.cast::<PyByteArray>() {
        // `bytearray` is the mutable counterpart of `bytes`; several public
        // signatures (e.g. `bit_operations.bit_insert(value: Union[bytes,
        // bytearray])`) advertise it. `to_vec()` snapshots the current contents,
        // which is safe even though the underlying buffer can be mutated later.
        return Ok(Value::Blob(b.to_vec()));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        let mut values = Vec::with_capacity(list.len());
        for item in list.iter() {
            values.push(py_to_value_inner(&item, depth + 1)?);
        }
        return Ok(Value::List(values));
    }
    if let Ok(dict) = obj.cast::<PyDict>() {
        // `OrderedMap` is an insertion-ordered map that is still an unordered
        // map on the wire, so the entries reach the server in the order the
        // Python dict holds them. A `HashMap` would send them in hash order,
        // which changes from run to run.
        let mut map = IndexMap::with_capacity(dict.len());
        for (k, v) in dict.iter() {
            let key = py_to_value_inner(&k, depth + 1)?;
            let val = py_to_value_inner(&v, depth + 1)?;
            map.insert(key, val);
        }
        return Ok(Value::OrderedMap(map));
    }

    Err(pyo3::exceptions::PyTypeError::new_err(format!(
        "Unsupported type for Aerospike value: {}",
        obj.get_type().name()?
    )))
}

/// Convert an Aerospike Value to a Python object
pub fn value_to_py(py: Python<'_>, val: &Value) -> PyResult<Py<PyAny>> {
    match val {
        Value::Nil => Ok(py.None()),
        Value::Bool(b) => Ok((*b).into_pyobject(py)?.to_owned().into_any().unbind()),
        Value::Int(i) => Ok(i.into_pyobject(py)?.into_any().unbind()),
        Value::Float(f) => {
            let fval: f64 = f64::from(f);
            Ok(fval.into_pyobject(py)?.into_any().unbind())
        }
        Value::String(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::Blob(b) => Ok(PyBytes::new(py, b).into_any().unbind()),
        Value::List(list) | Value::MultiResult(list) => {
            let items: Vec<Py<PyAny>> = list
                .iter()
                .map(|item| value_to_py(py, item))
                .collect::<PyResult<_>>()?;
            let py_list = PyList::new(py, &items)?;
            Ok(py_list.into_any().unbind())
        }
        Value::HashMap(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(value_to_py(py, k)?, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        // The server's maps decode as `OrderedMap` in the order the server
        // returned the entries; the Python dict keeps that order.
        Value::OrderedMap(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(value_to_py(py, k)?, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        Value::SortedMap(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(value_to_py(py, k)?, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        Value::KeyValueList(pairs) => {
            let items: Vec<(Py<PyAny>, Py<PyAny>)> = pairs
                .iter()
                .map(|(k, v)| Ok((value_to_py(py, k)?, value_to_py(py, v)?)))
                .collect::<PyResult<_>>()?;
            let py_list = PyList::new(py, &items)?;
            Ok(py_list.into_any().unbind())
        }
        Value::GeoJson(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::Hll(b) => Ok(PyBytes::new(py, b).into_any().unbind()),
        Value::Infinity => Ok(py.None()),
        Value::Wildcard => Ok(py.None()),
        // A particle type the Rust client does not interpret — in practice a
        // language-specific blob written by an old client (PYTHON_BLOB,
        // JAVA_BLOB, ...). Rust client 2.x panicked on these (issue #280);
        // 3.0 hands over the raw payload, which is returned as `bytes` so the
        // rest of the record stays readable.
        Value::Unknown(particle_type, bytes) => {
            // Once per particle type and process at WARNING: a scan over old
            // data meets such a value in every record, and a warning for each
            // would bury the log and slow the scan down.
            if UNKNOWN_PARTICLE_ANNOUNCED[usize::from(*particle_type)].swap(true, Ordering::Relaxed)
            {
                debug!(
                    "bin value has particle type {particle_type}, which this client does not \
                     interpret; returning its {} raw bytes",
                    bytes.len()
                );
            } else {
                warn!(
                    "bin value has particle type {particle_type}, which this client does not \
                     interpret; returning its {} raw bytes (further values of this type are \
                     logged at debug level)",
                    bytes.len()
                );
            }
            Ok(PyBytes::new(py, bytes).into_any().unbind())
        }
        // `Value` is non-exhaustive: a variant added by a newer Rust client
        // must not be silently turned into something else.
        other => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "Unsupported Aerospike value type: {other:?}"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `i64`-range ints convert as-is.
    #[test]
    fn py_to_value_accepts_i64_range_ints() {
        Python::initialize();
        Python::attach(|py| {
            for n in [0_i64, 1, -1, i64::MAX, i64::MIN] {
                let obj = n.into_pyobject(py).expect("int");
                match py_to_value(&obj.into_any()).expect("i64 should convert") {
                    Value::Int(v) => assert_eq!(v, n),
                    other => panic!("expected Value::Int, got {other:?}"),
                }
            }
        });
    }

    /// Python ints in `[2^63, 2^64-1]` (e.g. large unsigned values from the
    /// official C client) are bit-reinterpreted into the i64 integer particle
    /// instead of being rejected with OverflowError.
    #[test]
    fn py_to_value_accepts_uint64_range_ints() {
        Python::initialize();
        Python::attach(|py| {
            for u in [1_u64 << 63, u64::MAX, (1_u64 << 63) + 12345] {
                let obj = u.into_pyobject(py).expect("uint");
                match py_to_value(&obj.into_any()).expect("u64 should convert") {
                    Value::Int(v) => assert_eq!(v as u64, u, "bit-reinterpretation round-trip"),
                    other => panic!("expected Value::Int, got {other:?}"),
                }
            }
        });
    }

    /// `bytes` convert to a `Value::Blob`.
    #[test]
    fn py_to_value_accepts_bytes() {
        Python::initialize();
        Python::attach(|py| {
            let obj = PyBytes::new(py, b"\x00\x01\xff");
            match py_to_value(&obj.into_any()).expect("bytes should convert") {
                Value::Blob(b) => assert_eq!(b, vec![0u8, 1, 255]),
                other => panic!("expected Value::Blob, got {other:?}"),
            }
        });
    }

    /// `bytearray` (the mutable counterpart of `bytes`, advertised by several
    /// public signatures such as `bit_operations.bit_insert`) converts to the
    /// same `Value::Blob` as the equivalent `bytes`, instead of raising
    /// `TypeError: Unsupported type for Aerospike value: bytearray`.
    #[test]
    fn py_to_value_accepts_bytearray() {
        Python::initialize();
        Python::attach(|py| {
            let obj = PyByteArray::new(py, b"\x00\x01\xff");
            match py_to_value(&obj.into_any()).expect("bytearray should convert") {
                Value::Blob(b) => assert_eq!(b, vec![0u8, 1, 255]),
                other => panic!("expected Value::Blob, got {other:?}"),
            }
        });
    }

    /// An empty `bytearray` round-trips to an empty `Value::Blob`.
    #[test]
    fn py_to_value_accepts_empty_bytearray() {
        Python::initialize();
        Python::attach(|py| {
            let obj = PyByteArray::new(py, b"");
            match py_to_value(&obj.into_any()).expect("empty bytearray should convert") {
                Value::Blob(b) => assert!(b.is_empty()),
                other => panic!("expected Value::Blob, got {other:?}"),
            }
        });
    }

    /// Ints that fit neither i64 nor u64 still propagate the original error.
    #[test]
    fn py_to_value_rejects_ints_beyond_uint64() {
        Python::initialize();
        Python::attach(|py| {
            // Build `2**64` (one past the u64 ceiling) as a Python int.
            let max_u64 = u64::MAX.into_pyobject(py).expect("u64::MAX");
            let one = 1_u64.into_pyobject(py).expect("one");
            let huge = max_u64
                .add(one)
                .expect("u64::MAX + 1 is a valid Python big int");
            assert!(
                py_to_value(&huge).is_err(),
                "values beyond u64 range must still raise"
            );
        });
    }
}
