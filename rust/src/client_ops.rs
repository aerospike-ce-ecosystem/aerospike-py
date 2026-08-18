//! Shared async business logic for both `PyClient` (sync) and `PyAsyncClient` (async).
//!
//! Each `do_*` function is an `async fn` that takes the Aerospike client and
//! pre-parsed arguments, performs the database operation with tracing/metrics,
//! and returns Rust-native types. No PyO3/Python types are involved in the
//! return values — Python conversion is the caller's responsibility.

use std::sync::Arc;

use aerospike_core::{
    BatchOperation, BatchRecord, BatchWritePolicy, Bins, Client as AsClient, Error as AsError,
    Record, Task, Value,
};

use pyo3::PyResult;

use crate::client_common::{
    self, BatchApplyArgs, BatchOperateArgs, BatchReadArgs, BatchRemoveArgs, ExistsArgs, GetArgs,
    IndexCreateArgs, IndexRemoveArgs, InfoArgs, OperateArgs, PutArgs, PutPolicy, RemoveArgs,
    RemoveBinArgs, SelectArgs, SingleBinWriteArgs, TouchArgs, TruncateArgs, UdfPutArgs,
    UdfRemoveArgs,
};
use crate::errors::as_to_pyerr;
use crate::policy::write_policy::DEFAULT_WRITE_POLICY;
use crate::traced_exists_op;
use crate::traced_op;

// ── CRUD ────────────────────────────────────────────────────────────────────

/// Write a record to the cluster.
pub async fn do_put(client: &AsClient, args: PutArgs) -> PyResult<()> {
    match args.policy {
        PutPolicy::Default => {
            let wp = &*DEFAULT_WRITE_POLICY;
            traced_op!(
                "put",
                &args.key.namespace,
                &args.key.set_name,
                args.otel.parent_ctx,
                args.otel.conn_info,
                client.put(wp, &args.key, &args.bins).await
            )
        }
        PutPolicy::Custom(ref wp) => {
            traced_op!(
                "put",
                &args.key.namespace,
                &args.key.set_name,
                args.otel.parent_ctx,
                args.otel.conn_info,
                client.put(wp, &args.key, &args.bins).await
            )
        }
    }
}

/// Read all bins of a record.
pub async fn do_get(client: &AsClient, args: &GetArgs) -> PyResult<Record> {
    let rp = args.read_policy();
    traced_op!(
        "get",
        &args.key.namespace,
        &args.key.set_name,
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
        &args.key.namespace,
        &args.key.set_name,
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
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.get(&args.read_policy, &args.key, Bins::None).await
    )
}

/// Delete a record. Returns `PyErr(RecordNotFound)` if the record did not exist.
pub async fn do_remove(client: &AsClient, args: RemoveArgs) -> PyResult<()> {
    let existed = traced_op!(
        "delete",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.delete(&args.write_policy, &args.key).await
    )?;

    if !existed {
        // The server reported KEY_NOT_FOUND_ERROR (wire code 2); aerospike-core
        // collapsed it into `Ok(false)`, so the exception is built here — with
        // the real wire code attached (ADR-0027), not the -1 sentinel.
        return Err(crate::errors::record_not_found_for_delete());
    }
    Ok(())
}

/// Reset a record's TTL.
pub async fn do_touch(client: &AsClient, args: TouchArgs) -> PyResult<()> {
    traced_op!(
        "touch",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.touch(&args.write_policy, &args.key).await
    )
}

/// Append string values to bins.
pub async fn do_append(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    traced_op!(
        "append",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        {
            client
                .append(&args.write_policy, &args.key, &args.bins)
                .await
        }
    )
}

/// Prepend string values to bins.
pub async fn do_prepend(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    traced_op!(
        "prepend",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        {
            client
                .prepend(&args.write_policy, &args.key, &args.bins)
                .await
        }
    )
}

/// Increment/add to numeric bins.
pub async fn do_increment(client: &AsClient, args: SingleBinWriteArgs) -> PyResult<()> {
    traced_op!(
        "increment",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.add(&args.write_policy, &args.key, &args.bins).await
    )
}

