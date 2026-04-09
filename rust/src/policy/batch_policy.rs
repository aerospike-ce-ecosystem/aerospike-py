//! Batch policy parsing from Python dicts.

use aerospike_core::{BatchPolicy, BatchWritePolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::write_policy::parse_ttl;
use super::{extract_filter_expression, extract_policy_fields};

/// Parse a Python policy dict into a BatchPolicy
pub fn parse_batch_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<BatchPolicy> {
    trace!("Parsing batch policy");
    let mut policy = BatchPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "allow_inline" => policy.allow_inline;
        "allow_inline_ssd" => policy.allow_inline_ssd;
        "respond_all_keys" => policy.respond_all_keys
    });

    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Parse a Python policy/meta dict into a [`BatchWritePolicy`] with TTL support.
///
/// `policy_dict` provides the batch-level default TTL; `meta` (per-record)
/// overrides it. Note: this is the **inverse** of
/// [`parse_write_policy()`](super::write_policy::parse_write_policy), where
/// `policy_dict` takes precedence over `meta`.
pub fn parse_batch_write_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
    meta: Option<&Bound<'_, PyDict>>,
) -> PyResult<BatchWritePolicy> {
    trace!("Parsing batch write policy");
    let mut policy = BatchWritePolicy::default();

    // Apply batch-level policy dict first (default for all records)
    if let Some(dict) = policy_dict {
        if let Some(val) = dict.get_item("ttl")? {
            policy.expiration = parse_ttl(val.extract::<i64>()?)?;
        }
    }

    // Apply per-record meta — overrides batch-level TTL
    if let Some(meta_dict) = meta {
        if let Some(ttl) = meta_dict.get_item("ttl")? {
            policy.expiration = parse_ttl(ttl.extract::<i64>()?)?;
        }
    }

    Ok(policy)
}
