use aerospike_core::BatchRecord;
use pyo3::prelude::*;

use crate::errors::result_code_to_int;
use crate::types::key::key_to_py;
use crate::types::record::record_to_py;

#[pyclass(name = "BatchRecord")]
pub struct PyBatchRecord {
    #[pyo3(get)]
    key: Py<PyAny>,
    #[pyo3(get)]
    result: i32,
    #[pyo3(get)]
    record: Py<PyAny>,
}

#[pyclass(name = "BatchRecords")]
pub struct PyBatchRecords {
    #[pyo3(get)]
    batch_records: Vec<Py<PyBatchRecord>>,
}

pub fn batch_to_batch_records_py(
    py: Python<'_>,
    results: &[BatchRecord],
) -> PyResult<PyBatchRecords> {
    let mut batch_records = Vec::with_capacity(results.len());

    for br in results {
        let key_py = key_to_py(py, &br.key)?;

        let result_code = match &br.result_code {
            Some(rc) => result_code_to_int(rc),
            None => 0,
        };

        let record_py = match &br.record {
            Some(_) => record_to_py(py, br.record.as_ref().unwrap())?,
            None => py.None(),
        };

        let batch_record = PyBatchRecord {
            key: key_py,
            result: result_code,
            record: record_py,
        };

        batch_records.push(Py::new(py, batch_record)?);
    }

    Ok(PyBatchRecords { batch_records })
}
