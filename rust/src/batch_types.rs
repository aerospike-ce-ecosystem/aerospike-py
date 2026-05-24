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
/// Under standard CPython with the GIL, concurrent access from Python
/// is impossible and the Mutex is effectively uncontended. Under
/// free-threaded CPython (3.13t, 3.14t) the Mutex provides real mutual
/// exclusion during first-access conversion and caching.
enum LazyRecordCell {
    /// Raw Rust Record awaiting lazy conversion.
    Pending { record: Record, key_py: Py<PyAny> },
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
    /// Lazy-converted record cell. `Mutex` satisfies `Send + Sync` for pyclass
    /// and provides real mutual exclusion under free-threaded CPython
    /// (3.13t, 3.14t); under GIL builds it is effectively uncontended.
    record_cell: Mutex<LazyRecordCell>,
    #[pyo3(get)]
    in_doubt: bool,
}

#[pymethods]
impl PyBatchRecord {
    /// Lazily convert the record to Python `(key, meta, bins)` tuple.
    /// Returns `None` if the record was not found.
    ///
    /// A poisoned `record_cell` mutex means a previous lazy conversion
    /// panicked mid-flight (e.g. a legacy language-specific blob particle
    /// type that `aerospike-core` cannot decode — see issue #280). Rather
    /// than silently recovering and re-running the same conversion that
    /// already crashed, surface a clear [`RustPanicError`] so callers know
    /// this batch record's data is unrecoverable.
    #[getter]
    fn record(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let mut guard = self.record_cell.lock().map_err(|_| {
            crate::errors::RustPanicError::new_err(
                "BatchRecord.record conversion previously panicked; this batch \
                 record's data is unrecoverable (likely a legacy blob particle \
                 type aerospike-core cannot decode — see issue #280)",
            )
        })?;
        guard.to_python(py)
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
///   The heavier dict conversion runs later via `lazy_records.to_dict()` in the
///   Python coroutine on the event loop, where there is no contention.
pub enum PendingBatchRead {
    /// Zero-conversion handle: GIL hold < 0.01ms (Arc wrap only).
    /// Actual conversion happens on handle method calls in the event loop.
    Handle {
        results: Vec<BatchRecord>,
        /// Timestamp when Rust async I/O completed — populated only when internal
        /// stage profiling is enabled. `None` avoids an `Instant::now()` syscall
        /// per batch_read on the hot path.
        io_complete_at: Option<std::time::Instant>,
    },
}

impl<'py> IntoPyObject<'py> for PendingBatchRead {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self {
            PendingBatchRead::Handle {
                results,
                io_complete_at,
            } => {
                // ── (C) spawn_blocking queue delay: io_complete → into_pyobject ──
                if let Some(t) = io_complete_at {
                    crate::metrics::record_internal_stage_unchecked(
                        "spawn_blocking_delay",
                        "batch_read",
                        t.elapsed().as_secs_f64(),
                    );
                }

                // Capture into_pyobject_at only when profiling is ON.
                let into_pyobject_at = crate::metrics::maybe_now();
                crate::stage_timer!("into_pyobject", "batch_read", {
                    let handle = PyLazyBatchRecords::from_arc_with_timestamp(
                        Arc::new(results),
                        into_pyobject_at,
                    );
                    let result = Py::new(py, handle)?.into_bound(py).into_any();
                    Ok(result)
                })
            }
        }
    }
}

// ── PyLazyBatchRecords ────────────────────────────────────────────
//
// Zero-conversion handle returned by async `batch_read`. Wraps raw Rust
// batch results in an `Arc`; actual Python conversion is deferred to
// method calls that run in the event loop thread (zero GIL contention).

/// Handle wrapping raw Rust batch read results.
///
/// Returned by both sync `Client.batch_read()` and async
/// `AsyncClient.batch_read()`. The async future completes with
/// near-zero GIL cost (just an `Arc` wrap). Call methods on this
/// handle to access the data:
///
/// - [`to_dict()`](Self::to_dict) — fastest path, returns `dict[key, bins_dict]`
/// - [`to_numpy(dtype)`](Self::to_numpy) — NumPy structured array, GIL released during fill
/// - [`batch_records`](Self::batch_records) — compatibility path, returns `list[BatchRecord]`
///
/// **Cost shape of the Mapping protocol.** The dict-style dunders
/// (`__getitem__`, `__contains__`, `__iter__`, `items()`, `keys()`,
/// `values()`, `get()`) and `__len__`-less iteration are all backed by
/// a single cached `to_dict()`. The first such call pays the full
/// Rust→Python dict materialisation; subsequent calls hit the cache.
/// `__len__` itself is a pure-Rust filter+count and does not trigger
/// the dict build. If you only need cardinality, prefer `len(handle)`
/// or `found_count()` over `len(handle.to_dict())`.
#[pyclass(name = "LazyBatchRecords", mapping)]
pub struct PyLazyBatchRecords {
    inner: Arc<Vec<BatchRecord>>,
    /// Timestamp when `into_pyobject` completed — populated only when internal
    /// stage profiling is enabled (for `event_loop_resume_delay` measurement).
    into_pyobject_at: Option<std::time::Instant>,
    /// Lazily-materialised `dict[user_key, bins_dict]` view shared by all the
    /// dict-like dunder methods (`__contains__`, `__getitem__`, `__iter__`,
    /// `__len__`, `items`, `values`, `keys`). The first call that needs a
    /// dict pays the conversion cost; subsequent calls reuse the same
    /// `PyDict`. `to_dict()` always returns a *new* dict so that callers can
    /// mutate freely without poisoning the cache.
    ///
    /// `Mutex` is required because `#[pyclass]` types must be `Send + Sync`.
    /// Under the GIL it's effectively uncontended; under free-threaded
    /// CPython it provides real mutual exclusion during first materialisation.
    cached_dict: Mutex<Option<Py<PyDict>>>,
}

impl PyLazyBatchRecords {
    /// Build a handle directly from owned Rust batch results.
    ///
    /// Used by the sync `Client.batch_read` path, which has the GIL when
    /// constructing the handle (no `IntoPyObject` plumbing required).
    pub fn from_results(results: Vec<BatchRecord>) -> Self {
        Self {
            inner: Arc::new(results),
            into_pyobject_at: None,
            cached_dict: Mutex::new(None),
        }
    }

