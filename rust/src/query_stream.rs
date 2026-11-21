//! A running query: its records, what stops it, and what is reported about it.
//!
//! Three things read a query's records — `Query.results()`, `Query.foreach()`
//! and the awaitable [`PyRecordStream`] behind `AsyncQuery` — and all three
//! must get every record once and stop the query the same way. They share
//! [`RunningQuery`] for that and [`QueryTelemetry`] for the metric and the span.

use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::Instant;

use aerospike_core::query::PartitionFilter;
use aerospike_core::{
    Client as AsClient, Error as AsError, QueryHandle, QueryPolicy, Record, Statement,
};
use futures::future::{ready, Either, Ready};
use futures::FutureExt;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;
use tokio::sync::mpsc::error::TrySendError;
use tokio::sync::{mpsc, Semaphore};

use crate::errors::as_to_pyerr;
use crate::panic_safety::future_into_py_panic_safe;
use crate::types::record::record_to_py;

/// What a query hands over: a record, or the error that ended it.
type Item = Result<Record, AsError>;

/// Tells a running query to stop: from any thread, any number of times, and
/// whether or not anything is waiting for the signal yet.
pub(crate) struct StopSignal {
    stopped: AtomicBool,
    /// Never holds a permit, so waiting for one can only end by the semaphore
    /// being closed. Closing it is the signal: it wakes everything that waits
    /// in [`stopped`](Self::stopped) and makes every later wait return at once.
    gate: Semaphore,
}

impl StopSignal {
    fn new() -> Self {
        Self {
            stopped: AtomicBool::new(false),
            gate: Semaphore::new(0),
        }
    }

    pub(crate) fn stop(&self) {
        self.stopped.store(true, Ordering::Release);
        self.gate.close();
    }

    fn is_stopped(&self) -> bool {
        self.stopped.load(Ordering::Acquire)
    }

    /// Resolves once [`stop`](Self::stop) has been called.
    async fn stopped(&self) {
        // `Err` is the only possible outcome: see `gate`.
        let _closed = self.gate.acquire().await;
    }
}

/// A query that has been sent: its records, each exactly once, and the means
/// to stop it.
///
/// # Every record once
///
/// aerospike-core offers two ways to read a query. Its record stream
/// (`Client::query`) is *at least once*: the cursor a retried round resumes
/// from moves when the consumer takes a record out, so the records that were
/// already buffered when a node's connection failed are fetched a second time
/// and handed out twice. Its callback API (`Client::query_foreach`) moves the
/// cursor the moment the callback has taken a record, which makes it exactly
/// once. A socket timeout, a lost connection or a consumer that pauses long
/// enough for the server to give up are all it takes to retry a round, so
/// this type uses the callback API and keeps the queue between the node
/// readers and the consumer itself: a record is committed when it is in that
/// queue, and nothing in the queue is ever fetched again.
///
/// At most `record_queue_size` records wait here, see [`Room`]. A node reader
/// whose record does not fit waits, and does not read from its connection
/// while it waits, which is the backpressure towards the server.
///
/// # What a record costs
///
/// Every record of every query and scan passes through here, one queue
/// message each, so the two ends are kept short. A node reader puts its
/// record in without waiting, cloning or allocating as long as there is room
/// (see [`hand_over`]). The consumer takes the records out several at a time:
/// the queue's permits then go back to the readers in one piece, and a reader
/// that was waiting for room is woken once for all of them and not once per
/// record.
///
/// # Stopping
///
/// **Dropping it stops the query**, and so does the [`StopSignal`] handed out
/// by [`stopper`](Self::stopper). Without that the node readers would go on
/// until the scan was through, or stay blocked on the full queue while the
/// server kept the scan and its connections.
pub(crate) struct RunningQuery {
    records: mpsc::Receiver<Item>,
    /// Records taken out of the queue and not handed out yet, **last one
    /// first** (they are popped off the end). They are committed like the
    /// ones still in the queue and count against `record_queue_size` with
    /// them.
    taken: Vec<Item>,
    /// See [`Room::taken_at_once`].
    taken_at_once: usize,
    stop: Arc<StopSignal>,
}

/// How the records that may wait in the client are divided between the queue
/// and what the consumer has taken out of it.
///
/// `queue + taken_at_once - 1` is what the policy allows: of the records the
/// consumer takes out in one go, one is handed out at once and the others
/// wait in [`RunningQuery::taken`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Room {
    /// Slots of the queue the node readers fill.
    queue: usize,
    /// How many records the consumer takes out of the queue in one go.
    taken_at_once: usize,
}