/// Remove bins from a record by setting them to nil.
pub async fn do_remove_bin(client: &AsClient, args: RemoveBinArgs) -> PyResult<()> {
    traced_op!(
        "remove_bin",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.put(&args.write_policy, &args.key, &args.bins).await
    )
}

// ── Multi-operation ─────────────────────────────────────────────────────────

/// Perform multiple operations on a single record.
pub async fn do_operate(client: &AsClient, args: &OperateArgs) -> PyResult<Record> {
    traced_op!(
        "operate",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        {
            client
                .operate(&args.write_policy, &args.key, &args.ops)
                .await
        }
    )
}

/// Perform multiple operations on a single record (ordered variant).
/// Uses the same underlying client.operate() call but different tracing name.
pub async fn do_operate_ordered(client: &AsClient, args: &OperateArgs) -> PyResult<Record> {
    traced_op!(
        "operate_ordered",
        &args.key.namespace,
        &args.key.set_name,
        args.otel.parent_ctx,
        args.otel.conn_info,
        {
            client
                .operate(&args.write_policy, &args.key, &args.ops)
                .await
        }
    )
}

// ── Batch ───────────────────────────────────────────────────────────────────

/// Read multiple records in a batch.
pub async fn do_batch_read(client: &AsClient, args: &BatchReadArgs) -> PyResult<Vec<BatchRecord>> {
    let ops = args.to_batch_ops();
    traced_op!(
        "batch_read",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.batch(&args.batch_policy, &ops).await
    )
}

/// Perform operations on multiple records in a batch.
pub async fn do_batch_operate(
    client: &AsClient,
    args: &BatchOperateArgs,
) -> PyResult<Vec<BatchRecord>> {
    let batch_ops = args.to_batch_ops();
    traced_op!(
        "batch_operate",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.batch(&args.batch_policy, &batch_ops).await
    )
}

/// Remove multiple records in a batch.
pub async fn do_batch_remove(
    client: &AsClient,
    args: &BatchRemoveArgs,
) -> PyResult<Vec<BatchRecord>> {
    let ops = args.to_batch_ops();
    traced_op!(
        "batch_remove",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.batch(&args.batch_policy, &ops).await
    )
}

