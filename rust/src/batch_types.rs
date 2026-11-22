//! Python-visible batch record types for all batch operations
//! (`batch_read`, `batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`).
//!
//! Uses **lazy conversion** for the `record` field: bins are NOT converted to
//! Python until the user accesses `br.record`. This reduces GIL hold time by
//! 70-80% for large batches where not all records' bins are accessed.

use std::borrow::Cow;
use std::sync::{Arc, Mutex};

use aerospike_core::{BatchRecord, Error as AsError, Record, ResultCode};
use log::{debug, trace};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::errors::{ErrorClass, CLIENT_SIDE_RESULT_CODE};
use crate::types::key::key_to_py;
use crate::types::record::record_to_py_with_key;

// ── Row outcome ──────────────────────────────────────────────────

/// `error_type` of a row that no node answered.
pub(crate) const NO_RESPONSE_LABEL: &str = "NoResponse";

/// What happened to one row of a batch call.
///
/// Rust client 3.0 no longer stores a result code on the row. A row holds the
/// failure itself (an `Error`), and has three states: failed when the error is
/// set, successful when it is not and a record is present, and unanswered when
/// neither is. Every consumer of a batch result — `BatchRecord.result`, the
/// dict / list / NumPy views, `found_count`, the write retry loop — reads the
/// state through this type, so they cannot disagree about which rows worked.
///
/// A row is successful only when the server said so. An unanswered row is
/// **not** reported as OK: with Rust client 2.x a row without a result code
/// was treated as a success, which made a row nobody answered look written.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum RowOutcome {
    /// The server answered and the operation succeeded.
    Ok,
    /// The row failed, either with a server result code or on the client side
    /// (timeout, connection loss, ...).
    Failed(ErrorClass),
    /// Core stamped PARTITION_UNAVAILABLE locally because the row had no route.
    NotRouted,
    /// No node answered for this row and no failure was recorded for it.
    NoResponse,
}

impl RowOutcome {
    #[inline]
    pub(crate) fn of(br: &BatchRecord) -> Self {
        Self::from_parts(br.error(), br.record.is_some())
    }

    /// The outcome of a row with this error and record presence. Split out of
    /// [`of`](Self::of) because a failed `BatchRecord` cannot be built outside
    /// aerospike-core, while an `Error` can.
    #[inline]
    pub(crate) fn from_parts(error: Option<&AsError>, has_record: bool) -> Self {
        match (error, has_record) {
            // A failed UDF row keeps a record (its FAILURE bin) next to the
            // error; the error decides.
            (Some(e), _) => Self::from_failure(ErrorClass::of(e), e.node()),
            (None, true) => Self::Ok,
            (None, false) => Self::NoResponse,
        }
    }

    pub(crate) fn from_failure(class: ErrorClass, node: Option<&str>) -> Self {
        if class == ErrorClass::Server(ResultCode::PartitionUnavailable) && node.is_none() {
            Self::NotRouted
        } else {
            Self::Failed(class)
        }
    }

    pub(crate) fn has_server_answer(self) -> bool {
        matches!(self, Self::Ok | Self::Failed(ErrorClass::Server(_)))
    }

    /// `BatchRecord.result`: `0` on success, the server's wire code when a
    /// server answered with a failure, and the client-side sentinel `-1`
    /// otherwise. `error_type` tells the `-1` cases apart.
    pub(crate) fn result_code(self) -> i32 {
        match self {
            Self::Ok => 0,
            Self::Failed(class) => class.result_code(),
            Self::NotRouted => ErrorClass::Server(ResultCode::PartitionUnavailable).result_code(),
            Self::NoResponse => CLIENT_SIDE_RESULT_CODE,
        }
    }

    /// `BatchRecord.error_type`: `None` on success, otherwise the same label
    /// the exception, the metrics and the trace use for this failure.
    pub(crate) fn error_type(self) -> Option<Cow<'static, str>> {
        match self {
            Self::Ok => None,
            Self::Failed(class) => Some(class.label()),
            Self::NotRouted => Some(ErrorClass::Server(ResultCode::PartitionUnavailable).label()),
            Self::NoResponse => Some(Cow::Borrowed(NO_RESPONSE_LABEL)),
        }
    }
}

/// Whether a failed row's write may have been applied anyway.
///
/// aerospike-core decides this for a failure on the client side: a request
/// that was sent and never answered is in doubt. It does not for a row the
/// *server* answered with `TIMEOUT`, and that is the same situation seen from
/// the other end: the server gave up waiting, typically for a replica that is
/// gone, after the master had already taken the write. A single-record write
/// that ends this way is reported in doubt; a batch row has to be as well, or
/// "failed, certainly not applied" would be said of a record that was written.
///
/// In the other direction it marks every failed UDF row of a one-key batch in
/// doubt, although the server answered with a definite failure; see
/// [`may_have_been_applied`](crate::errors::may_have_been_applied).
pub(crate) fn row_in_doubt(br: &BatchRecord, outcome: RowOutcome) -> bool {
    if !br.has_write() {
        return false;
    }
    br.error().is_some_and(crate::errors::may_have_been_applied) || server_gave_up_waiting(outcome)
}