impl Room {
    /// The most the consumer takes out in one go. More than this gains
    /// nothing: a reader is woken once per so many records already.
    const MOST_TAKEN_AT_ONCE: usize = 64;

    fn of(policy: &QueryPolicy) -> Self {
        let wanted = policy.record_queue_size.max(1);
        // A query that returns at most ten records has no use for more room.
        match usize::try_from(policy.max_records) {
            Ok(limit) if limit > 0 => Self::for_records(wanted.min(limit)),
            _ => Self::for_records(wanted),
        }
    }

    /// Room for `allowed` waiting records (at least one). A quarter of it, at
    /// most, is taken out at a time: a small queue stays a queue, and is not
    /// emptied into the consumer's hands in one go.
    fn for_records(allowed: usize) -> Self {
        let taken_at_once = (allowed / 4).clamp(1, Self::MOST_TAKEN_AT_ONCE);
        Self {
            queue: allowed - (taken_at_once - 1),
            taken_at_once,
        }
    }
}

impl RunningQuery {
    /// Send the query. Must run inside the Tokio runtime: the node readers and
    /// the task that watches over them are spawned from here.
    pub(crate) async fn start(
        client: &AsClient,
        policy: &QueryPolicy,
        partition_filter: PartitionFilter,
        statement: Statement,
    ) -> Result<Self, AsError> {
        let room = Room::of(policy);
        let (queue, records) = mpsc::channel(room.queue);
        let stop = Arc::new(StopSignal::new());
        let handle = {
            let queue = queue.clone();
            let stop = Arc::clone(&stop);
            client
                .query_foreach(policy, partition_filter, statement, move |item| {
                    hand_over(&queue, &stop, item)
                })
                .await?
        };
        tokio::spawn(watch_over(handle, queue, Arc::clone(&stop)));
        Ok(Self {
            records,
            taken: Vec::new(),
            taken_at_once: room.taken_at_once,
            stop,
        })
    }

    /// The next record, an error that ended the query, or `None` at its end
    /// or once it has been told to stop.
    ///
    /// Dropping this future while it waits loses nothing: what has left the
    /// queue is kept in `self`, not in the future.
    pub(crate) async fn next(&mut self) -> Option<Item> {
        if let Some(item) = self.taken.pop() {
            return Some(item);
        }
        let closed = tokio::select! {
            biased;
            taken = self.records.recv_many(&mut self.taken, self.taken_at_once) => taken == 0,
            () = self.stop.stopped() => true,
        };
        if closed {
            return None;
        }
        self.taken.reverse();
        self.taken.pop()
    }

    /// The next record if it has already arrived; `None` when taking one would
    /// mean waiting.
    fn next_if_ready(&mut self) -> Option<Option<Item>> {
        if let Some(item) = self.taken.pop() {
            return Some(Some(item));
        }
        // One poll, and not `try_recv`: that one parks the calling thread -
        // a runtime worker here - while a sender is in the middle of putting
        // a record in.
        let taken = self
            .records
            .recv_many(&mut self.taken, self.taken_at_once)
            .now_or_never()?;
        if taken == 0 {
            return Some(None);
        }
        self.taken.reverse();
        Some(self.taken.pop())
    }

    /// A handle that stops the query from outside, while a read is waiting.
    fn stopper(&self) -> Arc<StopSignal> {
        Arc::clone(&self.stop)
    }
}

impl Drop for RunningQuery {
    fn drop(&mut self) {
        self.stop.stop();
    }
}

/// What the query's callback returns: whether the query goes on, known at
/// once or after a wait for room in the queue.
type HandedOver = Either<Ready<bool>, Pin<Box<dyn Future<Output = bool> + Send>>>;

/// The query's callback: put one record, or the error that ends the query,
/// into the queue. Runs on a node's reader task, for one item at a time per
/// node. Resolves to whether the query goes on.
///
/// aerospike-core commits a record to the resume cursor when this resolves, so
/// "in the queue" and "will not be fetched again" are the same moment.
///
/// This runs for every record, and aerospike-core puts what it returns in a
/// box of its own. So the record goes into the queue right here, before any
/// future exists: nothing is cloned and the box holds a `bool`. Only when the
/// queue is full is a future built that waits, and that is the one case where
/// the reader has time to spare.
fn hand_over(queue: &mpsc::Sender<Item>, stop: &Arc<StopSignal>, item: Item) -> HandedOver {
    if stop.is_stopped() {
        return Either::Left(ready(false));
    }
    // The reader of this query stops at the first error it is given, so there
    // is nothing left to fetch once one is on its way.
    let goes_on = item.is_ok();
    match queue.try_send(item) {
        Ok(()) => Either::Left(ready(goes_on)),
        Err(TrySendError::Closed(_)) => Either::Left(ready(false)),
        // The consumer is slower than the server. Wait for room, and do not
        // read from the connection meanwhile.
        Err(TrySendError::Full(item)) => Either::Right(Box::pin(wait_for_room(
            queue.clone(),
            Arc::clone(stop),
            item,
            goes_on,
        ))),
    }
}