    /// Build a handle from already-shared `Arc` results plus a profiling
    /// timestamp. Used by the async `IntoPyObject` path.
    fn from_arc_with_timestamp(
        inner: Arc<Vec<BatchRecord>>,
        into_pyobject_at: Option<std::time::Instant>,
    ) -> Self {
        Self {
            inner,
            into_pyobject_at,
            cached_dict: Mutex::new(None),
        }
    }

    /// Return the cached `dict[user_key, bins_dict]`, building it on first
    /// access. Owned `Py<PyDict>` is cloned out so the caller can bind to
    /// the current GIL token without holding the mutex lock.
    fn cached_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let mut guard = self.cached_dict.lock().map_err(|_| {
            crate::errors::RustPanicError::new_err(
                "LazyBatchRecords dict cache mutex was poisoned by a previous \
                 panic during conversion; this handle's data is unrecoverable",
            )
        })?;
        if guard.is_none() {
            let d = batch_to_dict_py(py, &self.inner)?;
            *guard = Some(d.unbind());
        }
        Ok(guard.as_ref().unwrap().clone_ref(py).into_bound(py))
    }
}

#[pymethods]
impl PyLazyBatchRecords {
    /// Dict-view cardinality: number of records that ``to_dict()`` would
    /// include — i.e. successful reads (`result_code == Ok`) that carry
    /// both a `user_key` and a `record` body.
    ///
    /// Matches ``len(lazy_records.to_dict())`` and is the size users
    /// expect from a Mapping-protocol ``__len__``. For the raw record
    /// count (including missing reads and per-record failures) use
    /// ``len(lazy_records.batch_records)``.
    ///
    /// Fast path: pure Rust filter+count, no `PyDict` allocation.
    fn __len__(&self) -> usize {
        self.inner
            .iter()
            .filter(|br| {
                br.key.user_key.is_some()
                    && matches!(&br.result_code, None | Some(ResultCode::Ok))
                    && br.record.is_some()
            })
            .count()
    }

