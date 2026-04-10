//! Python-visible batch record types for all batch operations
//! (`batch_read`, `batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`).
//!
//! Uses **lazy conversion** for the `record` field: bins are NOT converted to
//! Python until the user accesses `br.record`. This reduces GIL hold time by
//! 70-80% for large batches where not all records' bins are accessed.

use std::sync::{Arc, Mutex};

use aerospike_core::{BatchRecord, Record, ResultCode};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::errors::result_code_to_int;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py_with_key;

// ── Lazy record cell ─────────────────────────────────────────────

/// Holds either raw Rust Record data (pre-conversion) or the cached
/// Python tuple `(key, meta, bins)` after first access.
///
/// Uses `Mutex` to satisfy `Send + Sync` required by `#[pyclass]`.
/// In practice, all access is single-threaded (GIL held), so contention is zero.
enum LazyRecordCell {
    /// Raw Rust Record awaiting lazy conversion.
    Pending {
        record: Record,
        key_py: Py<PyAny>,
    },
    /// Already converted to Python `(key, meta, bins)` tuple — cached.
    Converted(Py<PyAny>),
    /// Record not found (None).
    None,
}

impl LazyRecordCell {
    /// Convert to Python on first access; cache for subsequent accesses.
    #[allow(clippy::wrong_self_convention)]
    fn to_python(&mut self, py: Python) -> PyResult<Py<PyAny>> {
        match self {
            LazyRecordCell::Pending { record, key_py } => {
                let py_obj = record_to_py_with_key(py, record, key_py.clone_ref(py))?;
                *self = LazyRecordCell::Converted(py_obj.clone_ref(py));
                Ok(py_obj)
            }
            LazyRecordCell::Converted(cached) => Ok(cached.clone_ref(py)),
            LazyRecordCell::None => Ok(py.None()),
        }
    }
}

// ── PyBatchRecord ────────────────────────────────────────────────

/// A single record within batch results, exposed to Python.
///
/// The `record` field uses lazy conversion: bins are only converted
/// from Rust to Python when `br.record` is first accessed.
#[pyclass(name = "BatchRecord")]
pub struct PyBatchRecord {
    #[pyo3(get)]
    key: Py<PyAny>,
    #[pyo3(get)]
    result: i32,
    /// Lazy-converted record cell. `Mutex` satisfies `Send + Sync` for pyclass.
    /// In practice, the GIL prevents concurrent access from Python.
    record_cell: Mutex<LazyRecordCell>,
    #[pyo3(get)]
    in_doubt: bool,
}

#[pymethods]
impl PyBatchRecord {
    /// Lazily convert the record to Python `(key, meta, bins)` tuple.
    /// Returns `None` if the record was not found.
    #[getter]
    fn record(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.record_cell.lock().unwrap().to_python(py)
    }
}

/// Container holding a list of [`PyBatchRecord`]s, exposed to Python.
#[pyclass(name = "BatchRecords")]
pub struct PyBatchRecords {
    #[pyo3(get)]
    batch_records: Vec<Py<PyBatchRecord>>,
}

// ── Deferred conversion types for async client ─────────────────────
//
// These types hold Rust data from completed I/O and implement `IntoPyObject`
// so that `pyo3-async-runtimes::future_into_py` can convert them to Python
// objects inside the **single** GIL acquisition it already performs
// (via `spawn_blocking`). This avoids calling `Python::attach()` on a
// Tokio worker thread, which would block the worker on GIL contention
// and prevent new I/O from being initiated under concurrent load.

/// Deferred batch records → Python conversion for `batch_operate`,
/// `batch_write`, `batch_write_numpy`, and `batch_remove`.
pub struct PendingBatchRecords {
    pub results: Vec<BatchRecord>,
}

impl<'py> IntoPyObject<'py> for PendingBatchRecords {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let batch = batch_to_batch_records_py(py, self.results)?;
        Ok(Py::new(py, batch)?.into_bound(py).into_any())
    }
}