/// [`hand_over`] for a queue that was full: put the item in when there is
/// room, unless the query is told to stop first.
async fn wait_for_room(
    queue: mpsc::Sender<Item>,
    stop: Arc<StopSignal>,
    item: Item,
    goes_on: bool,
) -> bool {
    tokio::select! {
        biased;
        () = stop.stopped() => false,
        sent = queue.send(item) => sent.is_ok() && goes_on,
    }
}

/// Hold the engine's handle for as long as the query runs: to cancel the
/// query when it is told to stop, and to let go of the handle at the end.
///
/// The handle owns the callback, and the callback owns the sending half of
/// the queue. The consumer sees the end of the query when the last sender is
/// gone, so the handle must not outlive the query.
async fn watch_over(mut handle: QueryHandle, queue: mpsc::Sender<Item>, stop: Arc<StopSignal>) {
    let ended = tokio::select! {
        biased;
        () = stop.stopped() => None,
        ended = handle.wait() => Some(ended),
    };
    match ended {
        // Told to stop. The callback already refuses every further record;
        // this also keeps the engine from starting another round.
        None => handle.cancel(),
        Some(Ok(())) => {}
        // Every failure of the query itself has been through the callback
        // already, and the consumer stops at the first one. What can arrive
        // only here is the engine's task dying. Without this the consumer
        // would take the closing queue for a normal end and return a
        // truncated result as if it were complete.
        Some(Err(e)) => {
            tokio::select! {
                biased;
                () = stop.stopped() => {}
                _sent = queue.send(Err(e)) => {}
            }
        }
    }
}

/// The duration metric and the OpenTelemetry span of one query, from the moment
/// it is sent to the moment its stream ends or is stopped.
pub(crate) struct QueryTelemetry {
    started: Instant,
    op_name: &'static str,
    namespace: String,
    set_name: String,
    #[cfg(feature = "otel")]
    span: opentelemetry::global::BoxedSpan,
}

impl QueryTelemetry {
    /// Start timing. The span opens here, before the query is sent, so that its
    /// duration is the query's and not the time it took to convert the result.
    #[allow(unused_variables)]
    pub(crate) fn start(
        op_name: &'static str,
        namespace: &str,
        set_name: &str,
        conn_info: &crate::tracing::ConnectionInfo,
    ) -> Self {
        #[cfg(feature = "otel")]
        let span = {
            use opentelemetry::trace::{SpanKind, Tracer};
            use opentelemetry::KeyValue;
            let tracer = crate::tracing::otel_impl::get_tracer();
            let span_name = format!("{} {}.{}", op_name.to_uppercase(), namespace, set_name);
            tracer
                .span_builder(span_name)
                .with_kind(SpanKind::Client)
                .with_attributes(vec![
                    KeyValue::new("db.system.name", "aerospike"),
                    KeyValue::new("db.namespace", namespace.to_string()),
                    KeyValue::new("db.collection.name", set_name.to_string()),
                    KeyValue::new("db.operation.name", op_name.to_uppercase()),
                    KeyValue::new("server.address", conn_info.server_address.clone()),
                    KeyValue::new("server.port", conn_info.server_port),
                    KeyValue::new("db.aerospike.cluster_name", conn_info.cluster_name.clone()),
                ])
                .start(&tracer)
        };
        Self {
            started: Instant::now(),
            op_name,
            namespace: namespace.to_string(),
            set_name: set_name.to_string(),
            #[cfg(feature = "otel")]
            span,
        }
    }

    /// The query ended: with `failure`, or — `None` — by reaching its end or by
    /// being stopped by its caller, neither of which is an error.
    pub(crate) fn finish(self, failure: Option<&AsError>) {
        if crate::metrics::is_metrics_enabled() {
            let error_type = failure.map(crate::metrics::error_type_from_aerospike_error);
            crate::metrics::OperationTimer::started_at(
                self.started,
                self.op_name,
                &self.namespace,
                &self.set_name,
            )
            .finish(error_type.as_deref().unwrap_or(""));
        }

        #[cfg(feature = "otel")]
        {
            use opentelemetry::trace::TraceContextExt;
            let cx = opentelemetry::Context::current().with_span(self.span);
            let span_ref = TraceContextExt::span(&cx);
            if let Some(e) = failure {
                crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
            }
            span_ref.end();
        }
    }