    /// Dict-style item access: `lazy_records[user_key]` returns the bins dict.
    ///
    /// Records without a `user_key` (digest-only) or with a failed result
    /// are not present in the dict view — use `batch_records[i]` for raw
    /// index-based access (including digest-only and failed records).
    fn __getitem__<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        match d.get_item(key)? {
            Some(v) => Ok(v),
            None => Err(pyo3::exceptions::PyKeyError::new_err(format!(
                "{} not present in LazyBatchRecords dict view \
                 (key is digest-only, missing from the batch response, or its read failed — \
                 inspect lazy_records.batch_records[i].result for the per-record code, \
                 or iterate all_user_keys() for every requested user_key)",
                key.repr()?
            ))),
        }
    }

    fn __contains__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<bool> {
        let d = self.cached_dict(py)?;
        d.contains(key)
    }

    /// Dict-style ``lazy_records.get(key, default=None)`` — returns the
    /// bins dict for ``key``, or ``default`` if ``key`` is not in the
    /// dict view (digest-only / failed records are excluded). Mirrors
    /// ``dict.get`` semantics so code written against the pre-
    /// ``LazyBatchRecords`` ``dict`` return type keeps working unchanged.
    #[pyo3(signature = (key, default=None))]
    fn get<'py>(
        &self,
        py: Python<'py>,
        key: &Bound<'py, PyAny>,
        default: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        match d.get_item(key)? {
            Some(v) => Ok(v),
            None => Ok(match default {
                Some(d) => d.clone(),
                None => py.None().into_bound(py),
            }),
        }
    }

    fn __iter__<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let d = slf.cached_dict(py)?;
        d.call_method0("__iter__")
    }

    /// Dict-style ``lazy_records.items()`` view.
    fn items<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        d.call_method0("items")
    }

    /// Dict-style ``lazy_records.values()`` view.
    fn values<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        d.call_method0("values")
    }

    /// Iterate records (BatchRecord wrappers) in insertion order.
    ///
    /// Preserves the pre-dict-like iteration semantics for callers that
    /// need every record — including digest-only entries and failed reads
    /// that the dict view skips.
    fn iter_records(slf: PyRef<'_, Self>) -> PyBatchReadIter {
        PyBatchReadIter {
            inner: Arc::clone(&slf.inner),
            index: 0,
        }
    }

    /// Fastest dict access: returns `dict[user_key, bins_dict]`.
    ///
    /// Skips all intermediate objects (BatchRecord wrapper, key tuple, meta
    /// dict). Records without a `user_key` (digest-only) or with a failed
    /// result are excluded from the dict — use `batch_records` to access
    /// all records.
    ///
    /// This is the canonical conversion entry point. `as_dict()` remains
    /// available as a deprecated alias that forwards here unchanged.
    ///
    /// **Returned dict is a fresh shallow copy of the cached materialisation.**
    /// Mutating it will not affect future `to_dict()` calls nor the dict
    /// view used by `__getitem__`/`__contains__`/`__iter__`/`items`/`keys`/
    /// `values`. This preserves the original "callers can mutate freely"
    /// guarantee while sharing the underlying record→Python conversion
    /// cost between `to_dict()` and the Mapping-protocol dunders (was
    /// double-materialised before).
    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        // ── (D) event loop resume delay: into_pyobject → to_dict call ──
        if let Some(t) = self.into_pyobject_at {
            crate::metrics::record_internal_stage_unchecked(
                "event_loop_resume_delay",
                "batch_read",
                t.elapsed().as_secs_f64(),
            );
        }

        // ── Stage: to_dict (GIL held in event loop coroutine) ──
        crate::stage_timer!("to_dict", "batch_read", {
            let cached = self.cached_dict(py)?;
            cached.copy()
        })
    }

    /// Convert the batch read result into a `NumpyBatchRecords` structured
    /// array. The fill loop runs under `Python::detach`, so the GIL is
    /// released while raw Aerospike values are written into the NumPy
    /// buffer — see `numpy_support::batch_to_numpy_py` for details.
    ///
    /// **Missing / failed reads silently zero-fill.** Rows whose
    /// `result_code != 0` (including `RecordNotFound`) leave both the
    /// data and meta arrays at the dtype's zero value — callers MUST
    /// inspect `result.result_codes` (or `found_count()` on this
    /// handle) before treating any row as a successful read. Aerospike
    /// `Nil` bin values are also written as zero, so a genuinely-zero
    /// bin and a missing bin are indistinguishable in the buffer alone.
    fn to_numpy(&self, py: Python<'_>, dtype: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        crate::stage_timer!("to_numpy", "batch_read", {
            crate::numpy_support::batch_to_numpy_py(py, &self.inner, dtype)
        })
    }

    /// Merge multiple handles into a list of dicts in a single GIL acquisition.
    ///
    /// Avoids 9 separate event-loop coroutine resumes when using `asyncio.gather`.
    /// Instead of `[h.to_dict() for h in handles]`, call
    /// `LazyBatchRecords.merge_to_dict(handles)` once.
    #[staticmethod]
    fn merge_to_dict<'py>(
        handles: Vec<PyRef<'py, Self>>,
        py: Python<'py>,
    ) -> PyResult<Vec<Bound<'py, PyDict>>> {
        crate::stage_timer!("merge_to_dict", "batch_read", {
            let result: PyResult<Vec<_>> = handles
                .iter()
                .map(|h| batch_to_dict_py(py, &h.inner))
                .collect();
            result
        })
    }

    /// Compatibility path: returns `list[BatchRecord]` with lazy per-record conversion.
    ///
    /// Each `BatchRecord`'s `.record` field is lazily converted on first access.
    #[getter]
    fn batch_records(&self, py: Python<'_>) -> PyResult<Vec<Py<PyBatchRecord>>> {
        self.inner
            .iter()
            .map(|br| single_batch_record_to_py(py, br))
            .collect()
    }

    /// Drop the cached ``PyDict`` materialisation created by the first
    /// Mapping-protocol access (``__getitem__``/``__contains__``/
    /// ``items``/``keys``/``values``/``get``/``__iter__``) or by a
    /// previous ``to_dict()`` call. The raw Rust ``Arc<Vec<BatchRecord>>``
    /// is retained so that ``batch_records``, ``iter_records()``,
    /// ``all_user_keys()``, ``found_count()``, ``__len__``, and
    /// ``to_numpy(dtype)`` keep working without reissuing the read.
    ///
    /// Use this after a large-batch dict materialisation that you no
    /// longer need (for example, after copying the result into a
    /// downstream cache or feature store) to release the PyDict memory
    /// without dropping the entire handle. A subsequent Mapping access
    /// or ``to_dict()`` rebuilds the cache lazily on demand.
    fn release_cache(&self) -> PyResult<()> {
        let mut guard = self.cached_dict.lock().map_err(|_| {
            crate::errors::RustPanicError::new_err(
                "LazyBatchRecords dict cache mutex was poisoned by a previous \
                 panic during conversion; release_cache cannot reset it safely",
            )
        })?;
        *guard = None;
        Ok(())
    }

    /// Count of records with successful result code (no conversion needed).
    fn found_count(&self) -> usize {
        self.inner
            .iter()
            .filter(|br| matches!(&br.result_code, None | Some(ResultCode::Ok)))
            .count()
    }

    /// Dict-style ``lazy_records.keys()`` view — user keys of records
    /// that actually appear in the dict view (successful reads with a
    /// ``user_key``). Missing / failed records are excluded so that
    /// ``set(lazy_records.keys())`` matches
    /// ``set(lazy_records.to_dict().keys())``.
    fn keys<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        d.call_method0("keys")
    }

    /// Return *every* batch record's ``user_key``, including missing and
    /// failed reads (i.e. records that ``to_dict()`` filters out).
    ///
    /// Useful when you need positional alignment with the raw
    /// ``batch_records`` list or with a ``NumpyBatchRecords`` result.
    fn all_user_keys<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let keys = collect_user_keys(py, &self.inner)?;
        PyList::new(py, &keys)
    }
}

