//! Shared async business logic for both `PyClient` (sync) and `PyAsyncClient` (async).
//!
//! Each `do_*` function is an `async fn` that takes the Aerospike client and
//! pre-parsed arguments, performs the database operation with tracing/metrics,
//! and returns Rust-native types. No PyO3/Python types are involved in the
//! return values — Python conversion is the caller's responsibility.

use std::sync::Arc;

use aerospike_core::{
    BatchOperation, BatchPolicy, BatchRecord, BatchWritePolicy, Bins, Client as AsClient,
    Error as AsError, Key, Record, ResultCode, Task, Value,
};

use pyo3::PyResult;

use crate::batch_types::{PendingBatchRecords, RowOutcome};
use crate::client_common::{
    self, BatchApplyArgs, BatchOperateArgs, BatchReadArgs, BatchRemoveArgs, ExistsArgs, GetArgs,
    IndexCreateArgs, IndexRemoveArgs, InfoArgs, OperateArgs, PutArgs, PutPolicy, RemoveArgs,
    RemoveBinArgs, SelectArgs, SingleBinWriteArgs, TouchArgs, TruncateArgs, UdfPutArgs,
    UdfRemoveArgs,
};
use crate::errors::{as_to_pyerr, ErrorClass};
use crate::policy::write_policy::DEFAULT_WRITE_POLICY;
use crate::traced_exists_op;
use crate::traced_op;

// ── CRUD ────────────────────────────────────────────────────────────────────

/// Core 3.0 returns a bare routing error when close clears the partition map
/// between sends. In this case the last attempt failed before sending, but the
/// binding cannot know whether an earlier one reached the server.
async fn single_write_result<T>(
    client: &AsClient,
    connection: &crate::tracing::ConnectionInfo,
    key: &Key,
    policy: &aerospike_core::WritePolicy,
    writes: bool,
    operation: impl std::future::Future<Output = Result<T, AsError>>,
) -> PyResult<T> {
    use std::sync::atomic::Ordering;
    let could_retry = writes
        && policy.base_policy.max_retries > 0
        && !connection.closing.load(Ordering::Acquire)
        && client.is_strong_consistency(key.namespace()).is_some();
    operation.await.map_err(|err| {
        let lost_route_during_close = could_retry
            && connection.closing.load(Ordering::Acquire)
            && matches!(err.kind(), aerospike_core::ErrorKind::InvalidNamespace)
            && !client.partition_map_ready();
        crate::errors::as_to_pyerr_with_doubt(err, lost_route_during_close)
    })
}

macro_rules! observed_write {
    ($name:expr, $client:expr, $args:expr, $policy:expr, $writes:expr, $operation:expr) => {
        crate::observed_op!(
            $name,
            $args.key.namespace(),
            $args.key.set_name(),
            $args.otel.parent_ctx,
            $args.otel.conn_info,
            single_write_result(
                $client,
                &$args.otel.conn_info,
                &$args.key,
                $policy,
                $writes,
                $operation
            )
            .await
        )
    };
}

/// Write a record to the cluster.
pub async fn do_put(client: &AsClient, args: PutArgs) -> PyResult<()> {
    let policy = match &args.policy {
        PutPolicy::Default => &*DEFAULT_WRITE_POLICY,
        PutPolicy::Custom(policy) => policy,
    };
    observed_write!(
        "put",
        client,
        args,
        policy,
        true,
        client.put(policy, &args.key, &args.bins)
    )
}

/// Read all bins of a record.
pub async fn do_get(client: &AsClient, args: &GetArgs) -> PyResult<Record> {
    let rp = args.read_policy();
    traced_op!(
        "get",
        &args.key.namespace(),
        &args.key.set_name(),
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.get(rp, &args.key, Bins::All).await
    )
}

/// Read selected bins of a record.
pub async fn do_select(client: &AsClient, args: &SelectArgs) -> PyResult<Record> {
    let rp = args.read_policy();
    let bins_selector = args.bins_selector();
    traced_op!(
        "select",
        &args.key.namespace(),
        &args.key.set_name(),
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.get(rp, &args.key, bins_selector).await
    )
}

/// Check if a record exists. Returns the raw Result so callers can handle
/// KeyNotFoundError differently (sync returns tuple, async returns PendingExists).
pub async fn do_exists(client: &AsClient, args: &ExistsArgs) -> Result<Record, AsError> {
    traced_exists_op!(
        "exists",
        &args.key.namespace(),
        &args.key.set_name(),
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.get(&args.read_policy, &args.key, Bins::None).await
    )
}

/// Delete a record. Returns `PyErr(RecordNotFound)` if the record did not exist.
pub async fn do_remove(client: &AsClient, args: RemoveArgs) -> PyResult<()> {
    let existed = observed_write!(
        "delete",
        client,
        args,
        &args.write_policy,
        true,
        client.delete(&args.write_policy, &args.key)
    )?;

    if !existed {
        // The server reported KEY_NOT_FOUND_ERROR (wire code 2); aerospike-core
        // collapsed it into `Ok(false)`, so the exception is built here — with
        // the real wire code attached (ADR-0027), not the -1 sentinel.
        // With `max_retries > 0` this may be the answer to a second send
        // whose first one deleted the record; see
        // `rows_a_resend_leaves_in_doubt`.
        let may_be_a_resend = args.write_policy.base_policy.max_retries > 0;
        return Err(crate::errors::record_not_found_for_delete(may_be_a_resend));
    }
    Ok(())
}

/// Reset a record's TTL.
pub async fn do_touch(client: &AsClient, args: TouchArgs) -> PyResult<()> {
    observed_write!(
        "touch",
        client,
        args,
        &args.write_policy,
        true,
        client.touch(&args.write_policy, &args.key)
    )
}

/// Append string values to bins.
pub async fn do_append(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    observed_write!(
        "append",
        client,
        args,
        &args.write_policy,
        true,
        client.append(&args.write_policy, &args.key, &args.bins)
    )
}

/// Prepend string values to bins.
pub async fn do_prepend(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    observed_write!(
        "prepend",
        client,
        args,
        &args.write_policy,
        true,
        client.prepend(&args.write_policy, &args.key, &args.bins)
    )
}

/// Increment/add to numeric bins.
pub async fn do_increment(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    observed_write!(
        "increment",
        client,
        args,
        &args.write_policy,
        true,
        client.add(&args.write_policy, &args.key, &args.bins)
    )
}

/// Remove bins from a record by setting them to nil.
pub async fn do_remove_bin(client: &AsClient, args: RemoveBinArgs) -> PyResult<()> {
    observed_write!(
        "remove_bin",
        client,
        args,
        &args.write_policy,
        true,
        client.put(&args.write_policy, &args.key, &args.bins)
    )
}

// ── Multi-operation ─────────────────────────────────────────────────────────

/// Perform multiple operations on a single record.
pub async fn do_operate(client: &AsClient, args: &OperateArgs) -> PyResult<Record> {
    observed_write!(
        "operate",
        client,
        args,
        &args.write_policy,
        args.has_write,
        client.operate(&args.write_policy, &args.key, &args.ops)
    )
}

/// Perform multiple operations on a single record (ordered variant).
/// Uses the same underlying client.operate() call but different tracing name.
pub async fn do_operate_ordered(client: &AsClient, args: &OperateArgs) -> PyResult<Record> {
    observed_write!(
        "operate_ordered",
        client,
        args,
        &args.write_policy,
        args.has_write,
        client.operate(&args.write_policy, &args.key, &args.ops)
    )
}

// ── Batch ───────────────────────────────────────────────────────────────────

/// Take the rows out of the operations of a finished batch call.
///
/// `Client::batch` writes each result into the operation it belongs to and
/// returns only whether the call as a whole failed, so the rows exist either
/// way: one per operation, in request order.
///
/// Deliberately not `into_iter().map(..).collect()`: the standard library
/// would collect in place, into the allocation of `ops`. A `BatchOperation`
/// is 672 bytes and a `BatchRecord` 408, so every result would carry 264
/// bytes of unused capacity per row for as long as Python holds it.
fn collect_rows(ops: Vec<BatchOperation>) -> Vec<BatchRecord> {
    let mut rows = Vec::with_capacity(ops.len());
    rows.extend(ops.into_iter().map(BatchOperation::into_batch_record));
    rows
}

/// Give its key back to every row that lost it, and say which rows those
/// were (ascending).
///
/// While a batch runs, aerospike-core swaps each operation for an empty
/// stand-in and puts the real one back at the end. On the paths where it
/// returns early (no key could be routed at all, a job could not be joined)
/// the stand-ins are left behind, and a stand-in has an empty key. Such a row
/// is replaced by an unanswered row for the key the caller asked about, so a
/// partial result never names a key nobody requested.
fn restore_keys<'k>(rows: &mut [BatchRecord], keys: impl Iterator<Item = &'k Key>) -> Vec<usize> {
    let mut stand_ins = Vec::new();
    for (index, (row, key)) in rows.iter_mut().zip(keys).enumerate() {
        if row.key != *key {
            *row = BatchRecord::new(key.clone(), false);
            stand_ins.push(index);
        }
    }
    stand_ins
}

/// Whether a batch call that came back with an error of this class may have
/// sent the rows it left as stand-ins (see [`restore_keys`]).
///
/// aerospike-core returns without putting the rows back in two cases. When no
/// key could be routed, nothing was sent, and the error is the routing
/// failure: an invalid namespace, a partition without a node. When a node's
/// task could not be joined - it panicked, or the runtime is going down - its
/// request may have gone out before, and the answers of the other nodes are
/// lost along with it; the error is then a bare client error. Only the routing
/// failures are known to mean "nothing was sent". For anything else a write
/// may have been applied, and a row that says "no answer, not in doubt" would
/// invite the caller to send it again.
fn unanswered_rows_may_have_been_sent(class: ErrorClass) -> bool {
    !matches!(class, ErrorClass::InvalidArgument | ErrorClass::InvalidNode)
}

