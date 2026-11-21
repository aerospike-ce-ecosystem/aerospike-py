//! Helpers for converting Aerospike records and batch results to Python objects.

use aerospike_core::{Error as AsError, Record};
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use std::time::Duration;

use crate::errors::as_to_pyerr;
use crate::types::record::record_to_py_with_key;

/// Extract the TTL from a Record as seconds (u32).
///
/// Returns `0xFFFFFFFF` when the record has no TTL (never-expire).
pub fn record_ttl_seconds(record: &aerospike_core::Record) -> u32 {
    ttl_from_duration(record.time_to_live())
}

/// Convert an optional TTL duration to the Python-exposed u32 TTL value.
///
/// `None` means never-expire. Durations above `u32::MAX` are clamped to avoid
/// wraparound when converting from `u64` seconds.
pub fn ttl_from_duration(ttl: Option<Duration>) -> u32 {
    match ttl {
        Some(duration) => duration.as_secs().min(u32::MAX as u64) as u32,
        None => 0xFFFFFFFF_u32,
    }
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
            Err(e) if crate::errors::is_key_not_found(&e) => {
                let tuple = PyTuple::new(py, [self.key_py, py.None()])?;
                Ok(tuple.into_any())
            }
            Err(e) => Err(as_to_pyerr(e)),
        }
    }
}

/// Deferred `operate` result → Python conversion: `(key, meta, {bin: value})`.
pub struct PendingOperateRecord {
    pub record: Record,
    pub key_py: Py<PyAny>,
}

impl<'py> IntoPyObject<'py> for PendingOperateRecord {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        crate::operate_result::operate_record_to_py(py, &self.record, self.key_py)
            .map(|obj| obj.into_bound(py))
    }
}

/// Deferred `operate_ordered` result → Python conversion:
/// `(key, meta, [(bin_name, value), ...])` in request order.
pub struct PendingOrderedRecord {
    pub record: Record,
    pub plan: crate::operate_result::OrderedPlan,
    pub key_py: Py<PyAny>,
}

impl<'py> IntoPyObject<'py> for PendingOrderedRecord {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        crate::operate_result::ordered_record_to_py(py, &self.record, &self.plan, self.key_py)
            .map(|obj| obj.into_bound(py))
    }
}

#[cfg(test)]
mod tests {
    use super::ttl_from_duration;
    use std::time::Duration;

    #[test]
    fn ttl_from_duration_none_maps_to_never_expire() {
        assert_eq!(ttl_from_duration(None), 0xFFFFFFFF_u32);
    }

    #[test]
    fn ttl_from_duration_in_range_seconds() {
        assert_eq!(ttl_from_duration(Some(Duration::from_secs(123))), 123_u32);
    }

    #[test]
    fn ttl_from_duration_clamps_above_u32_max() {
        let overflow = u32::MAX as u64 + 42;
        assert_eq!(
            ttl_from_duration(Some(Duration::from_secs(overflow))),
            u32::MAX
        );
    }
}
