use aerospike_core::QueryPolicy;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::expressions::{is_expression, py_to_expression};

/// Parse a Python policy dict into a QueryPolicy
pub fn parse_query_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<QueryPolicy> {
    let mut policy = QueryPolicy::default();

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

    // Max records
    if let Some(val) = dict.get_item("max_records")? {
        policy.max_records = val.extract::<u64>()?;
    }

    // Records per second
    if let Some(val) = dict.get_item("records_per_second")? {
        policy.records_per_second = val.extract::<u32>()?;
    }

    // Max concurrent nodes
    if let Some(val) = dict.get_item("max_concurrent_nodes")? {
        policy.max_concurrent_nodes = val.extract::<usize>()?;
    }

    // Record queue size
    if let Some(val) = dict.get_item("record_queue_size")? {
        policy.record_queue_size = val.extract::<usize>()?;
    }

    // Filter expression
    if let Some(val) = dict.get_item("filter_expression")? {
        if is_expression(&val) {
            policy.base_policy.filter_expression = Some(py_to_expression(&val)?);
        }
    }

    Ok(policy)
}