/// The row was answered with the server's own `TIMEOUT` result code.
pub(crate) fn server_gave_up_waiting(outcome: RowOutcome) -> bool {
    outcome == RowOutcome::Failed(ErrorClass::Server(ResultCode::Timeout))
}

/// Whether the server answered this row with success.
///
/// The same judgement as `RowOutcome::of(br) == RowOutcome::Ok`, without
/// classifying the error of a failed row. Used on the per-row hot paths.
#[inline]
pub(crate) fn row_ok(br: &BatchRecord) -> bool {
    br.error().is_none() && br.record.is_some()
}

// ── Lazy record cell ─────────────────────────────────────────────

/// Holds either raw Rust Record data (pre-conversion) or the cached
/// Python tuple `(key, meta, bins)` after first access.
///
/// Uses `Mutex` to satisfy `Send + Sync` required by `#[pyclass]`.
/// Under standard CPython with the GIL, concurrent access from Python
/// is impossible and the Mutex is effectively uncontended. Under
/// free-threaded CPython (3.13t, 3.14t) the Mutex provides real mutual
/// exclusion during first-access conversion and caching.
///
/// `Pending` holds the `Record` inline. It is the state every row starts in,
/// and the cell already lives inside the row's own Python object, so boxing
/// the record would add one heap allocation per batch row and save nothing.
#[allow(clippy::large_enum_variant)]
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
    /// `None` for a successful row, otherwise the failure's class label.
    error_type: Option<Cow<'static, str>>,
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

    /// What kind of failure this row had: `None` when it succeeded, otherwise
    /// the same name an exception carries in `error_type` (`"KeyNotFoundError"`,
    /// `"Timeout"`, `"Connection"`, ...), or `"NoResponse"` when no node
    /// answered for the row.
    #[getter]
    fn error_type(&self) -> Option<&str> {
        self.error_type.as_deref()
    }
}

/// Container holding a list of [`PyBatchRecord`]s, exposed to Python.
#[pyclass(name = "BatchRecords")]
pub struct PyBatchRecords {
    #[pyo3(get)]
    batch_records: Vec<Py<PyBatchRecord>>,
    /// `(attempts, max_attempts, truncated_by_timeout, unresolved)` for calls
    /// that ran the client-side retry loop, else `None`.
    ///
    /// `None` on every path that issues a single batch call — `retry=0`
    /// `batch_write`, and `batch_operate` / `batch_remove` / `batch_apply`,
    /// which have no `retry` parameter. Keeping it `None` rather than a
    /// populated default means the common path builds no tuple at all, and the
    /// Python wrapper only pays one attribute read.
    #[pyo3(get)]
    retry_info: Option<(u32, u32, bool, u32)>,
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
    /// `Some` only for `batch_write` / `batch_write_numpy`.
    pub retry_stats: Option<crate::client_ops::BatchWriteRetryStats>,
    /// Ascending indices of failed rows to report as `in_doubt` although the
    /// row itself does not say so.
    ///
    /// Only the `retry=` loop fills this. A row holds the result of the last
    /// attempt that sent its record; when an earlier attempt may have been
    /// applied and the last one failed without being in doubt itself, the
    /// record is still in doubt, and the row cannot express that.
    pub in_doubt_rows: Vec<usize>,
}

impl PendingBatchRecords {
    /// Convert into the Python `BatchRecords` container (lazy bins).
    pub fn into_batch_records(self, py: Python<'_>) -> PyResult<PyBatchRecords> {
        build_batch_records(py, self.results, self.retry_stats, &self.in_doubt_rows)
    }

    /// Whether any row will be reported in doubt: by the call that made the
    /// rows, or by its own error.
    fn any_row_in_doubt(&self) -> bool {
        !self.in_doubt_rows.is_empty()
            || self
                .results
                .iter()
                .any(|row| row_in_doubt(row, RowOutcome::of(row)))
    }
}

/// Attach the rows of a batch call that failed as a whole to its exception,
/// as `partial_result` (a `BatchRecords`).
///
/// The exception is the one the failure has always raised. What is new is
/// that the rows are not thrown away: `exc.partial_result.batch_records` has
/// one entry per requested record, in request order, and each says whether it
/// succeeded, failed with a server code, or got no answer.
///
/// Runs on the error path only. If the conversion itself fails the original
/// exception is raised unchanged and the reason is logged.
///
/// The rows are built under the GIL. With the async client this runs inside
/// the batch future, on a runtime worker, and a worker that waits for the GIL
/// behind a busy event loop serves nobody else meanwhile. A whole-call
/// failure is what a node going down produces, for many calls at once, so the
/// wait would land on the requests to the healthy nodes at the worst moment.
/// [`off_the_runtime`] lets the runtime carry on while this thread waits.
///
/// `call_in_doubt` is set when the call gave up on rows it may already have
/// sent (a node's task could not be joined). The error of such a call is a
/// plain client error that knows nothing of a send, so the exception is
/// marked here, like the rows.
///
/// The exception is also in doubt when any of its rows is. A call that failed
/// on several nodes comes back with the error of one of them, the first whose
/// share failed, and that one may be a refusal (`KEY_BUSY`, not in doubt)
/// while another node's share was sent and never answered. Which error it is
/// depends on the order of the records; whether a write of the call may have
/// been applied must not.
pub(crate) fn attach_partial_result(
    err: PyErr,
    rows: PendingBatchRecords,
    call_in_doubt: bool,
) -> PyErr {
    let call_in_doubt = call_in_doubt || rows.any_row_in_doubt();
    off_the_runtime(|| {
        Python::attach(|py| {
            let attached = rows
                .into_batch_records(py)
                .and_then(|batch| Py::new(py, batch))
                .and_then(|batch| err.value(py).setattr("partial_result", batch))
                .and_then(|()| {
                    if call_in_doubt {
                        err.value(py).setattr("in_doubt", true)
                    } else {
                        Ok(())
                    }
                });
            if let Err(attach_err) = attached {
                debug!("failed to attach the partial batch result to the exception: {attach_err}");
            }
        });
    });
    err
}

