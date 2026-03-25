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
/// server overloaded, or partition unavailable. Permanent errors
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

/// Write multiple records from pre-parsed (key, bins) pairs with optional retry.
///
/// When `max_retries > 0`, failed records with retryable error codes are
/// re-submitted in subsequent batch calls, up to `max_retries` attempts.
/// A short exponential backoff (10ms * 2^attempt, capped at 500ms) is applied
/// between retries to avoid thundering-herd effects.
#[allow(clippy::too_many_arguments)]
pub async fn do_batch_write(
    client: &AsClient,
    batch_policy: &aerospike_core::BatchPolicy,
    records: &[(aerospike_core::Key, Vec<aerospike_core::Bin>)],
    ns: &str,
    set: &str,
    parent_ctx: client_common::ParentContext,
    conn_info: Arc<crate::tracing::ConnectionInfo>,
    max_retries: u32,
) -> PyResult<Vec<BatchRecord>> {
    let write_policy = BatchWritePolicy::default();

    // Build initial batch operations
    let batch_ops: Vec<BatchOperation> = records
        .iter()
        .map(|(key, bins)| {
            let ops: Vec<aerospike_core::operations::Operation> =
                bins.iter().map(aerospike_core::operations::put).collect();
            BatchOperation::write(&write_policy, key.clone(), ops)
        })
        .collect();

    // First attempt
    let mut results: Vec<BatchRecord> = traced_op!(
        "batch_write_numpy",
        ns,
        set,
        parent_ctx,
        conn_info,
        { client.batch(batch_policy, &batch_ops).await }
    )?;

    if max_retries == 0 {
        return Ok(results);
    }

    // Retry loop: only retry records with retryable error codes
    for attempt in 0..max_retries {
        // Find indices of failed records that are retryable
        let retry_indices: Vec<usize> = results
            .iter()
            .enumerate()
            .filter_map(|(i, br)| {
                if let Some(rc) = &br.result_code {
                    if *rc != aerospike_core::ResultCode::Ok && is_retryable_result_code(rc) {
                        return Some(i);
                    }
                }
                None
            })
            .collect();

        if retry_indices.is_empty() {
            log::debug!(
                "batch_write retry: all records succeeded after {} attempt(s)",
                attempt + 1
            );
            break;
        }

        // Exponential backoff: 10ms, 20ms, 40ms, ..., capped at 500ms
        // Cap the shift exponent to avoid overflow panic when attempt >= 64
        let capped_attempt = std::cmp::min(attempt, 6); // 10 * 2^6 = 640 > 500
        let backoff_ms = std::cmp::min(10u64 * (1u64 << capped_attempt), 500);
        log::info!(
            "batch_write retry: {} failed records, attempt {}/{}, backoff {}ms",
            retry_indices.len(),
            attempt + 1,
            max_retries,
            backoff_ms
        );
        tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;

        // Build retry batch from failed records only
        let retry_ops: Vec<BatchOperation> = retry_indices
            .iter()
            .map(|&i| {
                let (key, bins) = &records[i];
                let ops: Vec<aerospike_core::operations::Operation> =
                    bins.iter().map(aerospike_core::operations::put).collect();
                BatchOperation::write(&write_policy, key.clone(), ops)
            })
            .collect();

        let retry_results: Vec<BatchRecord> = match traced_op!(
            "batch_write_numpy_retry",
            ns,
            set,
            parent_ctx,
            conn_info,
            { client.batch(batch_policy, &retry_ops).await }
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
        for (retry_pos, &original_idx) in retry_indices.iter().enumerate() {
            if retry_pos < retry_results.len() {
                results[original_idx] = retry_results[retry_pos].clone();
            }
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
    let node = client
        .cluster
        .get_random_node()
        .map_err(as_to_pyerr)?;
    let map = node
        .info(&args.admin_policy, &[&args.command])
        .await
        .map_err(as_to_pyerr)?;
    Ok(map.get(&args.command).cloned().unwrap_or_default())
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
}