/// Turn a finished batch call into its rows, or into an exception that
/// carries them.
///
/// A call fails as a whole when a node's share of it could not be completed.
/// The rows the other nodes answered are still valid, so they are attached to
/// the exception as `partial_result` instead of being dropped: the exception
/// type is the one this failure always raised, and the caller who wants to
/// know which records are done can now find out.
///
/// Not every error of the call is such a failure. aerospike-core sends a key
/// that is alone on its node as a single-record command, and when the server
/// answers that one with a code worth a retry (KEY_BUSY, DEVICE_OVERLOAD, ...)
/// and no attempt is left, the answer comes back as the error of the whole
/// call. In a larger batch the same answer is just that row's result, and it
/// was with Rust client 2.x for a batch of any size. So the call fails only
/// when a row is left without a server's answer; otherwise every row says
/// what happened to its record and the call returns them.
fn finish_batch<'k>(
    ops: Vec<BatchOperation>,
    outcome: Result<(), AsError>,
    keys: impl Iterator<Item = &'k Key>,
    policy: &BatchPolicy,
    writes: bool,
) -> PyResult<PendingBatchRecords> {
    let Settled {
        rows,
        failure,
        stand_ins,
    } = settle_batch(ops, outcome, keys);
    let mut in_doubt_rows = if writes {
        rows_a_resend_leaves_in_doubt(&rows, policy)
    } else {
        Vec::new()
    };
    let gave_up_after_sending = writes
        && !stand_ins.is_empty()
        && failure
            .as_ref()
            .is_some_and(|err| unanswered_rows_may_have_been_sent(ErrorClass::of(err)));
    if gave_up_after_sending {
        in_doubt_rows.extend(stand_ins);
        in_doubt_rows.sort_unstable();
        in_doubt_rows.dedup();
    }
    let pending = PendingBatchRecords {
        in_doubt_rows,
        results: rows,
        retry_stats: None,
    };
    match failure {
        None => Ok(pending),
        Some(err) => Err(crate::batch_types::attach_partial_result(
            as_to_pyerr(err),
            pending,
            gave_up_after_sending,
        )),
    }
}

/// A finished batch call.
struct Settled {
    rows: Vec<BatchRecord>,
    /// The call's error, if it failed as a whole (see [`finish_batch`] for
    /// when it did).
    failure: Option<AsError>,
    /// The rows aerospike-core left as stand-ins: see [`restore_keys`].
    stand_ins: Vec<usize>,
}

fn settle_batch<'k>(
    ops: Vec<BatchOperation>,
    outcome: Result<(), AsError>,
    keys: impl Iterator<Item = &'k Key>,
) -> Settled {
    let mut rows = collect_rows(ops);
    let Err(err) = outcome else {
        return Settled {
            rows,
            failure: None,
            stand_ins: Vec::new(),
        };
    };
    let stand_ins = restore_keys(&mut rows, keys);
    let failure = if rows.iter().all(row_has_a_server_answer) {
        None
    } else {
        Some(err)
    };
    Settled {
        rows,
        failure,
        stand_ins,
    }
}

/// The failed rows of a write batch that say nothing certain about a *first*
/// send of their record, although they look as if they did, in ascending
/// order.
///
/// With `max_retries > 0` aerospike-core sends a node's share of a batch again
/// when its answer did not arrive. Two kinds of row then mislead.
///
/// **The answer to the second send.** If the first send had been applied, the
/// second one meets its own work: a delete finds no record, a write whose
/// filter the first send made false is filtered out, a UDF fails on the state
/// it left behind. Such a row says "failed" about a record that was changed.
/// For most answers aerospike-core marks a row that was sent before as in
/// doubt. These three it reads on the path of an ordinary record, which has
/// no such mark.
///
/// **No second send at all.** When no node can be found for a record at the
/// time of the re-send (its node was dropped from the cluster meanwhile, or
/// the client was closed), aerospike-core gives the row
/// `PARTITION_UNAVAILABLE` and calls it certain, "since nothing was sent".
/// That is true of the send that did not happen and says nothing of the one
/// before it. With 20 000 records and a client closed between the two sends,
/// some hundreds of rows per call said "refused, not in doubt" of records
/// that had been written.
///
/// The binding cannot see whether a row was sent before. So when re-sending
/// is switched on (it is off by default for a batch that writes), every row
/// of a write that ends in one of these ways is reported in doubt: the call
/// does not know, and says so. That includes a record that could not be
/// routed at the first send either, which was certainly not written.
fn rows_a_resend_leaves_in_doubt(rows: &[BatchRecord], batch_policy: &BatchPolicy) -> Vec<usize> {
    if batch_policy.base_policy.max_retries == 0 {
        return Vec::new();
    }
    rows.iter()
        .enumerate()
        .filter(|(_, row)| {
            row.has_write()
                && (crate::batch_types::could_not_be_routed(row)
                    || matches!(
                        RowOutcome::of(row),
                        RowOutcome::Failed(ErrorClass::Server(
                            ResultCode::KeyNotFoundError
                                | ResultCode::FilteredOut
                                | ResultCode::UdfBadResponse
                        ))
                    ))
        })
        .map(|(index, _)| index)
        .collect()
}

/// Whether a server said what happened to this row's record: success, or a
/// result code of its own.
fn row_has_a_server_answer(row: &BatchRecord) -> bool {
    matches!(
        RowOutcome::of(row),
        RowOutcome::Ok | RowOutcome::Failed(ErrorClass::Server(_))
    )
}

/// Read multiple records in a batch.
pub async fn do_batch_read(client: &AsClient, args: &BatchReadArgs) -> PyResult<Vec<BatchRecord>> {
    crate::observed_op!(
        "batch_read",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        send_and_settle_batch(
            client,
            &args.batch_policy,
            args.to_batch_ops(),
            args.rust_keys.iter(),
            false
        )
        .await
    )
    .map(|batch| batch.results)
}

async fn send_and_settle_batch<'k>(
    client: &AsClient,
    policy: &BatchPolicy,
    mut ops: Vec<BatchOperation>,
    keys: impl Iterator<Item = &'k Key>,
    writes: bool,
) -> PyResult<PendingBatchRecords> {
    let outcome = client.batch(policy, &mut ops).await;
    finish_batch(ops, outcome, keys, policy, writes)
}

/// Perform operations on multiple records in a batch.
pub async fn do_batch_operate(
    client: &AsClient,
    args: &BatchOperateArgs,
) -> PyResult<PendingBatchRecords> {
    crate::observed_op!(
        "batch_operate",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        send_and_settle_batch(
            client,
            &args.batch_policy,
            args.to_batch_ops(),
            args.rust_keys.iter(),
            args.has_write()
        )
        .await
    )
}

/// Remove multiple records in a batch.
pub async fn do_batch_remove(
    client: &AsClient,
    args: &BatchRemoveArgs,
) -> PyResult<PendingBatchRecords> {
    crate::observed_op!(
        "batch_remove",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        send_and_settle_batch(
            client,
            &args.batch_policy,
            args.to_batch_ops(),
            args.records.iter().map(|(key, _)| key),
            true
        )
        .await
    )
}

/// Execute a UDF on multiple records in a batch.
pub async fn do_batch_apply(
    client: &AsClient,
    args: &BatchApplyArgs,
) -> PyResult<PendingBatchRecords> {
    crate::observed_op!(
        "batch_apply",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        send_and_settle_batch(
            client,
            &args.batch_policy,
            args.to_batch_ops(),
            args.records.iter().map(|entry| &entry.0),
            true
        )
        .await
    )
}

/// Check if a batch record result code is retryable.
///
/// Retries on transient errors: timeout, device overload, key busy,
/// server memory error, or partition unavailable. Permanent errors
/// (key exists, record too big, etc.) are not retried.
fn is_retryable_result_code(rc: &aerospike_core::ResultCode) -> bool {
    use aerospike_core::ResultCode;
    matches!(
        rc,
        ResultCode::Timeout
            | ResultCode::DeviceOverload
            | ResultCode::KeyBusy
            | ResultCode::ServerMemError
            | ResultCode::PartitionUnavailable
    )
}

/// Whether a failure that never reached, or never came back from, a server is
/// worth another attempt. A bad argument or an unreadable response is not: it
/// would fail the same way again.
fn is_retryable_client_failure(class: ErrorClass) -> bool {
    matches!(
        class,
        ErrorClass::ClientTimeout
            | ErrorClass::RetriesExhausted
            | ErrorClass::Connection
            | ErrorClass::NoMoreConnections
            | ErrorClass::MaxErrorRate
            | ErrorClass::InvalidNode
    )
}

/// Whether another attempt may get past this failure.
fn failure_may_pass(class: ErrorClass) -> bool {
    match class {
        ErrorClass::Server(rc) => is_retryable_result_code(&rc),
        other => is_retryable_client_failure(other),
    }
}

/// Whether sending this `put` a second time gives the same end state as
/// sending it once.
///
/// A plain `put` overwrites the bins it names, so it does. A put that only
/// succeeds on a record in a particular state does not: once the first send
/// has been applied, `CREATE_ONLY` finds the record it just created and a
/// generation check finds the generation it just bumped, and the second send
/// fails for a write that in fact went through. The first send may also
/// invalidate a filter or start a requested relative TTL. A put containing
/// only NIL bins can delete the record by removing its last bin; replaying
/// it would then report KEY_NOT_FOUND for a successful deletion.
fn put_is_idempotent(policy: &BatchWritePolicy, bins: &[aerospike_core::Bin]) -> bool {
    policy.generation_policy == aerospike_core::GenerationPolicy::None
        && policy.record_exists_action != aerospike_core::RecordExistsAction::CreateOnly
        && policy.filter_expression.is_none()
        && !matches!(policy.expiration, aerospike_core::Expiration::Seconds(_))
        && bins.iter().any(|bin| bin.value != Value::Nil)
}

/// What the retry loop needs to know about one row.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
struct RowJudgement {
    /// The row did not succeed.
    failed: bool,
    /// The row failed in a way another attempt may fix, and another attempt is
    /// safe.
    retry: bool,
    /// The row failed and the write may have been applied anyway.
    in_doubt: bool,
    /// The row failed without a server answering for it.
    unanswered: bool,
}

/// Judge one `batch_write` row.
///
/// `idempotent` checks the row's bins and write policy when a transient
/// failure is in doubt. A row is retried only when a second send cannot
/// do harm: either the first one certainly was not applied (`!in_doubt`), or
/// applying it twice is the same as applying it once.
fn judge_row(
    outcome: RowOutcome,
    in_doubt: bool,
    idempotent: impl FnOnce() -> bool,
) -> RowJudgement {
    let (transient, unanswered) = match outcome {
        RowOutcome::Ok => return RowJudgement::default(),
        RowOutcome::NoResponse => (true, true),
        RowOutcome::Failed(class) => (
            failure_may_pass(class),
            !matches!(class, ErrorClass::Server(_)),
        ),
    };
    RowJudgement {
        failed: true,
        retry: transient && (!in_doubt || idempotent()),
        in_doubt,
        unanswered,
    }
}