/// Iterator for [`PyLazyBatchRecords`], yielding [`PyBatchRecord`] one at a time.
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

        // Skip per-record errors even if a body was returned (e.g. FilteredOut, RecordTooBig)
        if !matches!(&br.result_code, None | Some(ResultCode::Ok)) {
            continue;
        }
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

/// Convert each `BatchRecord`'s `user_key` to a Python object.
///
/// Records without a `user_key` (digest-only) are skipped. Conversion errors
/// are `?`-propagated rather than silently dropped, so the returned `Vec`
/// length always matches the number of records that carry a `user_key`.
pub fn collect_user_keys<'py>(
    py: Python<'py>,
    results: &[BatchRecord],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    use crate::types::value::value_to_py;
    results
        .iter()
        .filter_map(|br| br.key.user_key.as_ref())
        .map(|uk| -> PyResult<Bound<'py, PyAny>> {
            match uk {
                aerospike_core::Value::String(s) => Ok(s.into_pyobject(py)?.into_any()),
                aerospike_core::Value::Int(i) => Ok(i.into_pyobject(py)?.into_any()),
                v => Ok(value_to_py(py, v)?.into_bound(py)),
            }
        })
        .collect()
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

#[cfg(test)]
mod tests {
    use super::*;
    use aerospike_core::Value;