/// Execute a UDF on multiple records in a batch.
pub async fn do_batch_apply(
    client: &AsClient,
    args: &BatchApplyArgs,
) -> PyResult<Vec<BatchRecord>> {
    let ops = args.to_batch_ops();
    traced_op!(
        "batch_apply",
        &args.batch_ns,
        &args.batch_set,
        args.otel.parent_ctx,
        args.otel.conn_info,
        client.batch(&args.batch_policy, &ops).await
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
    /// Records still carrying a retryable failure code when the loop ended.
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

/// Collect indices of batch records with retryable error codes into `out`.
///
/// Clears `out` first, then appends indices of records whose `result_code`
/// is both non-Ok and retryable (timeout, device overload, key busy,
/// server memory error, partition unavailable).
fn collect_retryable_indices(results: &[BatchRecord], out: &mut Vec<usize>) {
    out.clear();
    out.extend(results.iter().enumerate().filter_map(|(i, br)| {
        if let Some(rc) = &br.result_code {
            if *rc != aerospike_core::ResultCode::Ok && is_retryable_result_code(rc) {
                return Some(i);
            }
        }
        None
    }));
}

/// Write multiple records from pre-parsed (key, bins) pairs with optional retry.
///
/// When `max_retries > 0`, failed records with retryable error codes are
/// re-submitted in subsequent batch calls, up to `max_retries` attempts.
/// A Full Jitter exponential backoff (`random_between(0, min(cap, base * 2^attempt))`)
/// is applied between retries to avoid thundering-herd effects.
///
/// **Retry behavior notes:**
/// - Transport-level errors consume retry budget rather than ending the call.
///   This covers the initial send too: a connection reset or an unreachable node
///   on the first attempt re-drives the whole batch instead of propagating
///   immediately. Re-driving is safe because every operation is a pure `put`,
///   an idempotent full-bin overwrite.
/// - If *every* attempt fails at the transport level there are no per-record
///   results to report, so the last transport error propagates. Once any attempt
///   has returned a batch response, later transport errors leave those results
///   intact and the call still returns `Ok`.
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
/// - Callers should always check per-record `result_code` values regardless of
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
) -> PyResult<(Vec<BatchRecord>, BatchWriteRetryStats)> {
    // Fast path: no retry — build ops directly, no cache overhead
    if max_retries == 0 {
        let batch_ops: Vec<BatchOperation> = records
            .iter()
            .map(|(key, bins, write_policy)| {
                let ops: Vec<aerospike_core::operations::Operation> =
                    bins.iter().map(aerospike_core::operations::put).collect();
                BatchOperation::write(write_policy, key.clone(), ops)
            })
            .collect();
        let results = traced_op!(
            op_name,
            ns,
            set,
            parent_ctx,
            conn_info,
            client.batch(batch_policy, &batch_ops).await
        )?;
        return Ok((results, BatchWriteRetryStats::SINGLE_ATTEMPT));
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
        parent_ctx,
        conn_info,
        op_name,
        retry_op_name: format!("{}_retry", op_name),
        start: std::time::Instant::now(),
    };
    drive_batch_write_retries(&env, max_retries, timeout_ms).await
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
/// Generic, not boxed: each call monomorphises into the code the loop had
/// inline, and the `max_retries == 0` fast path never reaches here at all.
trait BatchWriteAttempts {
    /// Milliseconds since the call began.
    fn elapsed_ms(&self) -> u64;

    /// How many records the full batch holds, for logging.
    fn record_count(&self) -> usize;

    /// Send one attempt. `indices` is `None` for the whole batch, `Some` for the
    /// subset still worth re-driving.
    fn send(
        &self,
        indices: Option<&[usize]>,
        attempt: u32,
    ) -> impl std::future::Future<Output = PyResult<Vec<BatchRecord>>> + Send;

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
    parent_ctx: client_common::ParentContext,
    conn_info: Arc<crate::tracing::ConnectionInfo>,
    op_name: &'a str,
    retry_op_name: String,
    start: std::time::Instant,
}

impl BatchWriteAttempts for ClusterAttempts<'_> {
    fn elapsed_ms(&self) -> u64 {
        self.start.elapsed().as_millis() as u64
    }

    fn record_count(&self) -> usize {
        self.records.len()
    }

    async fn send(&self, indices: Option<&[usize]>, attempt: u32) -> PyResult<Vec<BatchRecord>> {
        // Build this attempt from cached ops (avoids rebuilding from bins).
        // Without a response yet, re-send everything; otherwise only the records
        // whose result codes are worth re-driving.
        let attempt_ops: Vec<BatchOperation> = match indices {
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

        let attempt_op_name: &str = if attempt == 0 {
            self.op_name
        } else {
            &self.retry_op_name
        };
        traced_op!(
            attempt_op_name,
            self.ns,
            self.set,
            self.parent_ctx,
            self.conn_info,
            self.client.batch(self.batch_policy, &attempt_ops).await
        )
    }

    async fn sleep_ms(&self, ms: u64) {
        tokio::time::sleep(std::time::Duration::from_millis(ms)).await;
    }
}

/// Drive the attempt/retry loop. See [`do_batch_write`] for the semantics.
async fn drive_batch_write_retries<E: BatchWriteAttempts + Sync>(
    env: &E,
    max_retries: u32,
    timeout_ms: u64,
) -> PyResult<(Vec<BatchRecord>, BatchWriteRetryStats)> {
    let mut results: Vec<BatchRecord> = Vec::new();
    let mut retry_indices: Vec<usize> = Vec::new();
    // False until some attempt returns a batch response. While it is false there
    // is nothing to merge into, so the next attempt re-sends the whole batch.
    let mut responded = false;
    let mut last_transport_error: Option<pyo3::PyErr> = None;
    let mut attempts_made: u32 = 0;
    let mut truncated_by_timeout = false;

    // Attempt 0 is the initial send; attempts 1..=max_retries are the retries
    // that `retry=N` buys. Keeping the initial send inside the loop is what lets
    // a transport error on it consume retry budget instead of propagating —
    // previously that single case, the most common transient batch failure,
    // was the one thing `retry=` did nothing for.
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
                    max_retries + 1
                );
                truncated_by_timeout = true;
                break;
            }

            log::info!(
                "batch_write retry: {} record(s) to re-send, attempt {}/{}, backoff {}ms",
                if responded {
                    retry_indices.len()
                } else {
                    env.record_count()
                },
                attempt,
                max_retries,
                backoff_ms
            );
            env.sleep_ms(backoff_ms).await;
        }

        attempts_made += 1;
        let attempt_results: Vec<BatchRecord> = match env
            .send(
                if responded {
                    Some(&retry_indices)
                } else {
                    None
                },
                attempt,
            )
            .await
        {
            Ok(r) => r,
            Err(e) => {
                log::warn!(
                    "batch_write transport error on attempt {}/{}: {}",
                    attempt,
                    max_retries,
                    e
                );
                last_transport_error = Some(e);
                // Consume retry budget instead of abandoning the batch.
                continue;
            }
        };

        if responded {
            // Merge retry results back into the main results vector
            if attempt_results.len() != retry_indices.len() {
                log::warn!(
                    "batch_write retry: expected {} results, got {} (partial batch response)",
                    retry_indices.len(),
                    attempt_results.len()
                );
            }
            let update_count = attempt_results.len().min(retry_indices.len());
            for (original_idx, retry_record) in retry_indices[..update_count]
                .iter()
                .copied()
                .zip(attempt_results)
            {
                results[original_idx] = retry_record;
            }
        } else {
            results = attempt_results;
            responded = true;
        }
        last_transport_error = None;

        // Find indices of failed records that are retryable
        collect_retryable_indices(&results, &mut retry_indices);
        if retry_indices.is_empty() {
            log::debug!(
                "batch_write: all records succeeded after {} attempt(s)",
                attempt + 1
            );
            break;
        }
    }

    match last_transport_error {
        // Every attempt failed at the transport level, so there are no per-record
        // results to hand back. Propagate rather than returning an empty batch
        // that a caller would read as success.
        Some(e) if !responded => Err(e),
        _ => {
            // `retry_indices` already holds the records still carrying a
            // retryable code, so reporting it costs nothing extra.
            let stats = BatchWriteRetryStats {
                attempts: attempts_made,
                max_attempts: max_retries + 1,
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
            Ok((results, stats))
        }
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
    let node = client.cluster.get_random_node().map_err(as_to_pyerr)?;
    let map = node
        .info(&args.admin_policy, &[&args.command])
        .await
        .map_err(as_to_pyerr)?;
    Ok(map.get(&args.command).cloned().unwrap_or_default())
}

/// Lightweight health check: send `info("build")` to a random node.
/// Returns `true` if the node responds, `false` otherwise.
pub async fn do_ping(client: &AsClient) -> bool {
    let node = match client.cluster.get_random_node() {
        Ok(n) => n,
        Err(_) => return false,
    };
    let policy = aerospike_core::AdminPolicy::default();
    node.info(&policy, &["build"]).await.is_ok()
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
    client
        .execute_udf(
            &args.write_policy,
            &args.key,
            &args.module,
            &args.function,
            args.args.as_deref(),
        )
        .await
        .map_err(as_to_pyerr)
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

    // ── drive_batch_write_retries: the loop's own control flow ─────────────
    //
    // `truncated_by_timeout` and `unresolved` are the two observables this
    // change exists to add, and neither is reachable from an integration test
    // against a healthy server: forcing per-record retryable codes with a tiny
    // `socket_timeout` succeeded in 1 run out of 10 (measured), which is a flake
    // rather than a test. A scripted `BatchWriteAttempts` makes them exact.

    /// What a scripted attempt returns.
    enum Scripted {
        /// Per-record result codes, in the order the attempt requested them.
        Codes(Vec<Option<ResultCode>>),
        /// The whole attempt failed below the batch layer.
        Transport,
    }

    /// A `BatchWriteAttempts` with a canned response per attempt and a clock the
    /// test drives, so the elapsed-time guard fires exactly when intended.
    struct ScriptedAttempts {
        responses: Vec<Scripted>,
        record_count: usize,
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
                record_count,
                step_ms,
                elapsed: std::sync::atomic::AtomicU64::new(0),
                sent: std::sync::Mutex::new(Vec::new()),
            }
        }

        fn sends(&self) -> Vec<Option<Vec<usize>>> {
            self.sent.lock().unwrap().clone()
        }
    }

    impl BatchWriteAttempts for ScriptedAttempts {
        fn elapsed_ms(&self) -> u64 {
            self.elapsed.load(std::sync::atomic::Ordering::Relaxed)
        }

        fn record_count(&self) -> usize {
            self.record_count
        }

        async fn send(
            &self,
            indices: Option<&[usize]>,
            attempt: u32,
        ) -> PyResult<Vec<BatchRecord>> {
            self.sent
                .lock()
                .unwrap()
                .push(indices.map(<[usize]>::to_vec));
            self.elapsed
                .fetch_add(self.step_ms, std::sync::atomic::Ordering::Relaxed);
            match self.responses.get(attempt as usize) {
                Some(Scripted::Codes(codes)) => {
                    Ok(codes.iter().map(|c| make_batch_record(*c)).collect())
                }
                // Running off the end of the script means the loop attempted more
                // than the test scripted; treat it as a transport failure so the
                // test still terminates.
                _ => Err(crate::errors::ClientError::new_err(
                    "scripted transport error",
                )),
            }
        }

        async fn sleep_ms(&self, ms: u64) {
            self.elapsed
                .fetch_add(ms, std::sync::atomic::Ordering::Relaxed);
        }
    }

    fn drive(
        env: &ScriptedAttempts,
        max_retries: u32,
        timeout_ms: u64,
    ) -> PyResult<(Vec<BatchRecord>, BatchWriteRetryStats)> {
        futures::executor::block_on(drive_batch_write_retries(env, max_retries, timeout_ms))
    }

    #[test]
    fn test_budget_truncation_sets_the_flag_and_counts_unresolved() {
        // The reported failure: `retry=10` asks for 11 attempts, `total_timeout`
        // allows one, and before this change nothing said so.
        let env = ScriptedAttempts::new(
            3,
            100, // one send exhausts the whole budget
            vec![Scripted::Codes(vec![
                Some(ResultCode::Ok),
                Some(ResultCode::Timeout),
                Some(ResultCode::DeviceOverload),
            ])],
        );
        let (results, stats) = drive(&env, 10, 100).unwrap();

        assert!(
            stats.truncated_by_timeout,
            "the elapsed guard stopped the loop; the flag must say so"
        );
        assert_eq!(stats.attempts, 1, "only the initial send fit in the budget");
        assert_eq!(stats.max_attempts, 11, "retry=10 asked for 11");
        assert_eq!(
            stats.unresolved, 2,
            "two records still carry a retryable code"
        );
        assert_eq!(results.len(), 3);
    }

    #[test]
    fn test_unresolved_counts_only_retryable_failures() {
        // A permanent failure is not something more retries would fix, so it must
        // not inflate `unresolved` — otherwise a caller reads it as "retry budget
        // would have saved these".
        let env = ScriptedAttempts::new(
            3,
            100,
            vec![Scripted::Codes(vec![
                Some(ResultCode::Ok),
                Some(ResultCode::KeyExistsError), // permanent
                Some(ResultCode::Timeout),        // retryable
            ])],
        );
        let (_, stats) = drive(&env, 5, 100).unwrap();

        assert_eq!(stats.unresolved, 1);
        assert!(stats.truncated_by_timeout);
    }

    #[test]
    fn test_no_truncation_when_the_budget_is_ample() {
        // Retry succeeds inside the budget: both observables stay at their
        // defaults, so a passing truncation test cannot be passing by accident.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::Codes(vec![Some(ResultCode::Ok), Some(ResultCode::Timeout)]),
                Scripted::Codes(vec![Some(ResultCode::Ok)]),
            ],
        );
        let (results, stats) = drive(&env, 5, 60_000).unwrap();

        assert!(!stats.truncated_by_timeout);
        assert_eq!(stats.unresolved, 0);
        assert_eq!(stats.attempts, 2);
        assert_eq!(results.len(), 2);
        assert_eq!(
            results[1].result_code,
            Some(ResultCode::Ok),
            "retry merged in"
        );
    }

    #[test]
    fn test_only_the_retryable_subset_is_resent() {
        let env = ScriptedAttempts::new(
            3,
            1,
            vec![
                Scripted::Codes(vec![
                    Some(ResultCode::Ok),
                    Some(ResultCode::Timeout),
                    Some(ResultCode::Ok),
                ]),
                Scripted::Codes(vec![Some(ResultCode::Ok)]),
            ],
        );
        drive(&env, 5, 60_000).unwrap();

        assert_eq!(
            env.sends(),
            vec![None, Some(vec![1])],
            "the first attempt sends everything; the retry sends only index 1"
        );
    }

    #[test]
    fn test_every_attempt_failing_at_transport_propagates() {
        // Nothing ever responded, so there are no per-record results to hand back
        // and an empty Ok would read as success.
        let env = ScriptedAttempts::new(2, 1, vec![Scripted::Transport]);
        let err = drive(&env, 3, 60_000).unwrap_err();

        assert_eq!(
            env.sends(),
            vec![None, None, None, None],
            "the full retry budget was spent, and since nothing ever responded \
             every attempt must re-send the WHOLE batch — asserting only the \
             count here let an empty-subset re-send pass"
        );
        assert!(err.to_string().contains("scripted transport error"));
    }

    #[test]
    fn test_a_first_attempt_transport_error_resends_the_whole_batch() {
        // This is the case #424 was filed for, and the one no test pinned.
        //
        // Attempt 0 dies below the batch layer, so nothing responded and there is
        // no per-record result to merge into. `responded` must therefore still be
        // false on attempt 1, which makes it send `None` — the whole batch —
        // rather than the (empty) retry subset.
        //
        // Without this assertion, replacing the `if responded { .. } else { None }`
        // selector with a bare `Some(&retry_indices)` is invisible: the scripted
        // env answers with its canned codes whatever it is asked for, so results,
        // stats and attempt counts are all unchanged. Against a real server that
        // mutation sends an EMPTY batch, writes nothing, and returns Ok — a silent
        // data loss that reads as success. `sends()` is the only observable that
        // distinguishes them.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::Transport,
                Scripted::Codes(vec![Some(ResultCode::Ok), Some(ResultCode::Ok)]),
            ],
        );
        let (results, stats) = drive(&env, 3, 60_000).unwrap();

        assert_eq!(
            env.sends(),
            vec![None, None],
            "attempt 0 never responded, so attempt 1 must re-send the whole batch"
        );
        assert_eq!(results.len(), 2, "both records came back on the retry");
        assert_eq!(
            stats.attempts, 2,
            "the transport failure consumed one attempt"
        );
        assert_eq!(stats.unresolved, 0);
        assert!(!stats.truncated_by_timeout);
    }

    #[test]
    fn test_a_later_transport_error_keeps_the_results_already_received() {
        // Once an attempt has responded, a later transport failure must not throw
        // away what was already delivered.
        let env = ScriptedAttempts::new(
            2,
            1,
            vec![
                Scripted::Codes(vec![Some(ResultCode::Ok), Some(ResultCode::Timeout)]),
                Scripted::Transport,
            ],
        );
        let (results, stats) = drive(&env, 1, 60_000).unwrap();

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].result_code, Some(ResultCode::Ok));
        assert_eq!(stats.attempts, 2);
        assert_eq!(stats.unresolved, 1);
        assert!(
            !stats.truncated_by_timeout,
            "attempts ran out, not the clock"
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

    // ── collect_retryable_indices tests ────────────────────────────────────

    /// Create a minimal `BatchRecord` for testing.
    ///
    /// `BatchRecord::new` is `pub(crate)` in `aerospike_core`, so we build
    /// an instance by cloning a layout-compatible repr and overwriting the
    /// public `result_code` field.  The private `has_write: bool` field is
    /// irrelevant to `collect_retryable_indices`.
    fn make_batch_record(result_code: Option<ResultCode>) -> BatchRecord {
        /// Layout-compatible mirror used solely to construct test fixtures.
        #[repr(C)]
        struct BatchRecordMirror {
            key: aerospike_core::Key,
            record: Option<Record>,
            result_code: Option<ResultCode>,
            in_doubt: bool,
            has_write: bool,
        }

        // Compile-time guards: if `aerospike_core::BatchRecord`'s layout ever
        // drifts from `BatchRecordMirror`, the transmute below becomes UB.
        // These assertions turn that into a build failure instead.
        static_assertions::assert_eq_size!(BatchRecordMirror, BatchRecord);
        static_assertions::assert_eq_align!(BatchRecordMirror, BatchRecord);

        let mirror = BatchRecordMirror {
            key: aerospike_core::Key::new("test", "demo", Value::from("k1".to_string())).unwrap(),
            record: None,
            result_code,
            in_doubt: false,
            has_write: false,
        };
        // SAFETY: `BatchRecordMirror` has the identical field types and order
        // as `BatchRecord`. This is only used in unit tests. Size + alignment
        // are guarded by the `static_assertions` calls above.
        unsafe { std::mem::transmute(mirror) }
    }

    #[test]
    fn test_collect_retryable_indices_all_ok() {
        let results = vec![
            make_batch_record(Some(ResultCode::Ok)),
            make_batch_record(Some(ResultCode::Ok)),
            make_batch_record(None), // None means Ok
        ];
        let mut indices = Vec::new();
        collect_retryable_indices(&results, &mut indices);
        assert!(indices.is_empty());
    }

    #[test]
    fn test_collect_retryable_indices_retryable_only() {
        let results = vec![
            make_batch_record(Some(ResultCode::Ok)),
            make_batch_record(Some(ResultCode::Timeout)),
            make_batch_record(Some(ResultCode::Ok)),
            make_batch_record(Some(ResultCode::KeyBusy)),
        ];
        let mut indices = Vec::new();
        collect_retryable_indices(&results, &mut indices);
        assert_eq!(indices, vec![1, 3]);
    }

    #[test]
    fn test_collect_retryable_indices_non_retryable_excluded() {
        let results = vec![
            make_batch_record(Some(ResultCode::KeyExistsError)),
            make_batch_record(Some(ResultCode::RecordTooBig)),
            make_batch_record(Some(ResultCode::Timeout)),
        ];
        let mut indices = Vec::new();
        collect_retryable_indices(&results, &mut indices);
        assert_eq!(indices, vec![2]); // Only Timeout is retryable
    }

    #[test]
    fn test_collect_retryable_indices_mixed() {
        let results = vec![
            make_batch_record(Some(ResultCode::Ok)),             // ok
            make_batch_record(Some(ResultCode::Timeout)),        // retryable
            make_batch_record(Some(ResultCode::KeyExistsError)), // non-retryable
            make_batch_record(Some(ResultCode::DeviceOverload)), // retryable
            make_batch_record(None),                             // ok (None)
            make_batch_record(Some(ResultCode::ServerMemError)), // retryable
        ];
        let mut indices = Vec::new();
        collect_retryable_indices(&results, &mut indices);
        assert_eq!(indices, vec![1, 3, 5]);
    }

    #[test]
    fn test_collect_retryable_indices_clears_output() {
        let results = vec![make_batch_record(Some(ResultCode::Timeout))];
        let mut indices = vec![99, 100]; // pre-populated
        collect_retryable_indices(&results, &mut indices);
        assert_eq!(indices, vec![0]); // old values cleared
    }
}