/// Run blocking work from inside a future without holding up the runtime.
///
/// On a worker of the multi-thread runtime the worker's other tasks are
/// handed to another thread first (`block_in_place`). Anywhere else (the sync
/// client's `block_on` thread, a test without a runtime) the work just runs.
fn off_the_runtime<R>(work: impl FnOnce() -> R) -> R {
    use tokio::runtime::{Handle, RuntimeFlavor};
    match Handle::try_current() {
        Ok(handle) if handle.runtime_flavor() == RuntimeFlavor::MultiThread => {
            tokio::task::block_in_place(work)
        }
        _ => work(),
    }
}

impl<'py> IntoPyObject<'py> for PendingBatchRecords {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let batch = self.into_batch_records(py)?;
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
/// `__len__` itself is a pure-Rust pass that counts distinct Mapping keys
/// and does not trigger the dict build. If you only need cardinality,
/// prefer `len(handle)` over `len(handle.to_dict())`; use `found_count()`
/// for the number of successful rows.
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
    /// `PyDict`. `to_dict()` returns a shallow copy: the outer dict is new,
    /// the bins dicts inside it are shared with this cache.
    ///
    /// `Mutex` is required because `#[pyclass]` types must be `Send + Sync`.
    /// Under the GIL it's effectively uncontended; under free-threaded
    /// CPython it provides real mutual exclusion during first materialisation.
    cached_dict: Mutex<Option<Py<PyDict>>>,
    /// What [`distinct_dict_keys`] returned for `inner`, computed on the
    /// first `len()`. The rows never change, so neither does the count, and
    /// a caller that asks for the length in a loop hashes the keys once.
    distinct_keys: std::sync::OnceLock<Option<usize>>,
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
            distinct_keys: std::sync::OnceLock::new(),
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
            distinct_keys: std::sync::OnceLock::new(),
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
    /// Dict-view cardinality: the number of **distinct** user keys that
    /// ``to_dict()`` would include — successful reads (`result_code == Ok`)
    /// that carry both a `user_key` and a `record` body.
    ///
    /// Always equals ``len(lazy_records.to_dict())``, including when the
    /// same user key was requested more than once (or in several sets):
    /// those rows share one Mapping entry and are counted once. For the
    /// number of successful rows use ``found_count()``; for the raw row
    /// count (including missing reads and per-record failures) use
    /// ``len(lazy_records.batch_records)`` or ``len(lazy_records.to_list())``.
    ///
    /// Fast path: a pure Rust pass over the keys, no `PyDict` allocation.
    fn __len__(&self, py: Python<'_>) -> PyResult<usize> {
        // An already-built dict view knows its own size.
        if let Ok(guard) = self.cached_dict.lock() {
            if let Some(dict) = guard.as_ref() {
                return Ok(dict.bind(py).len());
            }
        }
        match *self
            .distinct_keys
            .get_or_init(|| distinct_dict_keys(&self.inner))
        {
            Some(count) => Ok(count),
            // A user key of a type the Rust pass does not model: let the
            // Python dict decide what counts as the same key.
            None => Ok(self.cached_dict(py)?.len()),
        }
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
    /// This is the canonical conversion entry point; the Mapping-
    /// protocol dunders (`__getitem__`, `__contains__`, `items`,
    /// `keys`, `values`, `get`, `__iter__`) share the same cached
    /// materialisation behind the scenes.
    ///
    /// **Returned dict is a shallow copy of the cached materialisation.**
    /// The outer dict is new on every call, so adding or removing keys on
    /// it affects neither future `to_dict()` calls nor the dict view used
    /// by `__getitem__`/`__contains__`/`__iter__`/`items`/`keys`/`values`.
    /// The bins dicts it holds are **shared** with that view: mutating one
    /// in place is visible through the handle and through later
    /// `to_dict()` calls. Copy a bins dict before editing it, or use
    /// `to_list()`, which materialises fresh dicts every time. Sharing is
    /// what lets `to_dict()` and the Mapping-protocol dunders pay the
    /// record→Python conversion once.
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

    /// Positional bulk conversion: returns `list[bins_dict | None]` aligned
    /// 1:1 with the request key order (`len(result) == number of records`).
    ///
    /// Failed reads (non-OK result code, e.g. `FilteredOut`) and records
    /// without a body (not-found) yield `None` at their position. Slots are
    /// identified purely by position — **key-agnostic** — so it stays
    /// correct when the same `user_key` appears in multiple sets within one
    /// batch (the dict views collide on such keys; positional access does
    /// not), and **digest-only requests that succeed return their bins**
    /// (the dict views must skip them for lack of a `user_key`).
    ///
    /// Check misses with `is None` — a found record whose selected bins are
    /// empty (e.g. `bins=[]` header-only reads) is `{}`, not `None`. `None`
    /// folds together not-found and per-record errors; callers that must
    /// distinguish them should inspect `handle.batch_records[i].result`.
    /// Conversion happens in a single Rust pass like `to_dict` — skipping
    /// `BatchRecord` wrappers, key tuples and meta dicts.
    ///
    /// This is the recommended conversion for feature-store style callers
    /// that need request-order alignment: it replaces the
    /// `for br in handle.batch_records: br.record` pattern, which pays a
    /// lazy per-record conversion several times slower than one bulk pass.
    ///
    /// **Returned list is freshly materialised on every call** (no cache):
    /// callers can mutate the returned bins dicts freely without affecting
    /// the dict views or later `to_list()` calls.
    fn to_list<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        // ── (D) event loop resume delay: into_pyobject → to_list call ──
        if let Some(t) = self.into_pyobject_at {
            crate::metrics::record_internal_stage_unchecked(
                "event_loop_resume_delay",
                "batch_read",
                t.elapsed().as_secs_f64(),
            );
        }

        // ── Stage: to_list (GIL held in event loop coroutine) ──
        crate::stage_timer!("to_list", "batch_read", {
            batch_to_list_py(py, &self.inner)
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
    ///
    /// **Poison recovery.** Unlike the dict-view accessors (which
    /// surface a ``RustPanicError`` if a previous conversion panicked
    /// mid-flight and poisoned the mutex), ``release_cache`` is a
    /// cleanup intent: the whole point is to discard whatever the
    /// cache currently holds. A poisoned cache *is* unrecoverable for
    /// reads, but it can — and should — still be cleared, so the next
    /// read rebuilds it from the raw Rust records. We therefore
    /// recover the poisoned lock, write ``None``, and explicitly
    /// clear the poison flag so that subsequent ``cached_dict`` calls
    /// no longer raise ``RustPanicError``. This keeps
    /// ``release_cache`` safe to call from ``finally:`` cleanup
    /// blocks without masking the original exception, and the handle
    /// is fully usable for fresh reads afterwards.
    ///
    /// **Recovery limit.** If the original panic was caused by an
    /// undecodable record in ``inner`` (e.g. issue #280's legacy blob
    /// particle), a fresh ``to_dict()`` will rebuild over the same
    /// raw data and panic on the same record — re-poisoning the
    /// mutex. ``release_cache`` cannot undo that; it only clears the
    /// previous state so the next attempt has a clean baseline.
    /// Inspect ``iter_records()`` / ``batch_records`` to isolate the
    /// offending record before re-reading.
    fn release_cache(&self) {
        // Branch on the lock result itself rather than snapshotting
        // `is_poisoned()` separately: under free-threaded CPython a
        // sibling thread could poison the mutex between the snapshot
        // and the lock, leaving us to recover silently with no
        // `debug!` trace. The `LockResult` is authoritative for the
        // path actually taken.
        let mut guard = match self.cached_dict.lock() {
            Ok(g) => g,
            Err(poisoned) => {
                // Log the recovery path so callers running release_cache from
                // a retry loop can correlate repeated "panic → release →
                // panic" against the underlying record. Plain `release_cache`
                // calls (cache present but no poison) stay quiet.
                debug!(
                    "LazyBatchRecords::release_cache: recovered poisoned cache mutex \
                     (records={}); next read will rebuild from raw records",
                    self.inner.len()
                );
                poisoned.into_inner()
            }
        };
        *guard = None;
        drop(guard);
        // `clear_poison` (stable in Rust 1.74+) resets the mutex's
        // poison flag so a future `cached_dict()` lock succeeds —
        // without it, the handle would stay in a "len()/found_count()
        // works but `.to_dict()` raises" inconsistent state. Safe to
        // call unconditionally: it's a no-op when the mutex isn't
        // poisoned.
        self.cached_dict.clear_poison();
    }

    /// Count of records with successful result code (no conversion needed).
    fn found_count(&self) -> usize {
        self.inner.iter().filter(|br| row_ok(br)).count()
    }

    /// Dict-style ``lazy_records.keys()`` view — user keys of records
    /// that actually appear in the dict view (successful reads with a
    /// ``user_key``). Missing / failed records are excluded so that
    /// ``set(lazy_records.keys())`` matches
    /// ``set(lazy_records.to_dict().keys())``.
    ///
    /// **`keys()` vs `all_user_keys()`.** `keys()` is the
    /// Mapping-protocol view (dict-view cardinality, never contains
    /// `None`); `all_user_keys()` is the positional view (length
    /// always equals `len(batch_records)`, contains `None` for
    /// digest-only slots). Use `keys()` when you need the dict-view
    /// invariant `len(keys()) == len(to_dict())`; use
    /// `all_user_keys()` when you need positional alignment with
    /// `batch_records` / a `NumpyBatchRecords` row.
    fn keys<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let d = self.cached_dict(py)?;
        d.call_method0("keys")
    }

    /// Return *every* batch record's ``user_key`` in request order.
    ///
    /// The returned list has the same length as ``batch_records`` and is
    /// positionally aligned with a ``NumpyBatchRecords`` data array.
    /// Per-slot contents:
    ///
    /// - **User-keyed requests** (`(ns, set, user_key)` or
    ///   `(ns, set, user_key, digest)`): the slot carries the
    ///   `user_key` the caller supplied, *verbatim* — not echoed by
    ///   the server. This holds regardless of whether the read
    ///   succeeded, returned `RecordNotFound`, or failed for any
    ///   other reason.
    /// - **Digest-only requests** (`(ns, set, None, digest)`): the
    ///   slot is `None`. The server never carries a user_key for
    ///   these requests, so there is nothing to populate.
    ///
    /// **`all_user_keys()` vs `keys()`.** Use `all_user_keys()` for
    /// the positional invariant (length matches `batch_records`,
    /// may contain `None`); use the Mapping-protocol `keys()` for the
    /// dict-view cardinality (matches `to_dict().keys()`, never
    /// contains `None`).
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
    let outcome = RowOutcome::of(br);
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
            result: outcome.result_code(),
            record_cell: Mutex::new(record_cell),
            in_doubt: row_in_doubt(br, outcome),
            error_type: outcome.error_type(),
        },
    )
}