    /// Something other than the query ended it — a panic, or an exception from
    /// the caller's callback. The span is closed; no duration is recorded,
    /// because there is no outcome of the query to record it under.
    pub(crate) fn abandon(self) {
        #[cfg(feature = "otel")]
        {
            use opentelemetry::trace::Span;
            let mut span = self.span;
            span.end();
        }
    }
}

// ── The awaitable stream ─────────────────────────────────────────────────

/// Where a [`PyRecordStream`] is in its life.
enum Phase {
    /// Nothing has been sent. The first read sends the query.
    NotStarted(Box<QueryRequest>),
    Running(RunningQuery),
    /// A read found the end, or the failure, behind records it had already
    /// taken. The records were returned; this is what the next read reports.
    Ending(Option<AsError>),
    Done,
}

/// Everything needed to send the query on the first read.
pub(crate) struct QueryRequest {
    pub(crate) client: Arc<AsClient>,
    pub(crate) policy: QueryPolicy,
    pub(crate) partition_filter: PartitionFilter,
    pub(crate) statement: Statement,
    pub(crate) op_name: &'static str,
    pub(crate) namespace: String,
    pub(crate) set_name: String,
    pub(crate) connection_info: Arc<crate::tracing::ConnectionInfo>,
}

struct StreamState {
    /// Held by the one read in flight. A second concurrent read waits for it.
    phase: tokio::sync::Mutex<Phase>,
    /// Outside `phase`, so that `close()` reaches the query while a read holds
    /// the phase and waits for records.
    stopper: Mutex<Option<Arc<StopSignal>>>,
    closed: AtomicBool,
    telemetry: Mutex<Option<QueryTelemetry>>,
}

/// Lock a mutex that guards plain data: a panic elsewhere cannot have left it
/// half-updated, so a poisoned lock is still good.
fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

impl StreamState {
    /// Report the outcome of the query, once.
    fn finish(&self, failure: Option<&AsError>) {
        if let Some(telemetry) = lock(&self.telemetry).take() {
            telemetry.finish(failure);
        }
    }

    fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }

    /// Stop the query and report it as ended. Safe to call at any time, from
    /// any thread, any number of times.
    fn close(&self) {
        self.closed.store(true, Ordering::Release);
        if let Some(stop) = lock(&self.stopper).take() {
            stop.stop();
        }
        self.finish(None);
    }

    /// Stop the query without reporting an outcome. For a query that
    /// something other than the query ended: an exception from the caller's
    /// callback is not a result of the query, as it is not for the sync
    /// `foreach`. The span is closed; no duration is recorded.
    fn abandon(&self) {
        self.closed.store(true, Ordering::Release);
        if let Some(stop) = lock(&self.stopper).take() {
            stop.stop();
        }
        if let Some(telemetry) = lock(&self.telemetry).take() {
            telemetry.abandon();
        }
    }

    /// Wait for at least one record and return it together with the records
    /// that have already arrived, up to `max_records`. `None` at the end.
    ///
    /// Dropping this future while it waits loses nothing: a record leaves the
    /// stream only in the poll that returns it.
    async fn next_batch(&self, max_records: usize) -> Result<Option<Vec<Record>>, AsError> {
        let mut phase = self.phase.lock().await;
        if self.is_closed() {
            *phase = Phase::Done;
            return Ok(None);
        }

        if matches!(*phase, Phase::NotStarted(_)) {
            let Phase::NotStarted(request) = std::mem::replace(&mut *phase, Phase::Done) else {
                unreachable!("checked by the matches! above");
            };
            let request = *request;
            // The clock starts when the query is sent, not when the stream
            // object was made: a stream nobody reads has no duration.
            *lock(&self.telemetry) = Some(QueryTelemetry::start(
                request.op_name,
                &request.namespace,
                &request.set_name,
                &request.connection_info,
            ));
            let running = RunningQuery::start(
                &request.client,
                &request.policy,
                request.partition_filter,
                request.statement,
            )
            .await
            .inspect_err(|e| self.finish(Some(e)))?;
            *lock(&self.stopper) = Some(running.stopper());
            if self.is_closed() {
                // close() ran between the check above and the line before this
                // one, found no stopper, and so could not stop what is now
                // running. Dropping `running` does.
                lock(&self.stopper).take();
                return Ok(None);
            }
            *phase = Phase::Running(running);
        }

        let running = match std::mem::replace(&mut *phase, Phase::Done) {
            Phase::Running(running) => running,
            Phase::Ending(None) | Phase::Done => {
                self.finish(None);
                return Ok(None);
            }
            Phase::Ending(Some(e)) => {
                self.finish(Some(&e));
                return Err(e);
            }
            Phase::NotStarted(_) => unreachable!("started above"),
        };
        *phase = Phase::Running(running);
        let Phase::Running(running) = &mut *phase else {
            unreachable!("assigned on the line above");
        };

        let first = running.next().await;
        if self.is_closed() {
            // Closed while this read was waiting. Whatever arrived is not
            // handed out: the caller asked for the stream to end.
            *phase = Phase::Done;
            return Ok(None);
        }
        let mut records = match first {
            Some(Ok(record)) => {
                let mut records = Vec::with_capacity(max_records.min(64));
                records.push(record);
                records
            }
            Some(Err(e)) => {
                *phase = Phase::Done;
                self.finish(Some(&e));
                return Err(e);
            }
            None => {
                *phase = Phase::Done;
                self.finish(None);
                return Ok(None);
            }
        };

        while records.len() < max_records {
            match running.next_if_ready() {
                Some(Some(Ok(record))) => records.push(record),
                Some(Some(Err(e))) => {
                    *phase = Phase::Ending(Some(e));
                    break;
                }
                Some(None) => {
                    *phase = Phase::Ending(None);
                    break;
                }
                None => break,
            }
        }
        Ok(Some(records))
    }
}

