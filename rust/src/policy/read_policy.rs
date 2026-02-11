use std::sync::LazyLock;

use aerospike_core::ReadPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::extract_policy_fields;
use crate::expressions::{is_expression, py_to_expression};

pub static DEFAULT_READ_POLICY: LazyLock<ReadPolicy> = LazyLock::new(ReadPolicy::default);

/// Parse a Python policy dict into a ReadPolicy
pub fn parse_read_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<ReadPolicy> {
    trace!("Parsing read policy");
    let mut policy = ReadPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "sleep_between_retries" => policy.base_policy.sleep_between_retries
    });

    if let Some(val) = dict.get_item("filter_expression")? {
        if is_expression(&val) {
            policy.base_policy.filter_expression = Some(py_to_expression(&val)?);
        }
    }

    Ok(policy)
}