/// The judgement of a row that came back without any answer, when the way
/// its call failed settles it. `None` leaves the row to [`judge_row`].
fn judge_unanswered(
    gave_up_after_sending: bool,
    call_would_fail_again: bool,
) -> Option<RowJudgement> {
    if gave_up_after_sending {
        // Sent, perhaps, and never answered: see
        // `unanswered_rows_may_have_been_sent`. Sending it again could apply
        // the write a second time, and what made the call give up may do so
        // again.
        return Some(RowJudgement {
            failed: true,
            retry: false,
            in_doubt: true,
            unanswered: true,
        });
    }
    call_would_fail_again.then_some(RowJudgement {
        failed: true,
        retry: false,
        in_doubt: false,
        unanswered: true,
    })
}

/// Compute backoff duration in milliseconds using Full Jitter strategy.
///
/// Returns a random value in `[0, min(cap_ms, base_ms * 2^attempt)]`.
/// The shift exponent is capped at 6 to prevent overflow (`10 * 2^6 = 640 > 500`).
fn compute_backoff_ms(attempt: u32, base_ms: u64, cap_ms: u64) -> u64 {
    use rand::RngExt;
    let capped_attempt = std::cmp::min(attempt, 6);
    let max_backoff = std::cmp::min(base_ms * (1u64 << capped_attempt), cap_ms);
    rand::rng().random_range(0..=max_backoff)
}

/// Whether the remaining `total_timeout` budget still permits another attempt.
///
/// `timeout_ms == 0` means no budget was configured, so retries are unbounded by
/// time. Otherwise an attempt is allowed only if waiting `backoff_ms` still
/// leaves the deadline in the future — this is the guard that silently truncates
/// `retry=N` under the 1000 ms default `total_timeout`.
fn retry_budget_permits(elapsed_ms: u64, backoff_ms: u64, timeout_ms: u64) -> bool {
    timeout_ms == 0 || elapsed_ms + backoff_ms < timeout_ms
}

/// What the client-side retry loop actually did, so Python can see truncation.
///
/// `retry=N` promises `N + 1` attempts, but the elapsed-time guard above stops
/// early once `total_timeout` runs out. Without these counters that difference
/// is invisible from Python — the only report was a `log::warn!`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BatchWriteRetryStats {
    /// Attempts actually issued, including the initial send. Always >= 1.
    pub attempts: u32,
    /// Attempts the caller asked for: `1 + retry`.
    pub max_attempts: u32,
    /// The elapsed-time guard stopped the loop while records still needed
    /// retrying — i.e. `total_timeout` truncated `retry=N`.
    pub truncated_by_timeout: bool,
    /// Records still carrying a retryable failure when the loop ended.
    pub unresolved: u32,
}

impl BatchWriteRetryStats {
    /// Stats for a path that issues exactly one batch call and never retries.
    pub const SINGLE_ATTEMPT: Self = Self {
        attempts: 1,
        max_attempts: 1,
        truncated_by_timeout: false,
        unresolved: 0,
    };
}

/// Write multiple records from pre-parsed (key, bins) pairs with optional retry.
///
/// When `max_retries > 0`, the records that failed with a transient error are
/// sent again in further batch calls, up to `max_retries` times, with a Full
/// Jitter exponential backoff (`random_between(0, min(cap, base * 2^attempt))`)
/// in between.
///
/// **Retry behaviour:**
/// - Every attempt reports a row for each record it sent, also when the call
///   as a whole failed: the rows other nodes answered are kept, and only the
///   records that failed are sent again. A record that already succeeded is
///   never re-sent.
/// - A record is sent again when its failure is transient — a retryable
///   server code, or no answer because of a timeout or a lost connection — and
///   a second send cannot do harm. A call that failed in a way that would
///   repeat (an unknown namespace, an invalid argument) is not attempted
///   again. A plain `put` overwrites its bins, so
///   another send restores its bin values. A filtered, create-only or
///   generation-checked put, an all-NIL put, or one setting an explicit
///   relative TTL is left alone when the first send may already have applied.
/// - If, when the loop ends, a record still has no answer from a server, the
///   call raises the failure of the attempt that left it that way, with every
///   row attached as `partial_result`. Otherwise the call returns `Ok` and
///   the per-record result codes say what happened.
/// - The elapsed time guard prevents retries when `elapsed + backoff >= total_timeout`,
///   but does not account for the actual batch operation time. Total wall-clock
///   time may exceed `total_timeout` by up to one additional timeout window.
///   `total_timeout` defaults to **1000 ms**, so a large `retry=N` is routinely
///   truncated: with Full Jitter doubling from 10 ms plus each attempt's own
///   network time, `retry=10` yields far fewer than 11 attempts by default.
///   Callers who want the full count must raise `total_timeout` themselves —
///   this function never lengthens the budget on its own.
/// - The returned [`BatchWriteRetryStats`] reports how many attempts were
///   actually issued, whether the timeout guard truncated them, and how many
///   records are still failing, so that truncation is visible from Python
///   instead of only in a `log::warn!`.
/// - Callers should always check per-record `result` values regardless of
///   the overall `Ok` return status.
#[allow(clippy::too_many_arguments)]
pub async fn do_batch_write(
    client: &AsClient,
    batch_policy: &aerospike_core::BatchPolicy,
    records: &[(
        aerospike_core::Key,
        Vec<aerospike_core::Bin>,
        Arc<BatchWritePolicy>,
    )],
    ns: &str,
    set: &str,
    parent_ctx: client_common::ParentContext,
    conn_info: Arc<crate::tracing::ConnectionInfo>,
    max_retries: u32,
    op_name: &str,
) -> PyResult<PendingBatchRecords> {
    let run = async {
        // Fast path: no retry — build ops directly, no cache overhead
        if max_retries == 0 {
            let batch_ops: Vec<BatchOperation> = crate::stage_timer!("build_ops", op_name, {
                records
                    .iter()
                    .map(|(key, bins, write_policy)| {
                        let ops: Vec<aerospike_core::operations::Operation> =
                            bins.iter().map(aerospike_core::operations::put).collect();
                        BatchOperation::write(write_policy, key.clone(), ops)
                    })
                    .collect()
            });
            let mut pending = crate::stage_timer!(
                "io",
                op_name,
                send_and_settle_batch(
                    client,
                    batch_policy,
                    batch_ops,
                    records.iter().map(|(key, _, _)| key),
                    true
                )
                .await
            )?;
            pending.retry_stats = Some(BatchWriteRetryStats::SINGLE_ATTEMPT);
            return Ok(pending);
        }

        // Retry path: pre-build ops once per record, reuse via clone on retry
        let cached_ops: Vec<Vec<aerospike_core::operations::Operation>> = records
            .iter()
            .map(|(_, bins, _)| bins.iter().map(aerospike_core::operations::put).collect())
            .collect();

        let timeout_ms = batch_policy.base_policy.total_timeout as u64;
        let env = ClusterAttempts {
            client,
            batch_policy,
            records,
            cached_ops,
            ns,
            set,
            parent_ctx: &parent_ctx,
            conn_info: &conn_info,
            retry_op_name: format!("{}_retry", op_name),
            start: std::time::Instant::now(),
            call_would_fail_again: std::sync::atomic::AtomicBool::new(false),
            gave_up_after_sending: std::sync::atomic::AtomicBool::new(false),
        };
        let BatchWriteOutcome {
            mut rows,
            stats,
            in_doubt_rows,
            error,
        } = drive_batch_write_retries(&env, max_retries, timeout_ms).await;

        match error {
            None => Ok(PendingBatchRecords {
                results: rows,
                retry_stats: Some(stats),
                in_doubt_rows,
            }),
            Some(err) => {
                restore_keys(&mut rows, records.iter().map(|(key, _, _)| key));
                let gave_up_after_sending = env
                    .gave_up_after_sending
                    .load(std::sync::atomic::Ordering::Relaxed);
                let mut in_doubt_rows = in_doubt_rows;
                if gave_up_after_sending {
                    // A row without any answer cannot say that it is in doubt:
                    // that is known from the call, not from the row.
                    in_doubt_rows.extend(
                        rows.iter()
                            .enumerate()
                            .filter(|(_, row)| RowOutcome::of(row) == RowOutcome::NoResponse)
                            .map(|(index, _)| index),
                    );
                    in_doubt_rows.sort_unstable();
                    in_doubt_rows.dedup();
                }
                Err(crate::batch_types::attach_partial_result(
                    err,
                    PendingBatchRecords {
                        results: rows,
                        retry_stats: Some(stats),
                        in_doubt_rows,
                    },
                    gave_up_after_sending,
                ))
            }
        }
    };
    crate::observed_op!(op_name, ns, set, parent_ctx, conn_info, run.await)
}

/// The outside world the retry loop talks to: a clock, a sleep, and one send.
///
/// Extracted purely so [`drive_batch_write_retries`] can be exercised without a
/// cluster. `retry=N`'s whole point is what happens when attempts fail or the
/// budget runs out, and those paths are not reachable from an integration test
/// against a healthy server — forcing per-record retryable codes with a tiny
/// `socket_timeout` succeeded in 1 run out of 10 (measured), which is a flake
/// rather than a test. A scripted implementation makes them deterministic.
///
/// The row type is the implementation's own. The loop never looks inside a
/// row; it asks [`judge`](Self::judge). That matters for the scripted
/// implementation: a failed `aerospike_core::BatchRecord` can only be built by
/// aerospike-core itself.
///
/// Generic, not boxed: each call monomorphises into the code the loop had
/// inline, and the `max_retries == 0` fast path never reaches here at all.
trait BatchWriteAttempts {
    /// One record's result from one attempt.
    type Row: Send;

    /// Milliseconds since the call began.
    fn elapsed_ms(&self) -> u64;

    /// Send one attempt: every record when `indices` is `None`, otherwise the
    /// listed ones.
    ///
    /// Returns one row per record sent, in the order sent, together with the
    /// failure of the call as a whole when it had one. The rows are complete
    /// in both cases.
    fn send(
        &self,
        indices: Option<&[usize]>,
        attempt: u32,
    ) -> impl std::future::Future<Output = (Vec<Self::Row>, Option<pyo3::PyErr>)> + Send;