/// Deferred batch read → Python conversion.
///
/// **Why not convert to `PyDict` directly here?**
///
/// `IntoPyObject` runs inside `future_into_py`'s `spawn_blocking` callback,
/// which holds the GIL. Under `asyncio.gather` with N concurrent `batch_read`
/// calls, N `spawn_blocking` threads compete for the GIL sequentially.
///
/// - If we convert to `PyDict` here: each thread holds GIL for 1-5ms
///   → total serialized time = N × 1-5ms (blocks Tokio from initiating new I/O).
/// - With `Handle` (Arc wrap only): each thread holds GIL for < 0.01ms
///   → threads release almost instantly, Tokio workers are freed for new I/O.
///   The heavier dict conversion runs later via `handle.as_dict()` in the
///   Python coroutine on the event loop, where there is no contention.
pub enum PendingBatchRead {
    /// Zero-conversion handle: GIL hold < 0.01ms (Arc wrap only).
    /// Actual conversion happens on handle method calls in the event loop.
    Handle(Vec<BatchRecord>),
    /// Numpy: returns structured NumPy array (eager, already fast).
    Numpy {
        results: Vec<BatchRecord>,
        dtype: Py<PyAny>,
    },
}

impl<'py> IntoPyObject<'py> for PendingBatchRead {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self {
            PendingBatchRead::Handle(results) => {
                // GIL hold < 0.01ms: Arc::new (move, no copy) + Py::new
                let handle = PyBatchReadHandle {
                    inner: Arc::new(results),
                };
                Ok(Py::new(py, handle)?.into_bound(py).into_any())
            }
            PendingBatchRead::Numpy { results, dtype } => {
                crate::numpy_support::batch_to_numpy_py(py, &results, &dtype.into_bound(py))
                    .map(|obj| obj.into_bound(py))
            }
        }
    }
}

// ── PyBatchReadHandle ────────────────────────────────────────────
//
// Zero-conversion handle returned by async `batch_read`. Wraps raw Rust
// batch results in an `Arc`; actual Python conversion is deferred to
// method calls that run in the event loop thread (zero GIL contention).

/// Handle wrapping raw Rust batch read results.
///
/// Returned by `AsyncClient.batch_read()`. The async future completes
/// with near-zero GIL cost (just an `Arc` wrap). Call methods on this
/// handle to access the data:
///
/// - [`as_dict()`](Self::as_dict) — fastest path, returns `dict[key, bins_dict]`
/// - [`batch_records`](Self::batch_records) — compatibility path, returns `list[BatchRecord]`
#[pyclass(name = "BatchReadHandle")]
pub struct PyBatchReadHandle {
    inner: Arc<Vec<BatchRecord>>,
}

#[pymethods]
impl PyBatchReadHandle {
    fn __len__(&self) -> usize {
        self.inner.len()
    }

    fn __getitem__(&self, py: Python<'_>, index: isize) -> PyResult<Py<PyBatchRecord>> {
        let len = self.inner.len() as isize;
        let idx = if index < 0 { len + index } else { index };
        if idx < 0 || idx >= len {
            return Err(pyo3::exceptions::PyIndexError::new_err(
                "BatchReadHandle index out of range",
            ));
        }
        single_batch_record_to_py(py, &self.inner[idx as usize])
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyBatchReadIter {
        PyBatchReadIter {
            inner: Arc::clone(&slf.inner),
            index: 0,
        }
    }

    /// Fastest access path: returns `dict[key_str, bins_dict]` directly.
    ///
    /// Skips all intermediate objects (BatchRecord wrapper, key tuple, meta dict).
    /// Records without a `user_key` (digest-only) or with a failed result are
    /// excluded from the dict. Use `batch_records` to access all records.
    fn as_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        batch_to_dict_py(py, &self.inner)
    }

    /// Compatibility path: returns `list[BatchRecord]` with lazy per-record conversion.
    ///
    /// Each `BatchRecord`'s `.record` field is lazily converted on first access.
    #[getter]
    fn batch_records(&self, py: Python<'_>) -> PyResult<Vec<Py<PyBatchRecord>>> {
        let br = batch_to_batch_records_py(py, (*self.inner).clone())?;
        Ok(br.batch_records)
    }

    /// Count of records with successful result code (no conversion needed).
    fn found_count(&self) -> usize {
        self.inner
            .iter()
            .filter(|br| matches!(&br.result_code, None | Some(ResultCode::Ok)))
            .count()
    }

    /// Extract just the user keys without converting record data.
    fn keys<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        use crate::types::value::value_to_py;
        let keys: Vec<Bound<'py, PyAny>> = self
            .inner
            .iter()
            .filter_map(|br| {
                br.key.user_key.as_ref().map(|uk| match uk {
                    aerospike_core::Value::String(s) => {
                        s.into_pyobject(py).map(|o| o.into_any()).ok()
                    }
                    aerospike_core::Value::Int(i) => {
                        i.into_pyobject(py).map(|o| o.into_any()).ok()
                    }
                    v => value_to_py(py, v).ok().map(|o| o.into_bound(py)),
                })
            })
            .flatten()
            .collect();
        PyList::new(py, &keys)
    }
}