    /// Build a minimal `BatchRecord` with the given `user_key`.
    ///
    /// `BatchRecord::new` is `pub(crate)` in `aerospike_core`, so we construct
    /// a layout-compatible mirror and transmute — the same pattern used by the
    /// `client_ops` unit tests. Size + alignment are guarded at compile time.
    fn make_batch_record(user_key: Value) -> BatchRecord {
        #[repr(C)]
        struct BatchRecordMirror {
            key: aerospike_core::Key,
            record: Option<Record>,
            result_code: Option<ResultCode>,
            in_doubt: bool,
            has_write: bool,
        }

        static_assertions::assert_eq_size!(BatchRecordMirror, BatchRecord);
        static_assertions::assert_eq_align!(BatchRecordMirror, BatchRecord);

        let mirror = BatchRecordMirror {
            key: aerospike_core::Key::new("test", "demo", user_key).unwrap(),
            record: None,
            result_code: Some(ResultCode::Ok),
            in_doubt: false,
            has_write: false,
        };
        // SAFETY: `BatchRecordMirror` mirrors `BatchRecord`'s field types and
        // order exactly; size + alignment are asserted above. Test-only.
        unsafe { std::mem::transmute(mirror) }
    }

    /// A poisoned `record_cell` mutex (left behind by a panic during a
    /// previous lazy conversion) must surface as a `RustPanicError` rather
    /// than being silently recovered. Without the fix the getter calls
    /// `unwrap_or_else(|e| e.into_inner())` and returns `Ok(...)`.
    #[test]
    fn record_getter_rejects_poisoned_cell() {
        Python::initialize();
        Python::attach(|py| {
            let br = Py::new(
                py,
                PyBatchRecord {
                    key: py.None(),
                    result: 0,
                    record_cell: Mutex::new(LazyRecordCell::None),
                    in_doubt: false,
                },
            )
            .expect("construct PyBatchRecord");

            // Poison the mutex by panicking while holding the lock.
            let poisoned = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let cell = br.borrow(py);
                let _g = cell.record_cell.lock().unwrap();
                panic!("synthetic conversion panic");
            }))
            .is_err();
            assert!(poisoned, "panic must unwind to poison the mutex");

            let cell = br.borrow(py);
            let err = cell
                .record(py)
                .expect_err("poisoned cell must surface an error");
            assert!(
                err.is_instance_of::<crate::errors::RustPanicError>(py),
                "poisoned record_cell must raise RustPanicError"
            );
        });
    }

    /// A poisoned `cached_dict` mutex on a `PyLazyBatchRecords` (left behind
    /// by a panic during a previous materialisation) must surface as a
    /// `RustPanicError` from every dict-view dunder, not be silently
    /// recovered. Mirrors the `PyBatchRecord.record_cell` poison contract.
    #[test]
    fn lazy_batch_records_rejects_poisoned_dict_cache() {
        Python::initialize();
        Python::attach(|py| {
            let handle =
                Py::new(py, PyLazyBatchRecords::from_results(Vec::new())).expect("construct");

            // Poison the cached_dict mutex by panicking while holding the lock.
            let poisoned = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let cell = handle.borrow(py);
                let _g = cell.cached_dict.lock().unwrap();
                panic!("synthetic cache materialisation panic");
            }))
            .is_err();
            assert!(poisoned, "panic must unwind to poison the mutex");

            let cell = handle.borrow(py);
            let err = cell
                .cached_dict(py)
                .expect_err("poisoned cache must surface an error");
            assert!(
                err.is_instance_of::<crate::errors::RustPanicError>(py),
                "poisoned cached_dict must raise RustPanicError"
            );
        });
    }

    /// `collect_user_keys` returns every key for a normal batch, preserving
    /// order and length (round-trip) — no keys are silently dropped.
    #[test]
    fn collect_user_keys_returns_all_keys() {
        Python::initialize();
        Python::attach(|py| {
            let records = vec![
                make_batch_record(Value::from("k0".to_string())),
                make_batch_record(Value::from("k1".to_string())),
                make_batch_record(Value::Int(42)),
            ];
            let keys = collect_user_keys(py, &records).expect("conversion should succeed");
            assert_eq!(keys.len(), records.len(), "no key may be dropped");

            assert_eq!(keys[0].extract::<String>().unwrap(), "k0");
            assert_eq!(keys[1].extract::<String>().unwrap(), "k1");
            assert_eq!(keys[2].extract::<i64>().unwrap(), 42);
        });
    }
}
