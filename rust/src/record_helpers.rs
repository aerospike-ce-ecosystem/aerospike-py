//! Helpers for converting Aerospike records and batch results to Python objects.

use aerospike_core::{BatchRecord, Error as AsError, Record, ResultCode};
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::errors::as_to_pyerr;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py_with_key;
use crate::types::value::value_to_py;

/// Convert Vec<BatchRecord> to Python list of (key, meta, bins) tuples.
pub fn batch_records_to_py(py: Python<'_>, results: &[BatchRecord]) -> PyResult<Py<PyAny>> {
    let items: Vec<Py<PyAny>> = results
        .iter()
        .map(|br| {
            let key_py = key_to_py(py, &br.key)?;
            match &br.record {
                Some(record) => {
                    let meta = record_to_meta(py, record)?;
                    let bins = PyDict::new(py);
                    for (name, value) in &record.bins {
                        bins.set_item(name, value_to_py(py, value)?)?;
                    }
                    let tuple = PyTuple::new(py, [key_py, meta, bins.into_any().unbind()])?;
                    Ok(tuple.into_any().unbind())
                }
                None => {
                    let tuple = PyTuple::new(py, [key_py, py.None(), py.None()])?;
                    Ok(tuple.into_any().unbind())
                }
            }
        })
        .collect::<PyResult<_>>()?;
    let py_list = PyList::new(py, &items)?;
    Ok(py_list.into_any().unbind())
}

/// Extract the TTL from a Record as seconds (u32).
///
/// Returns `0xFFFFFFFF` when the record has no TTL (never-expire).
pub fn record_ttl_seconds(record: &aerospike_core::Record) -> u32 {
    record
        .time_to_live()
        .map(|d| d.as_secs() as u32)
        .unwrap_or(0xFFFFFFFF_u32)
}

/// Extract meta dict from a Record.
pub fn record_to_meta(py: Python<'_>, record: &aerospike_core::Record) -> PyResult<Py<PyAny>> {
    let meta = PyDict::new(py);
    meta.set_item(intern!(py, "gen"), record.generation)?;
    meta.set_item(intern!(py, "ttl"), record_ttl_seconds(record))?;
    Ok(meta.into_any().unbind())
}

// ── Deferred conversion types for async client ─────────────────────
//
// These types hold Rust data from completed I/O and implement `IntoPyObject`
// so that `pyo3-async-runtimes::future_into_py` can convert them to Python
// objects inside the **single** GIL acquisition it already performs internally.
// This avoids the double-GIL-acquire that would happen if we called
// `Python::attach()` ourselves inside the future body.

/// Deferred record → Python conversion for `get`, `select`, `operate`.
pub struct PendingRecord {
    pub record: Record,
    pub key_py: Py<PyAny>,
}

impl<'py> IntoPyObject<'py> for PendingRecord {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        record_to_py_with_key(py, &self.record, self.key_py).map(|obj| obj.into_bound(py))
    }
}

/// Deferred exists result → Python conversion.
///
/// `Ok(record)` → `(key, meta_dict)`, `KeyNotFoundError` → `(key, None)`, other → `PyErr`.
pub struct PendingExists {
    pub result: Result<Record, AsError>,
    pub key_py: Py<PyAny>,
}

impl<'py> IntoPyObject<'py> for PendingExists {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self.result {
            Ok(record) => {
                let meta = record_to_meta(py, &record)?;
                let tuple = PyTuple::new(py, [self.key_py, meta])?;
                Ok(tuple.into_any())
            }
            Err(AsError::ServerError(ResultCode::KeyNotFoundError, _, _)) => {
                let tuple = PyTuple::new(py, [self.key_py, py.None()])?;
                Ok(tuple.into_any())
            }
            Err(e) => Err(as_to_pyerr(e)),
        }
    }
}

/// Deferred ordered record → Python conversion for `operate_ordered`.
///
/// Returns `(key, meta, [(bin_name, value), ...])` with bin order preserved.
pub struct PendingOrderedRecord {
    pub record: Record,
    pub key_py: Py<PyAny>,
}

impl<'py> IntoPyObject<'py> for PendingOrderedRecord {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let key_py = match &self.record.key {
            Some(k) => key_to_py(py, k)?,
            None => self.key_py,
        };
        let meta = record_to_meta(py, &self.record)?;
        let bin_items: Vec<Py<PyAny>> = self
            .record
            .bins
            .iter()
            .map(|(name, value)| {
                let tuple = PyTuple::new(
                    py,
                    [
                        name.as_str().into_pyobject(py)?.into_any().unbind(),
                        value_to_py(py, value)?,
                    ],
                )?;
                Ok(tuple.into_any().unbind())
            })
            .collect::<PyResult<_>>()?;
        let ordered_bins = PyList::new(py, &bin_items)?;
        let result = PyTuple::new(py, [key_py, meta, ordered_bins.into_any().unbind()])?;
        Ok(result.into_any())
    }
}
