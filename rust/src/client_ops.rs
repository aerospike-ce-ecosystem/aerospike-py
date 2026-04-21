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
    self, BatchOperateArgs, BatchReadArgs, BatchRemoveArgs, ExistsArgs, GetArgs, IndexCreateArgs,
    IndexRemoveArgs, InfoArgs, OperateArgs, PutArgs, PutPolicy, RemoveArgs, RemoveBinArgs,
    SelectArgs, SingleBinWriteArgs, TouchArgs, TruncateArgs, UdfPutArgs, UdfRemoveArgs,
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
        return Err(crate::errors::RecordNotFound::new_err(
            "AEROSPIKE_ERR (2): Record not found",
        ));
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
/// - If a transport-level error occurs during a retry attempt, retries stop
///   immediately and the function returns partial results. Records that were
///   being retried retain their previous (failed) result codes.
/// - The elapsed time guard prevents retries when `elapsed + backoff >= total_timeout`,
///   but does not account for the actual batch operation time. Total wall-clock
///   time may exceed `total_timeout` by up to one additional timeout window.
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
) -> PyResult<Vec<BatchRecord>> {
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
        return traced_op!(
            op_name,
            ns,
            set,
            parent_ctx,
            conn_info,
            client.batch(batch_policy, &batch_ops).await
        );
    }

    // Retry path: pre-build ops once per record, reuse via clone on retry
    let cached_ops: Vec<Vec<aerospike_core::operations::Operation>> = records
        .iter()
        .map(|(_, bins, _)| bins.iter().map(aerospike_core::operations::put).collect())
        .collect();

    let batch_ops: Vec<BatchOperation> = records
        .iter()
        .zip(cached_ops.iter())
        .map(|((key, _, write_policy), ops)| {
            BatchOperation::write(write_policy, key.clone(), ops.clone())
        })
        .collect();

    // First attempt
    let mut results: Vec<BatchRecord> = traced_op!(
        op_name,
        ns,
        set,
        parent_ctx,
        conn_info,
        client.batch(batch_policy, &batch_ops).await
    )?;

    // Retry loop: only retry records with retryable error codes
    let start = std::time::Instant::now();
    let timeout_ms = batch_policy.base_policy.total_timeout as u64;
    let mut retry_indices: Vec<usize> = Vec::new();
    for attempt in 0..max_retries {
        // Find indices of failed records that are retryable
        collect_retryable_indices(&results, &mut retry_indices);

        if retry_indices.is_empty() {
            log::debug!(
                "batch_write retry: all records succeeded after {} attempt(s)",
                attempt + 1
            );
            break;
        }

        // Full Jitter backoff: random_between(0, min(500ms, 10ms * 2^attempt))
        let backoff_ms = compute_backoff_ms(attempt, 10, 500);

        // Elapsed time guard: stop retries if remaining time is insufficient
        if timeout_ms > 0 {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            if elapsed_ms + backoff_ms >= timeout_ms {
                log::warn!(
                    "batch_write retry: elapsed {}ms + backoff {}ms >= timeout {}ms, stopping",
                    elapsed_ms,
                    backoff_ms,
                    timeout_ms
                );
                break;
            }
        }

        log::info!(
            "batch_write retry: {} failed records, attempt {}/{}, backoff {}ms",
            retry_indices.len(),
            attempt + 1,
            max_retries,
            backoff_ms
        );
        tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;

        // Build retry batch from cached ops (avoids rebuilding from bins)
        let retry_ops: Vec<BatchOperation> = retry_indices
            .iter()
            .map(|&i| {
                let (key, _, write_policy) = &records[i];
                BatchOperation::write(write_policy, key.clone(), cached_ops[i].clone())
            })
            .collect();

        let retry_op_name = format!("{}_retry", op_name);
        let retry_results: Vec<BatchRecord> = match traced_op!(
            &retry_op_name,
            ns,
            set,
            parent_ctx,
            conn_info,
            client.batch(batch_policy, &retry_ops).await
        ) {
            Ok(r) => r,
            Err(e) => {
                log::warn!(
                    "batch_write retry transport error on attempt {}/{}: {}",
                    attempt + 1,
                    max_retries,
                    e
                );
                break; // Return partial results instead of propagating error
            }
        };

        // Merge retry results back into the main results vector
        if retry_results.len() != retry_indices.len() {
            log::warn!(
                "batch_write retry: expected {} results, got {} (partial batch response)",
                retry_indices.len(),
                retry_results.len()
            );
        }
        for (original_idx, retry_record) in
            retry_indices.iter().copied().zip(retry_results.into_iter())
        {
            results[original_idx] = retry_record;
        }
    }

    Ok(results)
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

        let mirror = BatchRecordMirror {
            key: aerospike_core::Key::new("test", "demo", Value::from("k1".to_string())).unwrap(),
            record: None,
            result_code,
            in_doubt: false,
            has_write: false,
        };
        // SAFETY: `BatchRecordMirror` has the identical field types and order
        // as `BatchRecord`. This is only used in unit tests.
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
