//! PyO3 wrapper around `aerospike_core::PartitionFilter`.
//!
//! Exposed to Python via three module-level free functions
//! (`partition_filter_all`, `partition_filter_by_id`, `partition_filter_by_range`).
//! The wrapper is opaque from Python — users hold the handle and pass it as
//! `policy={"partition_filter": handle}`. Internally we clone the inner
//! `PartitionFilter` before handing it to `aerospike_core::Client::query()`
//! because the underlying struct holds `Arc<Mutex<Vec<PartitionStatus>>>`
//! whose state mutates during query execution; cloning isolates the user's
//! handle from any in-flight state changes.

use aerospike_core::query::PartitionFilter as CorePartitionFilter;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Total number of partitions in an Aerospike cluster.
const PARTITIONS: usize = 4096;

/// Opaque PyO3 wrapper around `aerospike_core::PartitionFilter`.
///
/// Construct via `partition_filter_all()`, `partition_filter_by_id(id)`, or
/// `partition_filter_by_range(begin, count)`. Pass the resulting handle to
/// `Query.results(policy={"partition_filter": handle})`.
#[pyclass(
    name = "PartitionFilter",
    module = "aerospike_py",
    frozen,
    from_py_object
)]
#[derive(Clone, Debug)]
pub struct PyPartitionFilter {
    pub(crate) inner: CorePartitionFilter,
}

impl PyPartitionFilter {
    /// Return a clone of the inner `aerospike_core::PartitionFilter`.
    ///
    /// Cloning is cheap (the struct holds `Arc<Mutex<...>>` and `AtomicBool`)
    /// and isolates the user's Python handle from in-flight query state mutations.
    pub fn clone_inner(&self) -> CorePartitionFilter {
        self.inner.clone()
    }
}

#[pymethods]
impl PyPartitionFilter {
    fn __repr__(&self) -> String {
        format!(
            "PartitionFilter(begin={}, count={})",
            self.inner.begin, self.inner.count
        )
    }
}

/// Build a filter that scans/queries every partition (0..4096).
#[pyfunction]
pub fn partition_filter_all() -> PyPartitionFilter {
    PyPartitionFilter {
        inner: CorePartitionFilter::all(),
    }
}

/// Build a filter targeting a single partition (0..=4095).
#[pyfunction]
pub fn partition_filter_by_id(partition_id: usize) -> PyResult<PyPartitionFilter> {
    if partition_id >= PARTITIONS {
        return Err(PyValueError::new_err(format!(
            "partition_id must be in [0, {PARTITIONS}), got {partition_id}"
        )));
    }
    Ok(PyPartitionFilter {
        inner: CorePartitionFilter::by_id(partition_id),
    })
}

/// Build a filter targeting `count` partitions starting at `begin`.
///
/// `begin` must be in `[0, 4096)` and `begin + count` must be `<= 4096`.
/// `count == 0` is permitted (yields an empty filter).
#[pyfunction]
pub fn partition_filter_by_range(begin: usize, count: usize) -> PyResult<PyPartitionFilter> {
    if begin >= PARTITIONS && count > 0 {
        return Err(PyValueError::new_err(format!(
            "begin must be in [0, {PARTITIONS}), got {begin}"
        )));
    }
    if begin
        .checked_add(count)
        .map(|s| s > PARTITIONS)
        .unwrap_or(true)
    {
        return Err(PyValueError::new_err(format!(
            "begin + count must be <= {PARTITIONS}, got begin={begin}, count={count}"
        )));
    }
    Ok(PyPartitionFilter {
        inner: CorePartitionFilter::by_range(begin, count),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::Python;

    #[test]
    fn test_all_covers_4096_partitions() {
        let pf = partition_filter_all();
        assert_eq!(pf.inner.begin, 0);
        assert_eq!(pf.inner.count, PARTITIONS);
    }

    #[test]
    fn test_by_id_in_range() {
        let pf = partition_filter_by_id(42).unwrap();
        assert_eq!(pf.inner.begin, 42);
        assert_eq!(pf.inner.count, 1);
    }

    #[test]
    fn test_by_id_out_of_range_raises() {
        Python::initialize();
        Python::attach(|_py| {
            let err = partition_filter_by_id(PARTITIONS).unwrap_err();
            assert!(err.to_string().contains("partition_id must be"));
        });
    }

    #[test]
    fn test_by_range_validates_overflow() {
        Python::initialize();
        Python::attach(|_py| {
            assert!(partition_filter_by_range(4000, 1000).is_err());
            assert!(partition_filter_by_range(0, 4096).is_ok());
            assert!(partition_filter_by_range(0, 0).is_ok());
        });
    }

    #[test]
    fn test_clone_preserves_begin_count() {
        let pf = partition_filter_by_range(100, 200).unwrap();
        let cloned = pf.clone();
        assert_eq!(cloned.inner.begin, 100);
        assert_eq!(cloned.inner.count, 200);
    }
}