/// Whether a batch row appears in the dict views: a successful read that
/// carries both a user key and a record body.
///
/// Shared by [`batch_to_dict_py`] and [`distinct_dict_keys`] so the Mapping
/// length can never disagree with the Mapping contents.
fn row_in_dict_view(br: &BatchRecord) -> bool {
    br.key.user_key().is_some() && row_ok(br)
}

/// Count the distinct user keys among the rows the dict views include.
///
/// Returns `None` when a row carries a user key that is not an integer, a
/// string or a blob; the caller then falls back to the Python dict, which is
/// the authority on key equality.
fn distinct_dict_keys(results: &[BatchRecord]) -> Option<usize> {
    #[derive(Hash, PartialEq, Eq)]
    enum DictKey<'a> {
        Int(i64),
        Str(&'a str),
        Bytes(&'a [u8]),
    }

    let mut seen = std::collections::HashSet::with_capacity(results.len());
    for br in results {
        if !row_in_dict_view(br) {
            continue;
        }
        let key = match br.key.user_key().as_ref()? {
            aerospike_core::Value::Int(i) => DictKey::Int(*i),
            aerospike_core::Value::String(s) => DictKey::Str(s.as_str()),
            aerospike_core::Value::Blob(b) => DictKey::Bytes(b.as_slice()),
            _ => return None,
        };
        seen.insert(key);
    }
    Some(seen.len())
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
    use std::time::{Duration, Instant};

    let stage_enabled = crate::metrics::is_internal_stage_enabled();
    let mut t_key = Duration::ZERO;
    let mut t_inner_alloc = Duration::ZERO;
    let mut t_value_to_py = Duration::ZERO;
    let mut t_bin_setitem = Duration::ZERO;
    let mut t_outer_setitem = Duration::ZERO;

    let dict = PyDict::new(py);
    for br in results {
        // Extract user_key as Python string directly from Rust Key
        let t0 = if stage_enabled {
            Some(Instant::now())
        } else {
            None
        };
        let key_str = match &br.key.user_key() {
            Some(aerospike_core::Value::String(s)) => s.into_pyobject(py)?.into_any(),
            Some(aerospike_core::Value::Int(i)) => i.into_pyobject(py)?.into_any(),
            Some(v) => value_to_py(py, v)?.into_bound(py),
            None => continue, // skip records without user_key
        };
        if let Some(t0) = t0 {
            t_key += t0.elapsed();
        }

        // Skip per-record errors even if a body was returned (e.g. FilteredOut, RecordTooBig)
        if br.error().is_some() {
            continue;
        }
        if let Some(record) = &br.record {
            let t1 = if stage_enabled {
                Some(Instant::now())
            } else {
                None
            };
            let bins = PyDict::new(py);
            if let Some(t1) = t1 {
                t_inner_alloc += t1.elapsed();
            }

            for (name, value) in &record.bins {
                let t2 = if stage_enabled {
                    Some(Instant::now())
                } else {
                    None
                };
                let v = value_to_py(py, value)?;
                if let Some(t2) = t2 {
                    t_value_to_py += t2.elapsed();
                }

                let t3 = if stage_enabled {
                    Some(Instant::now())
                } else {
                    None
                };
                bins.set_item(name, v)?;
                if let Some(t3) = t3 {
                    t_bin_setitem += t3.elapsed();
                }
            }

            let t4 = if stage_enabled {
                Some(Instant::now())
            } else {
                None
            };
            dict.set_item(&key_str, &bins)?;
            if let Some(t4) = t4 {
                t_outer_setitem += t4.elapsed();
            }
        }
    }

    if stage_enabled {
        crate::metrics::record_internal_stage_unchecked(
            "as_dict_key",
            "batch_read",
            t_key.as_secs_f64(),
        );
        crate::metrics::record_internal_stage_unchecked(
            "as_dict_inner_alloc",
            "batch_read",
            t_inner_alloc.as_secs_f64(),
        );
        crate::metrics::record_internal_stage_unchecked(
            "as_dict_value_to_py",
            "batch_read",
            t_value_to_py.as_secs_f64(),
        );
        crate::metrics::record_internal_stage_unchecked(
            "as_dict_bin_setitem",
            "batch_read",
            t_bin_setitem.as_secs_f64(),
        );
        crate::metrics::record_internal_stage_unchecked(
            "as_dict_outer_setitem",
            "batch_read",
            t_outer_setitem.as_secs_f64(),
        );
    }

    Ok(dict)
}

/// Positional bulk conversion backing [`PyLazyBatchRecords::to_list`].
///
/// One pass over the raw Rust batch results producing
/// `list[bins_dict | None]` of the same length, preserving request order.
/// No `user_key` extraction or dict hashing — slots are identified purely
/// by position, so multi-set batches that repeat the same user key cannot
/// collide (the dict views lose one of the colliding records).
pub fn batch_to_list_py<'py>(
    py: Python<'py>,
    results: &[BatchRecord],
) -> PyResult<Bound<'py, PyList>> {
    use crate::types::value::value_to_py;

    let out = PyList::empty(py);
    for br in results {
        // Per-record errors (e.g. FilteredOut, RecordTooBig) → None slot.
        if br.error().is_some() {
            out.append(py.None())?;
            continue;
        }
        match &br.record {
            Some(record) => {
                let bins = PyDict::new(py);
                for (name, value) in &record.bins {
                    bins.set_item(name, value_to_py(py, value)?)?;
                }
                out.append(bins)?;
            }
            // Not-found / digest-only without body → None slot.
            None => out.append(py.None())?,
        }
    }
    Ok(out)
}

