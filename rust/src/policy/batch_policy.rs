use aerospike_core::BatchPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::extract_policy_fields;
use crate::expressions::{is_expression, py_to_expression};

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

    if let Some(val) = dict.get_item("filter_expression")? {
        if is_expression(&val) {
            policy.filter_expression = Some(py_to_expression(&val)?);
        }
    }

    Ok(policy)
}
