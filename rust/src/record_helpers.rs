//! Helpers for converting Aerospike records and batch results to Python objects.

use aerospike_core::BatchRecord;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::types::key::key_to_py;
use crate::types::value::value_to_py;

/// Convert Vec<BatchRecord> to Python list of (key, meta, bins) tuples.
pub fn batch_records_to_py(py: Python<'_>, results: &[BatchRecord]) -> PyResult<Py<PyAny>> {
    let py_list = PyList::empty(py);
    for br in results {
        let key_py = key_to_py(py, &br.key)?;
        match &br.record {
            Some(record) => {
                let meta = record_to_meta(py, record)?;
                let bins = PyDict::new(py);
                for (name, value) in &record.bins {
                    bins.set_item(name, value_to_py(py, value)?)?;
                }
                let tuple = PyTuple::new(py, [key_py, meta, bins.into_any().unbind()])?;
                py_list.append(tuple)?;
            }
            None => {
                let tuple = PyTuple::new(py, [key_py, py.None(), py.None()])?;
                py_list.append(tuple)?;
            }
        }
    }
    Ok(py_list.into_any().unbind())
}

/// Extract meta dict from a Record.
pub fn record_to_meta(py: Python<'_>, record: &aerospike_core::Record) -> PyResult<Py<PyAny>> {
    let meta = PyDict::new(py);
    meta.set_item("gen", record.generation)?;
    let ttl: u32 = record
        .time_to_live()
        .map(|d| d.as_secs() as u32)
        .unwrap_or(0xFFFFFFFF_u32);
    meta.set_item("ttl", ttl)?;
    Ok(meta.into_any().unbind())
}
