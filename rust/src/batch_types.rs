//! Python-visible batch record types for all batch operations
//! (`batch_read`, `batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`).

use aerospike_core::BatchRecord;
use log::trace;
use pyo3::prelude::*;

use crate::errors::result_code_to_int;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py_with_key;

/// A single record within batch results, exposed to Python.
#[pyclass(name = "BatchRecord")]
pub struct PyBatchRecord {
    #[pyo3(get)]
    key: Py<PyAny>,
    #[pyo3(get)]
    result: i32,
    #[pyo3(get)]
    record: Py<PyAny>,
    #[pyo3(get)]
    in_doubt: bool,
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
        let batch = batch_to_batch_records_py(py, &self.results)?;
        Ok(Py::new(py, batch)?.into_bound(py).into_any())
    }
}

/// Deferred batch read → Python conversion supporting both standard
/// and numpy output paths.
pub enum PendingBatchRead {
    Standard(Vec<BatchRecord>),
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
            PendingBatchRead::Standard(results) => {
                let batch = batch_to_batch_records_py(py, &results)?;
                Ok(Py::new(py, batch)?.into_bound(py).into_any())
            }
            PendingBatchRead::Numpy { results, dtype } => {
                crate::numpy_support::batch_to_numpy_py(py, &results, &dtype.into_bound(py))
                    .map(|obj| obj.into_bound(py))
            }
        }
    }
}

/// Convert a slice of `BatchRecord`s into a Python [`PyBatchRecords`] object.
pub fn batch_to_batch_records_py(
    py: Python<'_>,
    results: &[BatchRecord],
) -> PyResult<PyBatchRecords> {
    trace!("Converting {} batch records to Python", results.len());
    let mut batch_records = Vec::with_capacity(results.len());

    for br in results {
        let key_py = key_to_py(py, &br.key)?;

        let result_code = match &br.result_code {
            Some(rc) => result_code_to_int(rc),
            None => 0,
        };

        // Pass the already-converted key_py to avoid double key conversion
        let record_py = match &br.record {
            Some(record) => record_to_py_with_key(py, record, key_py.clone_ref(py))?,
            None => py.None(),
        };

        let batch_record = PyBatchRecord {
            key: key_py,
            result: result_code,
            record: record_py,
            in_doubt: br.in_doubt,
        };

        batch_records.push(Py::new(py, batch_record)?);
    }

    Ok(PyBatchRecords { batch_records })
}
