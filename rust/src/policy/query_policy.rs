//! Query/scan policy parsing from Python dicts.

use aerospike_core::QueryPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{extract_filter_expression, extract_policy_fields};

/// Parse a Python policy dict into a QueryPolicy
pub fn parse_query_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<QueryPolicy> {
    trace!("Parsing query policy");
    let mut policy = QueryPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "max_records" => policy.max_records;
        "records_per_second" => policy.records_per_second;
        "max_concurrent_nodes" => policy.max_concurrent_nodes;
        "record_queue_size" => policy.record_queue_size
    });

    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}
