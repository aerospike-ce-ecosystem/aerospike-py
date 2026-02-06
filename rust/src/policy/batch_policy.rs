use aerospike_core::BatchPolicy;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::expressions::{is_expression, py_to_expression};

/// Parse a Python policy dict into a BatchPolicy
pub fn parse_batch_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<BatchPolicy> {
    let mut policy = BatchPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    // Socket timeout
    if let Some(val) = dict.get_item("socket_timeout")? {
        policy.base_policy.socket_timeout = val.extract::<u32>()?;
    }

    // Total timeout
    if let Some(val) = dict.get_item("total_timeout")? {
        policy.base_policy.total_timeout = val.extract::<u32>()?;
    }

    // Max retries
    if let Some(val) = dict.get_item("max_retries")? {
        policy.base_policy.max_retries = val.extract::<usize>()?;
    }

    // Allow inline
    if let Some(val) = dict.get_item("allow_inline")? {
        policy.allow_inline = val.extract::<bool>()?;
    }

    // Allow inline SSD
    if let Some(val) = dict.get_item("allow_inline_ssd")? {
        policy.allow_inline_ssd = val.extract::<bool>()?;
    }

    // Respond all keys
    if let Some(val) = dict.get_item("respond_all_keys")? {
        policy.respond_all_keys = val.extract::<bool>()?;
    }

    // Filter expression
    if let Some(val) = dict.get_item("filter_expression")? {
        if is_expression(&val) {
            policy.filter_expression = Some(py_to_expression(&val)?);
        }
    }

    Ok(policy)
}