/// Convert each `BatchRecord`'s `user_key` to a Python object, preserving
/// the request-order index of every record.
///
/// Records without a `user_key` (digest-only requests) are represented
/// by `py.None()` instead of being filtered out, so the returned `Vec`
/// length always equals `results.len()` and positional alignment with
/// `batch_records` / a `NumpyBatchRecords` data array holds. Conversion
/// errors are `?`-propagated rather than silently dropped.
///
/// **Allocation profile (intentional trade-off).** The previous
/// implementation `filter_map`-skipped digest-only entries and so
/// allocated nothing for them; the positional contract requires one
/// `py.None()` clone per skipped entry. For a digest-only-heavy
/// workload (e.g. a secondary-index follow-up that resolves every
/// match by digest only) this is `N` additional refcount bumps per
/// `all_user_keys()` call — `py.None()` is the interpreter-global
/// singleton, so the cost is a `Py_INCREF` and a `Bound` wrap, not a
/// fresh object. We accept the cost because the positional alignment
/// it preserves is what every documented `zip(all_user_keys(),
/// batch_records)` / NumPy-row consumer relies on; a future
/// digest-only-bulk accessor that streams without materialising the
/// list would be the right escape hatch if this ever shows up in a
/// hot-path profile.
pub fn collect_user_keys<'py>(
    py: Python<'py>,
    results: &[BatchRecord],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    use crate::types::value::value_to_py;
    results
        .iter()
        .map(|br| -> PyResult<Bound<'py, PyAny>> {
            match &br.key.user_key() {
                Some(aerospike_core::Value::String(s)) => Ok(s.into_pyobject(py)?.into_any()),
                Some(aerospike_core::Value::Int(i)) => Ok(i.into_pyobject(py)?.into_any()),
                Some(v) => Ok(value_to_py(py, v)?.into_bound(py)),
                None => Ok(py.None().into_bound(py)),
            }
        })
        .collect()
}