impl Drop for StreamState {
    fn drop(&mut self) {
        // The stream was let go of without being read to its end or closed.
        // `Phase::Running` stops the query when it drops; this reports it.
        self.finish(None);
    }
}

/// How many records [`PyRecordStream::read_all`] converts under one hold of
/// the GIL: some ten milliseconds' worth, so that the event loop and other
/// threads get their turn while a large result is being built.
const READ_ALL_CHUNK: usize = 4096;

/// One chunk of records being converted on a thread of its own.
type Converting = tokio::task::JoinHandle<PyResult<Vec<Py<PyAny>>>>;

/// Convert a chunk of records, and pass each through `wrap` when there is
/// one (the Python side's `Record` constructor). One hold of the GIL.
fn convert_chunk(chunk: Vec<Record>, wrap: Option<&Py<PyAny>>) -> PyResult<Vec<Py<PyAny>>> {
    Python::attach(|py| {
        let mut converted = Vec::with_capacity(chunk.len());
        for record in &chunk {
            let raw = record_to_py(py, record, None)?;
            converted.push(match wrap {
                Some(wrap) => wrap.call1(py, (raw,))?,
                None => raw,
            });
        }
        Ok(converted)
    })
}

/// Wait for a chunk that is being converted and append it to `converted`.
async fn collect_converted(
    converting: Option<Converting>,
    converted: &mut Vec<Py<PyAny>>,
) -> PyResult<()> {
    let Some(converting) = converting else {
        return Ok(());
    };
    let chunk = converting.await.map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("converting query records failed: {e}"))
    })??;
    if converted.is_empty() {
        *converted = chunk;
    } else {
        converted.extend(chunk);
    }
    Ok(())
}

/// Every record of a query, already converted: what
/// [`PyRecordStream::read_all`] resolves to.
pub(crate) struct ConvertedRecords(Vec<Py<PyAny>>);

impl<'py> IntoPyObject<'py> for ConvertedRecords {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        Ok(PyList::new(py, &self.0)?.into_any())
    }
}

/// Records on their way to Python: converted once the GIL is held, when the
/// awaited read completes.
pub(crate) struct PendingRecords(Vec<Record>);

impl<'py> IntoPyObject<'py> for PendingRecords {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let records: Vec<Py<PyAny>> = self
            .0
            .iter()
            .map(|record| record_to_py(py, record, None))
            .collect::<PyResult<_>>()?;
        Ok(PyList::new(py, &records)?.into_any())
    }
}

/// The records of a query, read a batch at a time by awaiting.
///
/// Created by `Query.stream()` and wrapped by `AsyncRecordStream` in Python.
/// Nothing is sent until the first `next_batch()`.
///
/// Memory is bounded whatever the pace of the reader: records wait in the
/// queue of [`RunningQuery`] (`record_queue_size` records), and when that is
/// full the per-node readers stop reading from the server.
#[pyclass(name = "RecordStream", module = "aerospike_py")]
pub struct PyRecordStream {
    state: Arc<StreamState>,
}