    /// Judge the row the record at `index` currently has.
    fn judge(&self, index: usize, row: &Self::Row) -> RowJudgement;

    /// Wait out the backoff between attempts.
    fn sleep_ms(&self, ms: u64) -> impl std::future::Future<Output = ()> + Send;
}

/// The real implementation: a batch call against the cluster, traced as before.
struct ClusterAttempts<'a> {
    client: &'a AsClient,
    batch_policy: &'a aerospike_core::BatchPolicy,
    records: &'a [(
        aerospike_core::Key,
        Vec<aerospike_core::Bin>,
        Arc<BatchWritePolicy>,
    )],
    cached_ops: Vec<Vec<aerospike_core::operations::Operation>>,
    ns: &'a str,
    set: &'a str,
    parent_ctx: &'a client_common::ParentContext,
    conn_info: &'a Arc<crate::tracing::ConnectionInfo>,
    retry_op_name: String,
    start: std::time::Instant,
    /// The last attempt failed as a whole in a way that would repeat (an
    /// unknown namespace, an invalid argument). aerospike-core then returns
    /// before it has marked the rows, which leaves them looking merely
    /// unanswered; this keeps them from being sent again for nothing.
    call_would_fail_again: std::sync::atomic::AtomicBool,
    /// The last attempt came back without its rows, and may have sent them
    /// before: see [`unanswered_rows_may_have_been_sent`]. Those rows are in
    /// doubt, and are not sent again.
    gave_up_after_sending: std::sync::atomic::AtomicBool,
}

impl BatchWriteAttempts for ClusterAttempts<'_> {
    type Row = BatchRecord;

    fn elapsed_ms(&self) -> u64 {
        self.start.elapsed().as_millis() as u64
    }

    async fn send(
        &self,
        indices: Option<&[usize]>,
        attempt: u32,
    ) -> (Vec<BatchRecord>, Option<pyo3::PyErr>) {
        // Build this attempt from cached ops (avoids rebuilding from bins).
        let mut attempt_ops: Vec<BatchOperation> = match indices {
            Some(indices) => indices
                .iter()
                .map(|&i| {
                    let (key, _, write_policy) = &self.records[i];
                    BatchOperation::write(write_policy, key.clone(), self.cached_ops[i].clone())
                })
                .collect(),
            None => self
                .records
                .iter()
                .zip(self.cached_ops.iter())
                .map(|((key, _, write_policy), ops)| {
                    BatchOperation::write(write_policy, key.clone(), ops.clone())
                })
                .collect(),
        };

        // The enclosing span/timer covers the complete public call. Extra
        // sends retain their own attempt-level metric and span.
        let send = self.client.batch(self.batch_policy, &mut attempt_ops);
        let result = if attempt == 0 {
            send.await
        } else {
            crate::observed_op!(
                self.retry_op_name.as_str(),
                self.ns,
                self.set,
                *self.parent_ctx,
                *self.conn_info,
                send.await
            )
        };
        let call_class = result.as_ref().err().map(ErrorClass::of);
        let outcome = result.map_err(as_to_pyerr);
        self.call_would_fail_again.store(
            call_class.is_some_and(|class| !failure_may_pass(class)),
            std::sync::atomic::Ordering::Relaxed,
        );
        let mut rows = collect_rows(attempt_ops);
        let stand_ins = if outcome.is_err() {
            match indices {
                Some(indices) => {
                    restore_keys(&mut rows, indices.iter().map(|&i| &self.records[i].0))
                }
                None => restore_keys(&mut rows, self.records.iter().map(|(key, _, _)| key)),
            }
        } else {
            Vec::new()
        };
        self.gave_up_after_sending.store(
            !stand_ins.is_empty() && call_class.is_none_or(unanswered_rows_may_have_been_sent),
            std::sync::atomic::Ordering::Relaxed,
        );
        (rows, outcome.err())
    }

    fn judge(&self, index: usize, row: &BatchRecord) -> RowJudgement {
        if crate::batch_types::row_ok(row) {
            return RowJudgement::default();
        }
        let outcome = RowOutcome::of(row);
        if outcome == RowOutcome::NoResponse {
            let settled_by_the_call = judge_unanswered(
                self.gave_up_after_sending
                    .load(std::sync::atomic::Ordering::Relaxed),
                self.call_would_fail_again
                    .load(std::sync::atomic::Ordering::Relaxed),
            );
            if let Some(judgement) = settled_by_the_call {
                return judgement;
            }
        }
        judge_row(
            outcome,
            crate::batch_types::row_in_doubt(row, outcome),
            || {
                let (_, bins, policy) = &self.records[index];
                put_is_idempotent(policy, bins)
            },
        )
    }

    async fn sleep_ms(&self, ms: u64) {
        tokio::time::sleep(std::time::Duration::from_millis(ms)).await;
    }
}

/// What [`drive_batch_write_retries`] ended with.
struct BatchWriteOutcome<R> {
    /// One row per record, in request order: the result of the last attempt
    /// that sent the record.
    rows: Vec<R>,
    stats: BatchWriteRetryStats,
    /// Ascending indices of failed rows that an earlier attempt left in doubt,
    /// although their last attempt did not. See the loop.
    in_doubt_rows: Vec<usize>,
    /// Set when a record still has no answer from a server: the failure of the
    /// most recent attempt that failed as a whole.
    error: Option<pyo3::PyErr>,
}

/// Drive the attempt/retry loop. See [`do_batch_write`] for the semantics.
async fn drive_batch_write_retries<E: BatchWriteAttempts + Sync>(
    env: &E,
    max_retries: u32,
    timeout_ms: u64,
) -> BatchWriteOutcome<E::Row> {
    let mut results: Vec<E::Row> = Vec::new();
    let mut retry_indices: Vec<usize> = Vec::new();
    let mut call_error: Option<pyo3::PyErr> = None;
    // `ever_in_doubt[i]`: some attempt left record `i` in doubt. Stays empty
    // until an attempt does, which is the rare case.
    let mut ever_in_doubt: Vec<bool> = Vec::new();
    let mut unanswered: usize = 0;
    let mut attempts_made: u32 = 0;
    let mut truncated_by_timeout = false;

    // Attempt 0 is the initial send; attempts 1..=max_retries are the retries
    // that `retry=N` buys.
    for attempt in 0..=max_retries {
        if attempt > 0 {
            // Full Jitter backoff: random_between(0, min(500ms, 10ms * 2^attempt))
            let backoff_ms = compute_backoff_ms(attempt - 1, 10, 500);

            // Elapsed time guard: stop retries if remaining time is insufficient.
            // This is what truncates `retry=N` under the 1000 ms default
            // `total_timeout`; record it so Python can see it happened.
            let elapsed_ms = env.elapsed_ms();
            if !retry_budget_permits(elapsed_ms, backoff_ms, timeout_ms) {
                log::warn!(
                    "batch_write retry: elapsed {}ms + backoff {}ms >= timeout {}ms, \
                     stopping after {}/{} attempt(s)",
                    elapsed_ms,
                    backoff_ms,
                    timeout_ms,
                    attempts_made,
                    max_retries.saturating_add(1)
                );
                truncated_by_timeout = true;
                break;
            }

            log::info!(
                "batch_write retry: {} record(s) to re-send, attempt {}/{}, backoff {}ms",
                retry_indices.len(),
                attempt,
                max_retries,
                backoff_ms
            );
            env.sleep_ms(backoff_ms).await;
        }

        attempts_made += 1;
        let (attempt_rows, attempt_error) = env
            .send(
                if attempt == 0 {
                    None
                } else {
                    Some(&retry_indices)
                },
                attempt,
            )
            .await;
        if let Some(e) = attempt_error {
            log::warn!(
                "batch_write: attempt {}/{} failed as a whole: {}",
                attempt,
                max_retries,
                e
            );
            call_error = Some(e);
        }

        if attempt == 0 {
            results = attempt_rows;
        } else {
            // Put each re-sent record's new row in its original place.
            if attempt_rows.len() != retry_indices.len() {
                log::warn!(
                    "batch_write retry: expected {} results, got {}",
                    retry_indices.len(),
                    attempt_rows.len()
                );
            }
            for (original_idx, row) in retry_indices.iter().copied().zip(attempt_rows) {
                results[original_idx] = row;
            }
        }

        // Judge every record again: which to send once more, which are still
        // without an answer.
        retry_indices.clear();
        unanswered = 0;
        for (i, row) in results.iter().enumerate() {
            let judgement = env.judge(i, row);
            if judgement.in_doubt {
                if ever_in_doubt.is_empty() {
                    ever_in_doubt.resize(results.len(), false);
                }
                ever_in_doubt[i] = true;
            }
            if judgement.retry {
                retry_indices.push(i);
            }
            if judgement.unanswered {
                unanswered += 1;
            }
        }
        if retry_indices.is_empty() {
            log::debug!(
                "batch_write: nothing left to re-send after {} attempt(s)",
                attempt + 1
            );
            break;
        }
    }

    // A record that was in doubt after one attempt and then failed again in a
    // way that is not in doubt by itself (the retry never left the client, or
    // the server refused it) is still in doubt: the earlier send may have been
    // applied. Only a later success settles it.
    let in_doubt_rows: Vec<usize> = ever_in_doubt
        .iter()
        .enumerate()
        .filter(|&(i, &was)| {
            was && {
                let judgement = env.judge(i, &results[i]);
                judgement.failed && !judgement.in_doubt
            }
        })
        .map(|(i, _)| i)
        .collect();

    // `retry_indices` already holds the records still carrying a retryable
    // failure, so reporting it costs nothing extra.
    let stats = BatchWriteRetryStats {
        attempts: attempts_made,
        max_attempts: max_retries.saturating_add(1),
        truncated_by_timeout,
        unresolved: retry_indices.len() as u32,
    };
    if stats.attempts < stats.max_attempts && stats.unresolved > 0 {
        log::warn!(
            "batch_write: {} record(s) still failing after {} of {} attempt(s){}",
            stats.unresolved,
            stats.attempts,
            stats.max_attempts,
            if truncated_by_timeout {
                " — retries truncated by total_timeout"
            } else {
                ""
            }
        );
    }

    BatchWriteOutcome {
        rows: results,
        stats,
        in_doubt_rows,
        // An earlier attempt may have failed as a whole and a later one made
        // up for it; that is a success. The failure is only reported while a
        // record is still without an answer.
        error: if unanswered > 0 { call_error } else { None },
    }
}