/// Iterator for [`PyBatchReadHandle`], yielding [`PyBatchRecord`] one at a time.
#[pyclass]
pub struct PyBatchReadIter {
    inner: Arc<Vec<BatchRecord>>,
    index: usize,
}

#[pymethods]
impl PyBatchReadIter {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> PyResult<Option<Py<PyBatchRecord>>> {
        if self.index >= self.inner.len() {
            return Ok(None);
        }
        let br = &self.inner[self.index];
        self.index += 1;
        single_batch_record_to_py(py, br).map(Some)
    }
}

/// Convert a single `BatchRecord` reference to a `PyBatchRecord`.
/// Used by `__getitem__` and `__next__`.
fn single_batch_record_to_py(py: Python<'_>, br: &BatchRecord) -> PyResult<Py<PyBatchRecord>> {
    let key_py = key_to_py(py, &br.key)?;
    let result_code = match &br.result_code {
        Some(rc) => result_code_to_int(rc),
        None => 0,
    };
    let record_cell = match &br.record {
        Some(record) => LazyRecordCell::Pending {
            record: record.clone(),
            key_py: key_py.clone_ref(py),
        },
        None => LazyRecordCell::None,
    };
    Py::new(
        py,
        PyBatchRecord {
            key: key_py,
            result: result_code,
            record_cell: Mutex::new(record_cell),
            in_doubt: br.in_doubt,
        },
    )
}

/// Convert batch results directly to `dict[key_str, bins_dict]`.
///
/// Skips all intermediate objects (BatchRecord wrapper, key tuple, meta dict,
/// record tuple). Only creates bins dicts + the outer dict.
///
/// Allocation count for N records with B bins each:
/// - Standard path: N × (5 key + 1 meta + 1 bins + B values + 1 tuple + 1 wrapper) = N×(9+B)
/// - AsDict path:   N × (1 bins + B values) + 1 outer dict = N×(1+B) + 1
///   → Savings: N × 8 allocations (e.g., 1800 × 8 = 14,400 alloc saved)
pub fn batch_to_dict_py<'py>(
    py: Python<'py>,
    results: &[BatchRecord],
) -> PyResult<Bound<'py, PyDict>> {
    use crate::types::value::value_to_py;

    let dict = PyDict::new(py);
    for br in results {
        // Extract user_key as Python string directly from Rust Key
        let key_str = match &br.key.user_key {
            Some(aerospike_core::Value::String(s)) => s.into_pyobject(py)?.into_any(),
            Some(aerospike_core::Value::Int(i)) => i.into_pyobject(py)?.into_any(),
            Some(v) => value_to_py(py, v)?.into_bound(py),
            None => continue, // skip records without user_key
        };

        // Only process successful reads
        if let Some(record) = &br.record {
            let bins = PyDict::new(py);
            for (name, value) in &record.bins {
                bins.set_item(name, value_to_py(py, value)?)?;
            }
            dict.set_item(&key_str, &bins)?;
        }
    }
    Ok(dict)
}

/// Convert `BatchRecord`s into a Python [`PyBatchRecords`] with **lazy bin conversion**.
///
/// Only key and result_code are converted eagerly (lightweight).
/// The record's `(key, meta, bins)` tuple is deferred until `br.record` is accessed.
pub fn batch_to_batch_records_py(
    py: Python<'_>,
    results: Vec<BatchRecord>,
) -> PyResult<PyBatchRecords> {
    trace!(
        "Converting {} batch records to Python (lazy bins)",
        results.len()
    );
    let mut batch_records = Vec::with_capacity(results.len());

    for br in results {
        // Only convert key immediately (lightweight, always needed for routing)
        let key_py = key_to_py(py, &br.key)?;

        let result_code = match &br.result_code {
            Some(rc) => result_code_to_int(rc),
            None => 0,
        };

        // LAZY: store raw Rust Record; convert only on first `br.record` access
        let record_cell = match br.record {
            Some(record) => LazyRecordCell::Pending {
                record,
                key_py: key_py.clone_ref(py),
            },
            None => LazyRecordCell::None,
        };

        let batch_record = PyBatchRecord {
            key: key_py,
            result: result_code,
            record_cell: Mutex::new(record_cell),
            in_doubt: br.in_doubt,
        };

        batch_records.push(Py::new(py, batch_record)?);
    }

    Ok(PyBatchRecords { batch_records })
}