impl PyRecordStream {
    pub(crate) fn new(request: QueryRequest) -> Self {
        Self {
            state: Arc::new(StreamState {
                phase: tokio::sync::Mutex::new(Phase::NotStarted(Box::new(request))),
                stopper: Mutex::new(None),
                closed: AtomicBool::new(false),
                telemetry: Mutex::new(None),
            }),
        }
    }
}

#[pymethods]
impl PyRecordStream {
    /// Await the next records: a list of at least one and at most
    /// `max_records` `(key, meta, bins)` tuples, or `None` at the end.
    ///
    /// Cancelling the awaiting task drops the read without losing a record
    /// that is still in the stream. A record the read had already taken when
    /// the cancellation arrived is gone, which is why the Python wrapper
    /// closes the stream when a read is cancelled.
    #[pyo3(signature = (max_records=256))]
    fn next_batch<'py>(&self, py: Python<'py>, max_records: usize) -> PyResult<Bound<'py, PyAny>> {
        if max_records == 0 {
            return Err(PyValueError::new_err("max_records must be at least 1"));
        }
        let state = Arc::clone(&self.state);
        future_into_py_panic_safe(py, "RecordStream.next_batch", async move {
            state
                .next_batch(max_records)
                .await
                .map(|batch| batch.map(PendingRecords))
                .map_err(as_to_pyerr)
        })
    }

    /// Await the whole query: one list of every record, each passed through
    /// `wrap` when one is given, otherwise a `(key, meta, bins)` tuple.
    ///
    /// For `results()`, which keeps every record anyway. Reading through
    /// `next_batch` is a trip through the event loop for every batch, and
    /// with another thread holding the GIL each trip waits for it several
    /// times: 100 000 records took 5.6 s that way where 0.14.x took 0.6 s.
    ///
    /// Here the records are gathered on the runtime, without the GIL, and
    /// converted [`READ_ALL_CHUNK`] at a time on a thread of their own while
    /// the next ones are being fetched. The event loop is involved once, at
    /// the end, and has nothing left to do then: wrapping every record in the
    /// loop's own thread would stall it for as long as the whole result takes.
    /// The GIL is never held for longer than one chunk takes, and no more
    /// than three chunks of unconverted records are in memory.
    ///
    /// An error ends it without a result, as it always did for `results()`.
    /// Cancelling the awaiting task drops what was gathered; the caller
    /// closes the stream.
    #[pyo3(signature = (wrap=None))]
    fn read_all<'py>(
        &self,
        py: Python<'py>,
        wrap: Option<Py<PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let state = Arc::clone(&self.state);
        let wrap = wrap.map(Arc::new);
        future_into_py_panic_safe(py, "RecordStream.read_all", async move {
            let mut gathered: Vec<Record> = Vec::new();
            let mut converting: Option<Converting> = None;
            let mut converted: Vec<Py<PyAny>> = Vec::new();
            let convert = |chunk: Vec<Record>| -> Converting {
                let wrap = wrap.clone();
                tokio::task::spawn_blocking(move || convert_chunk(chunk, wrap.as_deref()))
            };
            while let Some(batch) = state
                .next_batch(READ_ALL_CHUNK)
                .await
                .map_err(as_to_pyerr)?
            {
                if gathered.is_empty() {
                    gathered = batch;
                } else {
                    gathered.extend(batch);
                }
                if gathered.len() >= READ_ALL_CHUNK {
                    // One chunk at a time, so that they come out in order. If
                    // the one before is still being converted, fetching waits
                    // for it here: the conversion is the slower of the two
                    // then, and nothing is gained by reading further ahead.
                    collect_converted(converting.take(), &mut converted).await?;
                    converting = Some(convert(std::mem::take(&mut gathered)));
                }
            }
            collect_converted(converting.take(), &mut converted).await?;
            if !gathered.is_empty() {
                collect_converted(Some(convert(gathered)), &mut converted).await?;
            }
            Ok(ConvertedRecords(converted))
        })
    }

    /// Stop the query. A read that is waiting returns `None`; so does every
    /// later one. Idempotent, and does not wait for anything.
    fn close(&self) {
        self.state.close();
    }

    /// Stop the query as `close()` does, without recording a duration for
    /// it. Used when the caller's own code failed, not the query.
    fn abandon(&self) {
        self.state.abandon();
    }

    /// Whether `close()` has been called.
    #[getter]
    fn closed(&self) -> bool {
        self.state.is_closed()
    }
}

