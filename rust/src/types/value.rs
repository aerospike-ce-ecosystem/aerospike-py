use aerospike_core::Value;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::HashMap;

/// Convert a Python object to an Aerospike Value
pub fn py_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.is_none() {
        return Ok(Value::Nil);
    }
    if let Ok(b) = obj.cast::<PyBool>() {
        return Ok(Value::Bool(b.is_true()));
    }
    if let Ok(i) = obj.cast::<PyInt>() {
        let val: i64 = i.extract()?;
        return Ok(Value::Int(val));
    }
    if let Ok(f) = obj.cast::<PyFloat>() {
        let val: f64 = f.extract()?;
        return Ok(Value::Float(aerospike_core::FloatValue::from(val)));
    }
    if let Ok(s) = obj.cast::<PyString>() {
        let val: String = s.extract()?;
        return Ok(Value::String(val));
    }
    if let Ok(b) = obj.cast::<PyBytes>() {
        let val: Vec<u8> = b.extract()?;
        return Ok(Value::Blob(val));
    }
    if let Ok(list) = obj.cast::<PyList>() {
        let mut values = Vec::with_capacity(list.len());
        for item in list.iter() {
            values.push(py_to_value(&item)?);
        }
        return Ok(Value::List(values));
    }
    if let Ok(dict) = obj.cast::<PyDict>() {
        let mut map = HashMap::new();
        for (k, v) in dict.iter() {
            let key = py_to_value(&k)?;
            let val = py_to_value(&v)?;
            map.insert(key, val);
        }
        return Ok(Value::HashMap(map));
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
            let py_list = PyList::empty(py);
            for item in list {
                py_list.append(value_to_py(py, item)?)?;
            }
            Ok(py_list.into_any().unbind())
        }
        Value::HashMap(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(value_to_py(py, k)?, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        Value::OrderedMap(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(value_to_py(py, k)?, value_to_py(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
        Value::KeyValueList(pairs) => {
            let py_list = PyList::empty(py);
            for (k, v) in pairs {
                let tuple = (value_to_py(py, k)?, value_to_py(py, v)?);
                py_list.append(tuple)?;
            }
            Ok(py_list.into_any().unbind())
        }
        Value::GeoJSON(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::HLL(b) => Ok(PyBytes::new(py, b).into_any().unbind()),
        Value::Infinity => Ok(py.None()),
        Value::Wildcard => Ok(py.None()),
    }
}
