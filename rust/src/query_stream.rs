//! A running query: its records, what stops it, and what is reported about it.
//!
//! Three things use a query's record stream — `Query.results()`,
//! `Query.foreach()` and the awaitable [`PyRecordStream`] behind
//! `AsyncQuery` — and all three must stop it the same way. They share
//! [`RunningQuery`] for that and [`QueryTelemetry`] for the metric and the span.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::Instant;

use aerospike_core::query::{PartitionFilter, RecordStream};
use aerospike_core::{
    Client as AsClient, Error as AsError, QueryPolicy, Record, Recordset, Statement,
};
use futures::{FutureExt, StreamExt};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::errors::as_to_pyerr;
use crate::panic_safety::future_into_py_panic_safe;
use crate::types::record::record_to_py;

/// The record stream of a query that has been sent, and the handle that stops it.
///
/// **Dropping it stops the query.** The stream alone does not: aerospike-core's
/// per-node readers hold the `Recordset` too, so dropping the stream leaves them
/// blocked on a full record queue, and the server keeps the scan and its
/// connection until its socket timeout (30 seconds by default) runs out. Closing
/// the recordset fails the readers' next hand-over, which ends the commands at
/// once.
pub(crate) struct RunningQuery {
    recordset: Arc<Recordset>,
    stream: RecordStream,
}

impl RunningQuery {
    /// Send the query. Must run inside the Tokio runtime: the per-node readers
    /// are spawned from here.
    pub(crate) async fn start(
        client: &AsClient,
        policy: &QueryPolicy,
        partition_filter: PartitionFilter,
        statement: Statement,
    ) -> Result<Self, AsError> {
        let recordset = client.query(policy, partition_filter, statement).await?;
        let stream = Arc::clone(&recordset).into_stream();
        Ok(Self { recordset, stream })
    }

    /// The next record, an error that ended the stream, or `None` at its end.
    pub(crate) async fn next(&mut self) -> Option<Result<Record, AsError>> {
        self.stream.next().await
    }

    /// The next record if it has already arrived; `None` when taking one would
    /// mean waiting.
    fn next_if_ready(&mut self) -> Option<Option<Result<Record, AsError>>> {
        self.stream.next().now_or_never()
    }

    /// A handle that stops the query from outside, while a read is waiting.
    fn stopper(&self) -> Arc<Recordset> {
        Arc::clone(&self.recordset)
    }
}

impl Drop for RunningQuery {
    fn drop(&mut self) {
        self.recordset.close();
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
    stopper: Mutex<Option<Arc<Recordset>>>,
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
        if let Some(recordset) = lock(&self.stopper).take() {
            recordset.close();
        }
        self.finish(None);
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
/// Memory is bounded whatever the pace of the reader: records wait in
/// aerospike-core's record queue (`record_queue_size` records), and when that is
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

    /// Stop the query. A read that is waiting returns `None`; so does every
    /// later one. Idempotent, and does not wait for anything.
    fn close(&self) {
        self.state.close();
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
}