/// Convert `BatchRecord`s into a Python [`PyBatchRecords`] with **lazy bin conversion**.
///
/// Only key and result_code are converted eagerly (lightweight).
/// The record's `(key, meta, bins)` tuple is deferred until `br.record` is accessed.
///
/// `retry_stats` is what the `batch_write` retry loop has to report, and
/// `in_doubt_rows` (ascending) the failed rows the call knows more about than
/// the row itself says: one an earlier attempt left in doubt, or one that may
/// be the answer to a second send of its record.
fn build_batch_records(
    py: Python<'_>,
    results: Vec<BatchRecord>,
    retry_stats: Option<crate::client_ops::BatchWriteRetryStats>,
    in_doubt_rows: &[usize],
) -> PyResult<PyBatchRecords> {
    trace!(
        "Converting {} batch records to Python (lazy bins)",
        results.len()
    );
    let mut batch_records = Vec::with_capacity(results.len());
    let mut forced_in_doubt = in_doubt_rows.iter().copied().peekable();

    for (index, br) in results.into_iter().enumerate() {
        // Only convert key immediately (lightweight, always needed for routing)
        let key_py = key_to_py(py, &br.key)?;

        let outcome = RowOutcome::of(&br);
        let forced = forced_in_doubt.next_if_eq(&index).is_some();
        let in_doubt = row_in_doubt(&br, outcome) || (forced && outcome != RowOutcome::Ok);

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
            result: outcome.result_code(),
            record_cell: Mutex::new(record_cell),
            in_doubt,
            error_type: outcome.error_type(),
        };

        batch_records.push(Py::new(py, batch_record)?);
    }

    Ok(PyBatchRecords {
        batch_records,
        retry_info: retry_stats.map(|s| {
            (
                s.attempts,
                s.max_attempts,
                s.truncated_by_timeout,
                s.unresolved,
            )
        }),
    })
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
        make_batch_record_inner(aerospike_core::Key::new("test", "demo", user_key).unwrap())
    }

    /// Build a `BatchRecord` whose `Key` carries no `user_key` (digest-only).
    /// The digest is a zero-filled placeholder — sufficient for unit tests
    /// that don't perform any server-side lookup.
    fn make_digest_only_batch_record() -> BatchRecord {
        let key = aerospike_core::Key::with_digest("test", "demo", None, [0u8; 20]);
        make_batch_record_inner(key)
    }

    /// A row the server answered with success and no bins.
    ///
    /// Built through aerospike-core's public API only: a new row is
    /// unanswered, and giving it a record is what an answer does.
    fn make_batch_record_inner(key: aerospike_core::Key) -> BatchRecord {
        let mut row = BatchRecord::new(key, false);
        row.record = Some(Record::new(
            None,
            aerospike_core::IndexMap::new(),
            None,
            0,
            0,
        ));
        row
    }

    // ── Row outcome ─────────────────────────────────────────────

    #[test]
    fn a_row_is_ok_only_when_a_server_said_so() {
        let answered = make_batch_record(Value::Int(1));
        assert_eq!(RowOutcome::of(&answered), RowOutcome::Ok);
        assert!(row_ok(&answered));

        // Rust client 2.x reported a row like this one as a success.
        let never_answered = BatchRecord::new(
            aerospike_core::Key::new("test", "demo", Value::Int(2)).unwrap(),
            true,
        );
        assert_eq!(RowOutcome::of(&never_answered), RowOutcome::NoResponse);
        assert!(!row_ok(&never_answered));
    }

    #[test]
    fn the_error_decides_even_when_a_record_came_with_it() {
        // A failed UDF row keeps its FAILURE bin next to the error.
        let failure = AsError::client_error("udf failed");
        assert_eq!(
            RowOutcome::from_parts(Some(&failure), true),
            RowOutcome::Failed(ErrorClass::Client)
        );
    }

    #[test]
    fn result_and_error_type_follow_the_outcome() {
        let ok = RowOutcome::Ok;
        assert_eq!((ok.result_code(), ok.error_type()), (0, None));

        let missing = RowOutcome::Failed(ErrorClass::Server(ResultCode::KeyNotFoundError));
        assert_eq!(missing.result_code(), 2);
        assert_eq!(missing.error_type().as_deref(), Some("KeyNotFoundError"));

        let filtered = RowOutcome::Failed(ErrorClass::Server(ResultCode::FilteredOut));
        assert_eq!(filtered.result_code(), 27);
        assert_eq!(filtered.error_type().as_deref(), Some("FilteredOut"));

        let lost = RowOutcome::Failed(ErrorClass::Connection);
        assert_eq!(lost.result_code(), CLIENT_SIDE_RESULT_CODE);
        assert_eq!(lost.error_type().as_deref(), Some("Connection"));

        let silent = RowOutcome::NoResponse;
        assert_eq!(silent.result_code(), CLIENT_SIDE_RESULT_CODE);
        assert_eq!(silent.error_type().as_deref(), Some(NO_RESPONSE_LABEL));
    }

    #[test]
    fn only_the_servers_own_timeout_counts_as_giving_up() {
        assert!(server_gave_up_waiting(RowOutcome::Failed(
            ErrorClass::Server(ResultCode::Timeout)
        )));
        for other in [
            RowOutcome::Ok,
            RowOutcome::NoResponse,
            RowOutcome::Failed(ErrorClass::ClientTimeout),
            RowOutcome::Failed(ErrorClass::Server(ResultCode::DeviceOverload)),
            RowOutcome::Failed(ErrorClass::Server(ResultCode::KeyExistsError)),
        ] {
            assert!(!server_gave_up_waiting(other), "{other:?}");
        }
    }

    #[test]
    fn a_row_without_a_failure_is_never_in_doubt() {
        let written = {
            let mut row = BatchRecord::new(
                aerospike_core::Key::new("test", "demo", Value::Int(1)).unwrap(),
                true,
            );
            row.record = Some(Record::new(
                None,
                aerospike_core::IndexMap::new(),
                None,
                0,
                0,
            ));
            row
        };
        assert!(!row_in_doubt(&written, RowOutcome::of(&written)));

        let unanswered = BatchRecord::new(
            aerospike_core::Key::new("test", "demo", Value::Int(2)).unwrap(),
            true,
        );
        assert!(!row_in_doubt(&unanswered, RowOutcome::of(&unanswered)));
    }

    #[test]
    fn a_read_row_the_server_timed_out_is_not_in_doubt() {
        // Only a write can have been applied.
        let read_row = BatchRecord::new(
            aerospike_core::Key::new("test", "demo", Value::Int(1)).unwrap(),
            false,
        );
        let timed_out = RowOutcome::Failed(ErrorClass::Server(ResultCode::Timeout));
        assert!(!row_in_doubt(&read_row, timed_out));

        let write_row = BatchRecord::new(
            aerospike_core::Key::new("test", "demo", Value::Int(1)).unwrap(),
            true,
        );
        assert!(row_in_doubt(&write_row, timed_out));
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
                    error_type: None,
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

    /// `release_cache()` must recover a poisoned `cached_dict` mutex
    /// (instead of raising `RustPanicError`) so that callers using it
    /// from cleanup blocks (e.g. `finally: handle.release_cache()`)
    /// never mask the original in-flight exception. After
    /// `release_cache()`, the cache must be observably `None` so that
    /// the next read rebuilds it lazily.
    #[test]
    fn release_cache_recovers_poisoned_dict_cache() {
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

            // `release_cache()` must not raise — it is cleanup intent.
            let cell = handle.borrow(py);
            cell.release_cache();

            // Cache state is observably reset to None even though the
            // mutex was poisoned, so the next access can rebuild from
            // the raw records.
            let recovered = cell.cached_dict.lock().unwrap_or_else(|p| p.into_inner());
            assert!(
                recovered.is_none(),
                "release_cache must clear the cache after recovering a poisoned mutex"
            );
            drop(recovered);

            // Round-trip: a subsequent dict-view access succeeds and
            // returns a fresh empty dict (the underlying results are
            // empty in this test, so the rebuilt dict is empty too).
            // This proves the handle is fully usable after release.
            let d = cell
                .cached_dict(py)
                .expect("cached_dict must succeed after release_cache recovery");
            assert_eq!(d.len(), 0);
        });
    }

    /// `release_cache()` must remain idempotent across *repeated*
    /// poison-and-release cycles. The docstring documents that a
    /// fresh `to_dict()` over the same `inner` may re-poison the
    /// mutex (e.g. an undecodable record stays undecodable across
    /// retries); a subsequent `release_cache()` must still recover
    /// the mutex so users can call it inside an outer retry loop
    /// without leaving the handle wedged.
    #[test]
    fn release_cache_recovers_across_repeated_poisoning() {
        Python::initialize();
        Python::attach(|py| {
            let handle =
                Py::new(py, PyLazyBatchRecords::from_results(Vec::new())).expect("construct");

            for cycle in 0..3 {
                // Re-poison the cached_dict mutex with a synthetic panic.
                let poisoned = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let cell = handle.borrow(py);
                    let _g = cell.cached_dict.lock().unwrap();
                    panic!("synthetic conversion panic (cycle {cycle})");
                }))
                .is_err();
                assert!(
                    poisoned,
                    "cycle {cycle}: panic must unwind to poison the mutex"
                );

                // release_cache must succeed (no raise) every cycle.
                let cell = handle.borrow(py);
                cell.release_cache();

                // Mutex is unpoisoned and cache is observably None.
                let recovered = cell
                    .cached_dict
                    .lock()
                    .expect("cycle {cycle}: clear_poison must let lock() succeed");
                assert!(
                    recovered.is_none(),
                    "cycle {cycle}: cache must be None after release_cache"
                );
                drop(recovered);

                // Round-trip: a fresh dict-view access succeeds and
                // returns an empty dict (inner is empty in this test).
                let d = cell
                    .cached_dict(py)
                    .expect("cycle {cycle}: cached_dict must rebuild after release_cache");
                assert_eq!(d.len(), 0);
            }
        });
    }

    /// `collect_user_keys` preserves positional alignment by yielding
    /// `None` for digest-only requests (`user_key=None`) rather than
    /// filtering them out — otherwise users zipping
    /// `all_user_keys()` with `batch_records` / a `NumpyBatchRecords`
    /// row would get a silent off-by-one for every digest-only entry.
    #[test]
    fn collect_user_keys_preserves_digest_only_slots_as_none() {
        Python::initialize();
        Python::attach(|py| {
            let records = vec![
                make_batch_record(Value::from("k0".to_string())),
                // Digest-only request: the `Key` carries no `user_key`,
                // only a digest. `Key::new` would reject `Value::Nil`,
                // so we construct the `Key` directly via the helper.
                make_digest_only_batch_record(),
                make_batch_record(Value::Int(42)),
            ];
            let keys = collect_user_keys(py, &records).expect("conversion should succeed");
            assert_eq!(
                keys.len(),
                records.len(),
                "digest-only slots must remain in place, not be filtered"
            );

            assert_eq!(keys[0].extract::<String>().unwrap(), "k0");
            assert!(
                keys[1].is_none(),
                "digest-only entry must be `None`, not skipped"
            );
            assert_eq!(keys[2].extract::<i64>().unwrap(), 42);
        });
    }
}