// ── Info ────────────────────────────────────────────────────────────────────

/// Send an info command to all nodes.
pub async fn do_info_all(
    client: &AsClient,
    args: &InfoArgs,
) -> PyResult<Vec<(String, i32, String)>> {
    let nodes = client.nodes();
    let mut results = Vec::new();
    for node in &nodes {
        let r = node.info(&args.admin_policy, &[&args.command]).await;
        results.push(client_common::info_node_result(node, &args.command, r));
    }
    Ok(results)
}

/// Send an info command to a random node.
pub async fn do_info_random_node(client: &AsClient, args: &InfoArgs) -> PyResult<String> {
    let map = client
        .info(&args.admin_policy, &[&args.command])
        .await
        .map_err(as_to_pyerr)?;
    Ok(map.get(&args.command).cloned().unwrap_or_default())
}

/// Lightweight health check: send `info("build")` to a random node.
/// Returns `true` if the node responds, `false` otherwise.
pub async fn do_ping(client: &AsClient) -> bool {
    let policy = aerospike_core::AdminPolicy::default();
    client.info(&policy, &["build"]).await.is_ok()
}

// ── Truncate ────────────────────────────────────────────────────────────────

/// Truncate records in a namespace/set.
pub async fn do_truncate(client: &AsClient, args: TruncateArgs) -> PyResult<()> {
    client
        .truncate(
            &args.admin_policy,
            &args.namespace,
            &args.set_name,
            args.nanos,
        )
        .await
        .map_err(as_to_pyerr)
}

// ── UDF ─────────────────────────────────────────────────────────────────────

/// Register a UDF module.
pub async fn do_udf_put(client: &AsClient, args: UdfPutArgs) -> PyResult<()> {
    let task = client
        .register_udf(
            &args.admin_policy,
            &args.udf_body,
            &args.server_path,
            args.language,
        )
        .await
        .map_err(as_to_pyerr)?;
    task.wait_till_complete(None::<std::time::Duration>)
        .await
        .map_err(as_to_pyerr)?;
    Ok(())
}

/// Remove a UDF module.
pub async fn do_udf_remove(client: &AsClient, args: UdfRemoveArgs) -> PyResult<()> {
    let task = client
        .remove_udf(&args.admin_policy, &args.server_path)
        .await
        .map_err(as_to_pyerr)?;
    task.wait_till_complete(None::<std::time::Duration>)
        .await
        .map_err(as_to_pyerr)?;
    Ok(())
}

/// Execute a UDF on a single record.
pub async fn do_apply(
    client: &AsClient,
    args: &client_common::ApplyArgs,
) -> PyResult<Option<Value>> {
    single_write_result(
        client,
        &args.connection_info,
        &args.key,
        &args.write_policy,
        true,
        client.execute_udf(
            &args.write_policy,
            &args.key,
            &args.module,
            &args.function,
            args.args.as_deref().unwrap_or(&[]),
        ),
    )
    .await
}

// ── Index ───────────────────────────────────────────────────────────────────

/// Create a secondary index.
pub async fn do_index_create(client: &AsClient, args: IndexCreateArgs) -> PyResult<()> {
    let task = client
        .create_index_on_bin(
            &args.admin_policy,
            &args.namespace,
            &args.set_name,
            &args.bin_name,
            &args.index_name,
            args.index_type,
            aerospike_core::CollectionIndexType::Default,
            None,
        )
        .await
        .map_err(as_to_pyerr)?;
    task.wait_till_complete(None::<std::time::Duration>)
        .await
        .map_err(as_to_pyerr)?;
    Ok(())
}

/// Remove a secondary index.
pub async fn do_index_remove(client: &AsClient, args: IndexRemoveArgs) -> PyResult<()> {
    client
        .drop_index(&args.admin_policy, &args.namespace, "", &args.index_name)
        .await
        .map_err(as_to_pyerr)?;
    Ok(())
}

// ── Admin: User ─────────────────────────────────────────────────────────────

/// Create a new user with the given roles.
pub async fn do_admin_create_user(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: &str,
    password: &str,
    roles: &[String],
) -> PyResult<()> {
    let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
    client
        .create_user(admin_policy, username, password, &role_refs)
        .await
        .map_err(as_to_pyerr)
}

/// Drop (delete) a user.
pub async fn do_admin_drop_user(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: &str,
) -> PyResult<()> {
    client
        .drop_user(admin_policy, username)
        .await
        .map_err(as_to_pyerr)
}

/// Change a user's password.
pub async fn do_admin_change_password(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: &str,
    password: &str,
) -> PyResult<()> {
    client
        .change_password(admin_policy, username, password)
        .await
        .map_err(as_to_pyerr)
}

/// Grant roles to a user.
pub async fn do_admin_grant_roles(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: &str,
    roles: &[String],
) -> PyResult<()> {
    let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
    client
        .grant_roles(admin_policy, username, &role_refs)
        .await
        .map_err(as_to_pyerr)
}

/// Revoke roles from a user.
pub async fn do_admin_revoke_roles(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: &str,
    roles: &[String],
) -> PyResult<()> {
    let role_refs: Vec<&str> = roles.iter().map(|s| s.as_str()).collect();
    client
        .revoke_roles(admin_policy, username, &role_refs)
        .await
        .map_err(as_to_pyerr)
}

/// Query users (optionally filtered by username).
pub async fn do_admin_query_users(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    username: Option<&str>,
) -> PyResult<Vec<aerospike_core::User>> {
    client
        .query_users(admin_policy, username)
        .await
        .map_err(as_to_pyerr)
}

// ── Admin: Role ─────────────────────────────────────────────────────────────

/// Create a new role.
pub async fn do_admin_create_role(
    client: &AsClient,
    args: client_common::CreateRoleArgs,
) -> PyResult<()> {
    let wl_refs: Vec<&str> = args.whitelist.iter().map(|s| s.as_str()).collect();
    client
        .create_role(
            &args.admin_policy,
            &args.role,
            &args.privileges,
            &wl_refs,
            args.read_quota,
            args.write_quota,
        )
        .await
        .map_err(as_to_pyerr)
}

/// Drop (delete) a role.
pub async fn do_admin_drop_role(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: &str,
) -> PyResult<()> {
    client
        .drop_role(admin_policy, role)
        .await
        .map_err(as_to_pyerr)
}

/// Grant privileges to a role.
pub async fn do_admin_grant_privileges(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: &str,
    privileges: &[aerospike_core::Privilege],
) -> PyResult<()> {
    client
        .grant_privileges(admin_policy, role, privileges)
        .await
        .map_err(as_to_pyerr)
}

/// Revoke privileges from a role.
pub async fn do_admin_revoke_privileges(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: &str,
    privileges: &[aerospike_core::Privilege],
) -> PyResult<()> {
    client
        .revoke_privileges(admin_policy, role, privileges)
        .await
        .map_err(as_to_pyerr)
}

/// Query roles (optionally filtered by role name).
pub async fn do_admin_query_roles(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: Option<&str>,
) -> PyResult<Vec<aerospike_core::Role>> {
    client
        .query_roles(admin_policy, role)
        .await
        .map_err(as_to_pyerr)
}

/// Set allowlist (whitelist) for a role.
pub async fn do_admin_set_whitelist(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: &str,
    whitelist: &[String],
) -> PyResult<()> {
    let wl_refs: Vec<&str> = whitelist.iter().map(|s| s.as_str()).collect();
    client
        .set_allowlist(admin_policy, role, &wl_refs)
        .await
        .map_err(as_to_pyerr)
}