impl Drop for PyRecordStream {
    fn drop(&mut self) {
        // A read in flight keeps the state alive, so the state's own drop is
        // not enough to stop a query nobody will read from again.
        self.state.close();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn telemetry() -> QueryTelemetry {
        let conn_info = crate::tracing::ConnectionInfo {
            server_address: "127.0.0.1".into(),
            server_port: 3000,
            cluster_name: "test".into(),
        };
        QueryTelemetry::start("query", "test", "demo", &conn_info)
    }

    fn state(phase: Phase) -> StreamState {
        StreamState {
            phase: tokio::sync::Mutex::new(phase),
            stopper: Mutex::new(None),
            closed: AtomicBool::new(false),
            telemetry: Mutex::new(Some(telemetry())),
        }
    }

    #[tokio::test]
    async fn a_closed_stream_reads_nothing_and_stays_ended() {
        let state = state(Phase::Ending(Some(AsError::client_error(
            "the stream failed",
        ))));
        state.close();

        assert!(state.next_batch(8).await.expect("no error").is_none());
        assert!(state.next_batch(8).await.expect("no error").is_none());
        assert!(matches!(*state.phase.lock().await, Phase::Done));
    }

    #[tokio::test]
    async fn an_end_found_behind_records_is_reported_by_the_next_read() {
        let state = state(Phase::Ending(None));

        assert!(state.next_batch(8).await.expect("no error").is_none());
        assert!(
            lock(&state.telemetry).is_none(),
            "reaching the end reports the query's outcome"
        );
    }

    #[tokio::test]
    async fn a_failure_found_behind_records_is_reported_once() {
        let state = state(Phase::Ending(Some(AsError::client_error(
            "the stream failed",
        ))));

        assert!(state.next_batch(8).await.is_err());
        assert!(
            state
                .next_batch(8)
                .await
                .expect("no second error")
                .is_none(),
            "the stream is over after its failure"
        );
    }

    #[test]
    fn closing_twice_reports_the_outcome_once() {
        let state = state(Phase::Done);
        state.close();
        assert!(lock(&state.telemetry).is_none());
        state.close();
        assert!(state.is_closed());
    }

    // --- the queue between the node readers and the consumer ---------------

    /// A record that can be told from the others: its generation is `n`.
    fn record(n: u32) -> Item {
        Ok(Record::new(None, Default::default(), None, n, 0))
    }

    fn number(item: Option<Item>) -> u32 {
        item.expect("a record, not the end")
            .expect("a record, not an error")
            .generation
    }

    /// A query with room for `allowed` waiting records and no server behind
    /// it: the test plays the node readers through the sender.
    fn running(allowed: usize) -> (mpsc::Sender<Item>, Arc<StopSignal>, RunningQuery) {
        let room = Room::for_records(allowed);
        let (queue, records) = mpsc::channel(room.queue);
        let stop = Arc::new(StopSignal::new());
        let running = RunningQuery {
            records,
            taken: Vec::new(),
            taken_at_once: room.taken_at_once,
            stop: Arc::clone(&stop),
        };
        (queue, stop, running)
    }

    /// Hand records over for as long as they are taken at once; how many were.
    fn fill(queue: &mpsc::Sender<Item>, stop: &Arc<StopSignal>, from: u32) -> u32 {
        let mut accepted = 0;
        while matches!(
            hand_over(queue, stop, record(from + accepted)),
            Either::Left(_)
        ) {
            accepted += 1;
        }
        // The record that did not fit is dropped with its future: the reader
        // of a real query would wait with it instead.
        accepted
    }

    #[test]
    fn no_more_records_wait_than_the_policy_allows() {
        for allowed in [1, 2, 3, 4, 5, 8, 16, 63, 64, 100, 256, 1024, 1_000_000] {
            let room = Room::for_records(allowed);
            assert!(room.queue >= 1, "{allowed}: {room:?}");
            assert!(
                (1..=Room::MOST_TAKEN_AT_ONCE).contains(&room.taken_at_once),
                "{allowed}: {room:?}"
            );
            assert_eq!(
                room.queue + room.taken_at_once - 1,
                allowed,
                "{allowed}: {room:?}"
            );
        }
        assert_eq!(
            Room::for_records(1024),
            Room {
                queue: 961,
                taken_at_once: 64
            }
        );

        let limited = QueryPolicy {
            record_queue_size: 1024,
            max_records: 10,
            ..QueryPolicy::default()
        };
        assert_eq!(Room::of(&limited), Room::for_records(10));
        let unset = QueryPolicy {
            record_queue_size: 0,
            ..QueryPolicy::default()
        };
        assert_eq!(Room::of(&unset), Room::for_records(1));
    }

    #[tokio::test]
    async fn records_come_out_once_and_in_the_order_they_went_in() {
        let (queue, stop, mut running) = running(1024);
        for n in 0..500 {
            let handed = hand_over(&queue, &stop, record(n));
            assert!(
                matches!(handed, Either::Left(_)),
                "there is room, so nothing waits"
            );
            assert!(handed.await, "the query goes on after a record");
        }
        drop(queue);

        // Some through `next`, some through `next_if_ready`, as a batch read does.
        let mut seen = Vec::new();
        while let Some(item) = running.next().await {
            seen.push(number(Some(item)));
            for _ in 0..3 {
                match running.next_if_ready() {
                    Some(Some(item)) => seen.push(number(Some(item))),
                    Some(None) | None => break,
                }
            }
        }
        assert_eq!(seen, (0..500).collect::<Vec<_>>());
        assert!(running.next().await.is_none(), "the end stays the end");
    }

    #[tokio::test]
    async fn what_waits_in_the_client_stays_within_the_room() {
        for allowed in [1_u32, 4, 16, 100, 1024] {
            let (queue, stop, mut running) = running(allowed as usize);
            let mut handed_over = fill(&queue, &stop, 0);
            let mut handed_out = 0;
            // Take one, let the readers fill up again, and so on: at no point
            // may more be waiting than the policy allows.
            for _ in 0..(3 * allowed) {
                assert_eq!(number(running.next().await), handed_out);
                handed_out += 1;
                handed_over += fill(&queue, &stop, handed_over);
                let waiting = handed_over - handed_out;
                assert!(waiting <= allowed, "{waiting} wait, {allowed} allowed");
            }
            assert!(
                handed_over - handed_out >= allowed / 2,
                "{allowed}: the room is used, not just respected"
            );
        }
    }

    #[tokio::test]
    async fn a_reader_without_room_waits_and_its_record_is_not_lost() {
        let (queue, stop, mut running) = running(4);
        assert_eq!(fill(&queue, &stop, 0), 4);

        let waiting = hand_over(&queue, &stop, record(4));
        assert!(matches!(waiting, Either::Right(_)), "the queue is full");
        tokio::pin!(waiting);
        assert!(
            futures::poll!(&mut waiting).is_pending(),
            "the reader waits for room"
        );

        assert_eq!(number(running.next().await), 0);
        assert!(waiting.await, "there is room now, and the query goes on");
        drop(queue);
        for n in 1..=4 {
            assert_eq!(number(running.next().await), n);
        }
        assert!(running.next().await.is_none());
    }

    #[tokio::test]
    async fn stopping_releases_a_reader_that_waits_for_room() {
        let (queue, stop, running) = running(4);
        assert_eq!(fill(&queue, &stop, 0), 4);
        let waiting = hand_over(&queue, &stop, record(4));
        tokio::pin!(waiting);
        assert!(futures::poll!(&mut waiting).is_pending());

        drop(running);

        assert!(!waiting.await, "a stopped query does not go on");
        let after = hand_over(&queue, &stop, record(5));
        assert!(
            matches!(after, Either::Left(_)),
            "nothing waits after a stop"
        );
        assert!(!after.await);
    }

    #[tokio::test]
    async fn the_error_that_ends_a_query_is_handed_over_and_ends_it() {
        let (queue, stop, mut running) = running(16);
        assert!(hand_over(&queue, &stop, record(0)).await);
        let goes_on = hand_over(&queue, &stop, Err(AsError::client_error("node gone"))).await;
        assert!(!goes_on, "the readers stop at the error");
        drop(queue);

        assert_eq!(number(running.next().await), 0);
        assert!(matches!(running.next().await, Some(Err(_))));
        assert!(running.next().await.is_none());
    }

    #[tokio::test]
    async fn taking_what_is_ready_never_waits() {
        let (queue, stop, mut running) = running(16);
        assert!(
            running.next_if_ready().is_none(),
            "nothing has arrived: taking one would mean waiting"
        );

        assert!(hand_over(&queue, &stop, record(7)).await);
        assert_eq!(number(running.next_if_ready().expect("it has arrived")), 7);
        assert!(running.next_if_ready().is_none());

        drop(queue);
        assert!(
            matches!(running.next_if_ready(), Some(None)),
            "the end is known without waiting"
        );
    }

    #[tokio::test]
    async fn a_consumer_told_to_stop_while_it_waits_gets_the_end() {
        let (_queue, stop, mut running) = running(16);
        let stopper = running.stopper();
        let reading = tokio::spawn(async move { running.next().await.is_none() });
        tokio::task::yield_now().await;
        stopper.stop();
        assert!(reading.await.expect("the read does not panic"));
        assert!(stop.is_stopped());
    }
}