/// Set quotas for a role.
pub async fn do_admin_set_quotas(
    client: &AsClient,
    admin_policy: &aerospike_core::AdminPolicy,
    role: &str,
    read_quota: u32,
    write_quota: u32,
) -> PyResult<()> {
    client
        .set_quotas(admin_policy, role, read_quota, write_quota)
        .await
        .map_err(as_to_pyerr)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aerospike_core::ResultCode;

    #[test]
    fn test_retryable_timeout() {
        assert!(is_retryable_result_code(&ResultCode::Timeout));
    }

    #[test]
    fn test_retryable_device_overload() {
        assert!(is_retryable_result_code(&ResultCode::DeviceOverload));
    }

    #[test]
    fn test_retryable_key_busy() {
        assert!(is_retryable_result_code(&ResultCode::KeyBusy));
    }

    #[test]
    fn test_retryable_server_mem_error() {
        assert!(is_retryable_result_code(&ResultCode::ServerMemError));
    }

    #[test]
    fn test_retryable_partition_unavailable() {
        assert!(is_retryable_result_code(&ResultCode::PartitionUnavailable));
    }

    #[test]
    fn test_not_retryable_ok() {
        assert!(!is_retryable_result_code(&ResultCode::Ok));
    }

    #[test]
    fn test_not_retryable_key_exists() {
        assert!(!is_retryable_result_code(&ResultCode::KeyExistsError));
    }

    #[test]
    fn test_not_retryable_record_too_big() {
        assert!(!is_retryable_result_code(&ResultCode::RecordTooBig));
    }

    #[test]
    fn test_not_retryable_key_not_found() {
        assert!(!is_retryable_result_code(&ResultCode::KeyNotFoundError));
    }

    #[test]
    fn test_not_retryable_bin_type_error() {
        assert!(!is_retryable_result_code(&ResultCode::BinTypeError));
    }

    #[test]
    fn test_backoff_range() {
        // Full Jitter: result must be in [0, min(cap, base * 2^attempt)]
        for attempt in 0..=6 {
            let max_expected = std::cmp::min(10u64 * (1u64 << attempt), 500);
            for _ in 0..1000 {
                let val = compute_backoff_ms(attempt, 10, 500);
                assert!(
                    val <= max_expected,
                    "attempt={attempt}, val={val}, max={max_expected}"
                );
            }
        }
    }

    #[test]
    fn test_backoff_cap_enforced() {
        // Even with high attempt, backoff should never exceed cap
        for _ in 0..1000 {
            let val = compute_backoff_ms(10, 10, 500);
            assert!(val <= 500, "val={val} exceeded cap 500");
        }
    }

    #[test]
    fn test_backoff_overflow_safety() {
        // Very large attempt values should not panic
        let val = compute_backoff_ms(100, 10, 500);
        assert!(val <= 500);
        let val = compute_backoff_ms(u32::MAX, 10, 500);
        assert!(val <= 500);
    }

    // ── retry_budget_permits: the guard that truncates retry=N ─────────────

    #[test]
    fn test_budget_permits_with_room_to_spare() {
        assert!(retry_budget_permits(100, 50, 1000));
    }

    #[test]
    fn test_budget_boundary_is_exclusive() {
        // elapsed + backoff == timeout must NOT permit another attempt: the
        // deadline would be reached exactly when the backoff ends.
        assert!(!retry_budget_permits(950, 50, 1000));
        assert!(retry_budget_permits(949, 50, 1000));
    }

    #[test]
    fn test_budget_denies_when_overrun() {
        assert!(!retry_budget_permits(990, 50, 1000));
        assert!(!retry_budget_permits(2000, 0, 1000));
    }

    #[test]
    fn test_zero_timeout_means_unbounded() {
        // total_timeout = 0 is "no budget configured", not "no time left".
        assert!(retry_budget_permits(u64::MAX / 2, 500, 0));
    }

    #[test]
    fn test_default_total_timeout_truncates_full_jitter_ladder() {
        // The reported failure mode: BasePolicy::default() is total_timeout =
        // 1000ms, and the Full Jitter ladder caps at 500ms per wait, so once a
        // few attempts have been spent the guard denies the rest.
        const DEFAULT_TOTAL_TIMEOUT_MS: u64 = 1000;
        assert!(!retry_budget_permits(600, 500, DEFAULT_TOTAL_TIMEOUT_MS));
        assert!(!retry_budget_permits(900, 250, DEFAULT_TOTAL_TIMEOUT_MS));
    }

    // ── judge_row / put_is_idempotent: which rows are sent again ───────────

    const IDEMPOTENT: fn() -> bool = || true;
    const CONDITIONAL: fn() -> bool = || false;

    fn server(rc: ResultCode) -> RowOutcome {
        RowOutcome::Failed(ErrorClass::Server(rc))
    }

    #[test]
    fn test_a_successful_row_needs_nothing() {
        assert_eq!(
            judge_row(RowOutcome::Ok, false, IDEMPOTENT),
            RowJudgement::default()
        );
    }

    #[test]
    fn test_a_transient_server_code_is_retried_and_counts_as_answered() {
        let judgement = judge_row(server(ResultCode::DeviceOverload), false, CONDITIONAL);
        assert!(judgement.failed && judgement.retry);
        assert!(
            !judgement.unanswered,
            "a server that refuses a write did answer"
        );
    }

    #[test]
    fn test_a_permanent_server_code_is_not_retried() {
        for rc in [
            ResultCode::KeyExistsError,
            ResultCode::GenerationError,
            ResultCode::RecordTooBig,
            ResultCode::KeyNotFoundError,
            ResultCode::FilteredOut,
        ] {
            let judgement = judge_row(server(rc), false, IDEMPOTENT);
            assert!(judgement.failed, "{rc:?}");
            assert!(!judgement.retry, "{rc:?} would fail the same way again");
        }
    }

    #[test]
    fn test_losing_the_connection_or_timing_out_is_retried_for_a_plain_put() {
        for class in [
            ErrorClass::ClientTimeout,
            ErrorClass::RetriesExhausted,
            ErrorClass::Connection,
            ErrorClass::NoMoreConnections,
            ErrorClass::MaxErrorRate,
            ErrorClass::InvalidNode,
        ] {
            let judgement = judge_row(RowOutcome::Failed(class), true, IDEMPOTENT);
            assert!(judgement.retry, "{class:?}");
            assert!(judgement.unanswered, "{class:?}: no server answered");
            assert!(judgement.in_doubt, "{class:?}");
        }
    }

    #[test]
    fn test_a_client_failure_that_would_repeat_is_not_retried() {
        for class in [
            ErrorClass::InvalidArgument,
            ErrorClass::BadResponse,
            ErrorClass::Client,
            ErrorClass::Unknown,
        ] {
            let judgement = judge_row(RowOutcome::Failed(class), false, IDEMPOTENT);
            assert!(!judgement.retry, "{class:?}");
            assert!(judgement.unanswered, "{class:?}");
        }
    }

    #[test]
    fn test_only_a_failure_that_may_pass_is_worth_another_attempt() {
        assert!(failure_may_pass(ErrorClass::Connection));
        assert!(failure_may_pass(ErrorClass::ClientTimeout));
        assert!(failure_may_pass(ErrorClass::Server(
            ResultCode::DeviceOverload
        )));
        // An unknown namespace or a bad argument fails the same way again.
        assert!(!failure_may_pass(ErrorClass::InvalidArgument));
        assert!(!failure_may_pass(ErrorClass::Server(
            ResultCode::KeyExistsError
        )));
    }

    #[test]
    fn test_a_row_nobody_answered_is_retried() {
        let judgement = judge_row(RowOutcome::NoResponse, false, CONDITIONAL);
        assert!(judgement.failed && judgement.retry && judgement.unanswered);
    }

    #[test]
    fn test_a_conditional_write_in_doubt_is_never_sent_again() {
        // The first send may have created the record. A second CREATE_ONLY
        // would then fail with KEY_EXISTS for a write that went through.
        for outcome in [
            RowOutcome::Failed(ErrorClass::ClientTimeout),
            RowOutcome::Failed(ErrorClass::Connection),
            server(ResultCode::Timeout),
        ] {
            let judgement = judge_row(outcome, true, CONDITIONAL);
            assert!(!judgement.retry, "{outcome:?}");
            assert!(judgement.in_doubt, "{outcome:?}");
        }
    }

    #[test]
    fn test_a_conditional_write_that_was_certainly_not_applied_is_sent_again() {
        // The server refused it outright, or it never left the client.
        assert!(judge_row(server(ResultCode::DeviceOverload), false, CONDITIONAL).retry);
        assert!(
            judge_row(
                RowOutcome::Failed(ErrorClass::NoMoreConnections),
                false,
                CONDITIONAL
            )
            .retry
        );
    }

    #[test]
    fn test_only_an_unconditional_put_is_idempotent() {
        use aerospike_core::{GenerationPolicy, RecordExistsAction};

        let bins = [aerospike_core::Bin::new("v", Value::Int(1))];
        assert!(put_is_idempotent(&BatchWritePolicy::default(), &bins));

        for action in [
            RecordExistsAction::Update,
            RecordExistsAction::UpdateOnly,
            RecordExistsAction::Replace,
            RecordExistsAction::ReplaceOnly,
        ] {
            let policy = BatchWritePolicy {
                record_exists_action: action,
                ..BatchWritePolicy::default()
            };
            assert!(put_is_idempotent(&policy, &bins), "{action:?}");
        }

        let create_only = BatchWritePolicy {
            record_exists_action: RecordExistsAction::CreateOnly,
            ..BatchWritePolicy::default()
        };
        assert!(!put_is_idempotent(&create_only, &bins));

        for generation_policy in [
            GenerationPolicy::ExpectGenEqual,
            GenerationPolicy::ExpectGenGreater,
        ] {
            let policy = BatchWritePolicy {
                generation_policy,
                ..BatchWritePolicy::default()
            };
            assert!(!put_is_idempotent(&policy, &bins), "{generation_policy:?}");
        }
    }

    #[test]
    fn a_put_that_may_remove_the_last_bin_retries_only_after_a_definite_refusal() {
        let policy = BatchWritePolicy::default();
        let mut bins = vec![aerospike_core::Bin::new("only", Value::Nil)];
        let idempotent = || put_is_idempotent(&policy, &bins);
        assert!(!judge_row(RowOutcome::Failed(ErrorClass::Connection), true, idempotent).retry);
        assert!(judge_row(server(ResultCode::KeyBusy), false, idempotent).retry);
        bins.push(aerospike_core::Bin::new("preserved", Value::Int(0)));
        assert!(put_is_idempotent(&policy, &bins));
    }

    #[test]
    fn filtered_and_expiring_puts_are_retried_only_after_a_definite_refusal() {
        let bins = [aerospike_core::Bin::new("v", Value::Int(1))];
        for policy in [
            BatchWritePolicy {
                filter_expression: Some(aerospike_core::expressions::bool_val(true)),
                ..BatchWritePolicy::default()
            },
            BatchWritePolicy {
                expiration: aerospike_core::Expiration::Seconds(120),
                ..BatchWritePolicy::default()
            },
        ] {
            let idempotent = || put_is_idempotent(&policy, &bins);
            assert!(!judge_row(RowOutcome::Failed(ErrorClass::Connection), true, idempotent).retry);
            assert!(judge_row(server(ResultCode::KeyBusy), false, idempotent).retry);
        }
    }

    // ── collect_rows / restore_keys ─────────────────────────────────────────

    fn test_key(name: &str) -> Key {
        Key::new("test", "demo", Value::from(name.to_string())).unwrap()
    }

    #[test]
    fn test_rows_come_out_in_request_order() {
        let policy = aerospike_core::BatchReadPolicy::default();
        let ops = vec![
            BatchOperation::read(&policy, test_key("a"), Bins::All),
            BatchOperation::read(&policy, test_key("b"), Bins::All),
        ];
        let rows = collect_rows(ops);

        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].key.digest(), test_key("a").digest());
        assert_eq!(rows[1].key.digest(), test_key("b").digest());
        assert_eq!(
            RowOutcome::of(&rows[0]),
            RowOutcome::NoResponse,
            "an operation that was never run has no outcome, and that is not OK"
        );
    }

    #[test]
    fn test_the_rows_do_not_keep_the_request_buffer() {
        // Collected in place, the rows would sit in the operations'
        // allocation: capacity for about 1.6 rows per row, held for as long
        // as Python holds the result.
        let policy = aerospike_core::BatchReadPolicy::default();
        let ops: Vec<BatchOperation> = (0..1000)
            .map(|i| BatchOperation::read(&policy, test_key(&i.to_string()), Bins::All))
            .collect();

        let rows = collect_rows(ops);

        assert_eq!(rows.len(), 1000);
        assert_eq!(rows.capacity(), rows.len());
    }

    #[test]
    fn test_a_row_that_lost_its_key_gets_the_requested_one_back() {
        // What aerospike-core leaves in the caller's slice when it returns
        // before putting the operations back: a row with an empty key.
        let stand_in = BatchRecord::new(Key::with_digest("", "", None, [0; 20]), false);
        let mut answered = BatchRecord::new(test_key("b"), false);
        answered.record = Some(Record::new(
            None,
            aerospike_core::IndexMap::new(),
            None,
            7,
            0,
        ));
        let mut rows = vec![stand_in, answered];
        // The placeholder digest is also a legal explicitly supplied digest.
        let keys = [
            Key::with_digest("test", "demo", Some(Value::Int(7)), [0; 20]),
            test_key("b"),
        ];

        let stand_ins = restore_keys(&mut rows, keys.iter());

        assert_eq!(stand_ins, vec![0]);
        assert_eq!(rows[0].key, keys[0]);
        assert_eq!(rows[0].key.namespace(), "test");
        assert_eq!(RowOutcome::of(&rows[0]), RowOutcome::NoResponse);
        assert_eq!(
            rows[1].record.as_ref().map(|r| r.generation),
            Some(7),
            "a row that kept its key keeps its result"
        );
    }

    // ── a call that gave up on rows it may have sent ───────────────────────

    /// What aerospike-core leaves in the caller's slice when it returns
    /// before putting the operations back.
    fn stand_in_ops(count: usize) -> Vec<BatchOperation> {
        let policy = aerospike_core::BatchReadPolicy::default();
        (0..count)
            .map(|_| {
                let nobody = Key::with_digest("", "", None, [0; 20]);
                BatchOperation::read(&policy, nobody, Bins::All)
            })
            .collect()
    }

    /// Run `finish_batch` on a call that left only stand-ins behind and
    /// failed with `error`. Returns `(result, in_doubt)` of the rows on the
    /// exception, and the exception's own `in_doubt`.
    fn gave_up_with(error: AsError, writes: bool) -> (Vec<(i32, bool)>, bool) {
        pyo3::Python::initialize();
        let keys = [test_key("a"), test_key("b")];
        let policy = BatchPolicy::default();
        let raised = finish_batch(
            stand_in_ops(keys.len()),
            Err(error),
            keys.iter(),
            &policy,
            writes,
        )
        .err()
        .expect("a call that left rows without an answer fails as a whole");

        pyo3::Python::attach(|py| {
            use pyo3::types::PyAnyMethods;
            let exception = raised.value(py);
            let rows = exception
                .getattr("partial_result")
                .unwrap()
                .getattr("batch_records")
                .unwrap()
                .try_iter()
                .unwrap()
                .map(|row| {
                    let row = row.unwrap();
                    (
                        row.getattr("result").unwrap().extract::<i32>().unwrap(),
                        row.getattr("in_doubt").unwrap().extract::<bool>().unwrap(),
                    )
                })
                .collect();
            let in_doubt = exception.getattr("in_doubt").unwrap().extract().unwrap();
            (rows, in_doubt)
        })
    }

    /// The `in_doubt` of the exception a failed call raises with these rows
    /// attached, when the call's own error says "not in doubt".
    fn call_in_doubt_with_rows(in_doubt_rows: Vec<usize>) -> (Vec<bool>, bool) {
        pyo3::Python::initialize();
        let rows = PendingBatchRecords {
            in_doubt_rows,
            results: vec![
                BatchRecord::new(test_key("a"), true),
                BatchRecord::new(test_key("b"), true),
            ],
            retry_stats: None,
        };
        // An error that is certain by itself: nothing was sent for it.
        let refused = as_to_pyerr(AsError::invalid_argument("refused"));
        let raised = crate::batch_types::attach_partial_result(refused, rows, false);

        pyo3::Python::attach(|py| {
            use pyo3::types::PyAnyMethods;
            let exception = raised.value(py);
            let rows = exception
                .getattr("partial_result")
                .unwrap()
                .getattr("batch_records")
                .unwrap()
                .try_iter()
                .unwrap()
                .map(|row| row.unwrap().getattr("in_doubt").unwrap().extract().unwrap())
                .collect();
            (
                rows,
                exception.getattr("in_doubt").unwrap().extract().unwrap(),
            )
        })
    }

    #[test]
    fn test_a_failed_call_is_in_doubt_when_one_of_its_rows_is() {
        // A call that failed on two nodes raises the error of one of them. A
        // refusal from the first must not hide that the second node's share
        // was sent and never answered.
        let (rows, call_in_doubt) = call_in_doubt_with_rows(vec![1]);
        assert_eq!(rows, vec![false, true]);
        assert!(call_in_doubt, "a write of this call may have been applied");

        let (rows, call_in_doubt) = call_in_doubt_with_rows(Vec::new());
        assert_eq!(rows, vec![false, false]);
        assert!(!call_in_doubt);
    }

    #[test]
    fn test_a_write_batch_whose_task_was_lost_is_in_doubt() {
        // A node's task panicked or was cancelled: aerospike-core reports a
        // bare client error and hands back no row at all, also not the ones
        // other nodes had answered. The requests may all have gone out.
        let (rows, call_in_doubt) = gave_up_with(AsError::client_error("task 7 panicked"), true);

        assert_eq!(rows, vec![(-1, true), (-1, true)]);
        assert!(call_in_doubt);
    }

    #[test]
    fn test_a_batch_that_could_not_be_routed_was_never_sent() {
        let (rows, call_in_doubt) =
            gave_up_with(AsError::invalid_argument("namespace not found"), true);

        assert_eq!(rows, vec![(-1, false), (-1, false)]);
        assert!(!call_in_doubt);
    }

    #[test]
    fn test_reads_are_not_in_doubt_whatever_became_of_the_task() {
        let (rows, call_in_doubt) = gave_up_with(AsError::client_error("task 7 panicked"), false);

        assert_eq!(rows, vec![(-1, false), (-1, false)]);
        assert!(!call_in_doubt);
    }

    #[test]
    fn test_only_a_routing_failure_proves_that_nothing_was_sent() {
        assert!(!unanswered_rows_may_have_been_sent(
            ErrorClass::InvalidArgument
        ));
        assert!(!unanswered_rows_may_have_been_sent(ErrorClass::InvalidNode));
        for class in [
            ErrorClass::Client,
            ErrorClass::Connection,
            ErrorClass::ClientTimeout,
            ErrorClass::Unknown,
        ] {
            assert!(unanswered_rows_may_have_been_sent(class), "{class:?}");
        }
    }

    #[test]
    fn test_an_unanswered_row_of_the_retry_loop_follows_its_call() {
        let gave_up = judge_unanswered(true, true).expect("settled");
        assert!(gave_up.failed && gave_up.in_doubt && gave_up.unanswered);
        assert!(!gave_up.retry, "a write that may be in is not sent again");

        let never_sent = judge_unanswered(false, true).expect("settled");
        assert!(never_sent.failed && never_sent.unanswered);
        assert!(!never_sent.in_doubt && !never_sent.retry);

        assert_eq!(
            judge_unanswered(false, false),
            None,
            "an attempt that may pass next time is judged like any other row"
        );
    }

    // ── drive_batch_write_retries: the loop's own control flow ─────────────
    //
    // `truncated_by_timeout` and `unresolved` are not reachable from an
    // integration test against a healthy server: forcing per-record retryable
    // codes with a tiny `socket_timeout` succeeded in 1 run out of 10
    // (measured), which is a flake rather than a test. A scripted
    // `BatchWriteAttempts` makes them exact.
    //
    // The scripted rows are this module's own type. A failed
    // `aerospike_core::BatchRecord` can only be built inside aerospike-core,
    // and the loop does not look inside a row anyway: it asks `judge`.

    /// One record's result in a scripted attempt.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    struct Row {
        outcome: RowOutcome,
        in_doubt: bool,
    }

    const OK: Row = Row {
        outcome: RowOutcome::Ok,
        in_doubt: false,
    };

    /// The server answered with a failure code.
    fn refused(rc: ResultCode) -> Row {
        Row {
            outcome: server(rc),
            // A server that gave up waiting may already have taken the
            // write: `row_in_doubt` reports such a row in doubt.
            in_doubt: rc == ResultCode::Timeout,
        }
    }

    /// The request was sent and the connection died before the answer.
    const LOST: Row = Row {
        outcome: RowOutcome::Failed(ErrorClass::Connection),
        in_doubt: true,
    };

    /// The request never left the client.
    const UNSENT: Row = Row {
        outcome: RowOutcome::Failed(ErrorClass::NoMoreConnections),
        in_doubt: false,
    };

    /// What a scripted attempt returns: the rows of the records it was asked
    /// to send, in that order.
    enum Scripted {
        /// The call succeeded.
        Rows(Vec<Row>),
        /// The call failed as a whole; the rows are still there.
        CallFailed(Vec<Row>),
    }

    /// A `BatchWriteAttempts` with a canned response per attempt and a clock the
    /// test drives, so the elapsed-time guard fires exactly when intended.
    struct ScriptedAttempts {
        responses: Vec<Scripted>,
        /// Per record: whether its put may be sent twice.
        idempotent: Vec<bool>,
        /// Milliseconds each send consumes.
        step_ms: u64,
        elapsed: std::sync::atomic::AtomicU64,
        /// What each attempt asked for: `None` = full batch, `Some` = subset.
        sent: std::sync::Mutex<Vec<Option<Vec<usize>>>>,
    }

    impl ScriptedAttempts {
        fn new(record_count: usize, step_ms: u64, responses: Vec<Scripted>) -> Self {
            Self {
                responses,
                idempotent: vec![true; record_count],
                step_ms,
                elapsed: std::sync::atomic::AtomicU64::new(0),
                sent: std::sync::Mutex::new(Vec::new()),
            }
        }

        /// Mark the listed records as conditional writes.
        fn conditional(mut self, indices: &[usize]) -> Self {
            for &i in indices {
                self.idempotent[i] = false;
            }
            self
        }

        fn sends(&self) -> Vec<Option<Vec<usize>>> {
            self.sent.lock().unwrap().clone()
        }
    }

    impl BatchWriteAttempts for ScriptedAttempts {
        type Row = Row;

        fn elapsed_ms(&self) -> u64 {
            self.elapsed.load(std::sync::atomic::Ordering::Relaxed)
        }

        async fn send(
            &self,
            indices: Option<&[usize]>,
            attempt: u32,
        ) -> (Vec<Row>, Option<pyo3::PyErr>) {
            self.sent
                .lock()
                .unwrap()
                .push(indices.map(<[usize]>::to_vec));
            self.elapsed
                .fetch_add(self.step_ms, std::sync::atomic::Ordering::Relaxed);
            let asked = indices.map_or(self.idempotent.len(), <[usize]>::len);
            let call_error = || crate::errors::ClusterError::new_err("scripted call failure");
            match self.responses.get(attempt as usize) {
                Some(Scripted::Rows(rows)) => {
                    assert_eq!(rows.len(), asked, "attempt {attempt}: script/row mismatch");
                    (rows.clone(), None)
                }
                Some(Scripted::CallFailed(rows)) => {
                    assert_eq!(rows.len(), asked, "attempt {attempt}: script/row mismatch");
                    (rows.clone(), Some(call_error()))
                }
                // Running off the end of the script means the loop attempted
                // more than the test scripted. Keep failing the same way so
                // the test still terminates.
                None => (vec![LOST; asked], Some(call_error())),
            }
        }

        fn judge(&self, index: usize, row: &Row) -> RowJudgement {
            judge_row(row.outcome, row.in_doubt, || self.idempotent[index])
        }

        async fn sleep_ms(&self, ms: u64) {
            self.elapsed
                .fetch_add(ms, std::sync::atomic::Ordering::Relaxed);
        }
    }

    fn drive(env: &ScriptedAttempts, max_retries: u32, timeout_ms: u64) -> BatchWriteOutcome<Row> {
        futures::executor::block_on(drive_batch_write_retries(env, max_retries, timeout_ms))
    }

    #[test]
    fn test_budget_truncation_sets_the_flag_and_counts_unresolved() {
        // `retry=10` asks for 11 attempts and `total_timeout` allows one.
        let env = ScriptedAttempts::new(
            3,
            100, // one send exhausts the whole budget
            vec![Scripted::Rows(vec![
                OK,
                refused(ResultCode::Timeout),
                refused(ResultCode::DeviceOverload),
            ])],
        );
        let outcome = drive(&env, 10, 100);

        assert!(
            outcome.stats.truncated_by_timeout,
            "the elapsed guard stopped the loop; the flag must say so"
        );
        assert_eq!(
            outcome.stats.attempts, 1,
            "only the initial send fit in the budget"
        );
        assert_eq!(outcome.stats.max_attempts, 11, "retry=10 asked for 11");
        assert_eq!(
            outcome.stats.unresolved, 2,
            "two records still carry a retryable code"
        );
        assert_eq!(outcome.rows.len(), 3);
        assert!(
            outcome.error.is_none(),
            "every record was answered by a server"
        );
    }

    #[test]
    fn test_unresolved_counts_only_retryable_failures() {
        // A permanent failure is not something more retries would fix, so it must
        // not inflate `unresolved` — otherwise a caller reads it as "retry budget
        // would have saved these".
        let env = ScriptedAttempts::new(
            3,
            100,
            vec![Scripted::Rows(vec![
                OK,
                refused(ResultCode::KeyExistsError), // permanent
                refused(ResultCode::Timeout),        // retryable
            ])],
        );
        let outcome = drive(&env, 5, 100);

        assert_eq!(outcome.stats.unresolved, 1);
        assert!(outcome.stats.truncated_by_timeout);
    }

    #[test]
    fn test_no_truncation_when_the_budget_is_ample() {
        // Retry succeeds inside the budget: both observables stay at their
        // defaults, so a passing truncation test cannot be passing by accident.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::Rows(vec![OK, refused(ResultCode::Timeout)]),
                Scripted::Rows(vec![OK]),
            ],
        );
        let outcome = drive(&env, 5, 60_000);

        assert!(!outcome.stats.truncated_by_timeout);
        assert_eq!(outcome.stats.unresolved, 0);
        assert_eq!(outcome.stats.attempts, 2);
        assert_eq!(outcome.rows, vec![OK, OK], "retry merged in");
        assert!(
            outcome.in_doubt_rows.is_empty(),
            "a success settles the doubt"
        );
    }

    #[test]
    fn test_only_the_retryable_subset_is_resent() {
        let env = ScriptedAttempts::new(
            3,
            1,
            vec![
                Scripted::Rows(vec![OK, refused(ResultCode::Timeout), OK]),
                Scripted::Rows(vec![OK]),
            ],
        );
        drive(&env, 5, 60_000);

        assert_eq!(
            env.sends(),
            vec![None, Some(vec![1])],
            "the first attempt sends everything; the retry sends only index 1"
        );
    }

    #[test]
    fn test_every_attempt_failing_as_a_whole_reports_the_failure_with_its_rows() {
        let env = ScriptedAttempts::new(2, 1, vec![Scripted::CallFailed(vec![LOST, LOST])]);
        let outcome = drive(&env, 3, 60_000);

        assert_eq!(
            env.sends(),
            vec![None, Some(vec![0, 1]), Some(vec![0, 1]), Some(vec![0, 1])],
            "the full retry budget was spent, and every attempt re-sent both \
             records: an attempt that re-sends an empty subset would write \
             nothing and look like progress"
        );
        let err = outcome.error.expect("no record was ever answered");
        assert!(err.to_string().contains("scripted call failure"));
        assert_eq!(
            outcome.rows,
            vec![LOST, LOST],
            "the rows are reported, not dropped"
        );
        assert_eq!(outcome.stats.attempts, 4);
        assert_eq!(outcome.stats.unresolved, 2);
    }

    #[test]
    fn test_a_failed_first_attempt_is_made_up_for_by_the_retry() {
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::CallFailed(vec![LOST, LOST]),
                Scripted::Rows(vec![OK, OK]),
            ],
        );
        let outcome = drive(&env, 3, 60_000);

        assert_eq!(env.sends(), vec![None, Some(vec![0, 1])]);
        assert_eq!(outcome.rows, vec![OK, OK]);
        assert!(
            outcome.error.is_none(),
            "every record was written in the end; the earlier failure is history"
        );
        assert_eq!(
            outcome.stats.attempts, 2,
            "the failed call consumed one attempt"
        );
        assert_eq!(outcome.stats.unresolved, 0);
        assert!(!outcome.stats.truncated_by_timeout);
    }

    #[test]
    fn test_a_record_that_already_succeeded_is_never_sent_again() {
        // One node answered, the other did not. Rust client 2.x reported only
        // "the call failed", so the whole batch had to be sent again.
        let env = ScriptedAttempts::new(
            3,
            1,
            vec![
                Scripted::CallFailed(vec![OK, LOST, OK]),
                Scripted::Rows(vec![OK]),
            ],
        );
        let outcome = drive(&env, 3, 60_000);

        assert_eq!(
            env.sends(),
            vec![None, Some(vec![1])],
            "only the record without an answer is re-sent"
        );
        assert_eq!(outcome.rows, vec![OK, OK, OK]);
        assert!(outcome.error.is_none());
    }

    #[test]
    fn test_a_later_call_failure_keeps_the_results_already_received() {
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::Rows(vec![OK, refused(ResultCode::DeviceOverload)]),
                Scripted::CallFailed(vec![LOST]),
            ],
        );
        let outcome = drive(&env, 1, 60_000);

        assert_eq!(
            outcome.rows,
            vec![OK, LOST],
            "the first record stays written"
        );
        assert!(
            outcome.error.is_some(),
            "the second record has no answer, so the call reports the failure"
        );
        assert_eq!(outcome.stats.attempts, 2);
        assert_eq!(outcome.stats.unresolved, 1);
        assert!(
            !outcome.stats.truncated_by_timeout,
            "attempts ran out, not the clock"
        );
    }

    #[test]
    fn test_a_conditional_write_in_doubt_stops_the_loop_for_that_record() {
        // Record 0 is a plain put, record 1 is CREATE_ONLY. Both lost their
        // answer. Only the plain put may be sent again.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::CallFailed(vec![LOST, LOST]),
                Scripted::Rows(vec![OK]),
            ],
        )
        .conditional(&[1]);
        let outcome = drive(&env, 5, 60_000);

        assert_eq!(env.sends(), vec![None, Some(vec![0])]);
        assert_eq!(outcome.rows, vec![OK, LOST]);
        assert!(
            outcome.error.is_some(),
            "the conditional write is still unanswered; the caller must be told"
        );
        assert_eq!(
            outcome.stats.unresolved, 0,
            "more attempts would not have been made for it"
        );
        assert!(
            outcome.in_doubt_rows.is_empty(),
            "the row says in_doubt itself"
        );
    }

    #[test]
    fn test_a_conditional_write_the_server_refused_is_sent_again() {
        let env = ScriptedAttempts::new(
            1,
            1,
            vec![
                Scripted::Rows(vec![refused(ResultCode::DeviceOverload)]),
                Scripted::Rows(vec![OK]),
            ],
        )
        .conditional(&[0]);
        let outcome = drive(&env, 5, 60_000);

        assert_eq!(env.sends(), vec![None, Some(vec![0])]);
        assert_eq!(outcome.rows, vec![OK]);
    }

    #[test]
    fn test_doubt_from_an_earlier_attempt_outlives_a_later_clean_failure() {
        // Attempt 0 was sent and lost: the write may be in. Attempt 1 never
        // left the client, which by itself is not in doubt — but the record
        // still is.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::CallFailed(vec![LOST, OK]),
                Scripted::CallFailed(vec![UNSENT]),
            ],
        );
        let outcome = drive(&env, 1, 60_000);

        assert_eq!(outcome.rows, vec![UNSENT, OK]);
        assert_eq!(outcome.in_doubt_rows, vec![0]);
        assert!(outcome.error.is_some());
    }

    #[test]
    fn test_doubt_also_outlives_a_later_refusal_by_the_server() {
        let env = ScriptedAttempts::new(
            1,
            1,
            vec![
                Scripted::CallFailed(vec![LOST]),
                Scripted::Rows(vec![refused(ResultCode::RecordTooBig)]),
            ],
        );
        let outcome = drive(&env, 3, 60_000);

        assert_eq!(outcome.rows, vec![refused(ResultCode::RecordTooBig)]);
        assert_eq!(
            outcome.in_doubt_rows,
            vec![0],
            "the refusal does not say what the first send did"
        );
        assert!(
            outcome.error.is_none(),
            "a server answered for every record in the end"
        );
    }

    #[test]
    fn test_single_attempt_stats_describe_a_non_retrying_call() {
        let stats = BatchWriteRetryStats::SINGLE_ATTEMPT;
        assert_eq!(stats.attempts, 1);
        assert_eq!(stats.max_attempts, 1);
        assert!(!stats.truncated_by_timeout);
        assert_eq!(stats.unresolved, 0);
    }
}
