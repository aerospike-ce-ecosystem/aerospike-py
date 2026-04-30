//! Query/scan policy parsing from Python dicts.

use aerospike_core::QueryPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{
    extract_filter_expression, extract_policy_fields, parse_consistency_level,
    parse_read_touch_ttl, parse_replica,
};

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

    if let Some(val) = dict.get_item("replica")? {
        policy.replica = parse_replica(val.extract::<i32>()?);
    }
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.consistency_level = parse_consistency_level(val.extract::<i32>()?);
    }
    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.base_policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }

    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aerospike_core::policy::Replica;
    use aerospike_core::{ConsistencyLevel, ReadTouchTTL};

    fn build_dict<'py>(
        py: Python<'py>,
        build: impl FnOnce(&Bound<'py, PyDict>),
    ) -> Bound<'py, PyDict> {
        let d = PyDict::new(py);
        build(&d);
        d
    }

    #[test]
    fn parse_query_policy_with_replica() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("replica", 2i32).unwrap();
            });
            let p = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.replica, Replica::PreferRack);
        });
    }

    #[test]
    fn parse_query_policy_with_read_mode_and_ttl() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_mode_ap", 1i32).unwrap();
                d.set_item("read_touch_ttl_percent", 75i64).unwrap();
            });
            let p = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(
                p.base_policy.consistency_level,
                ConsistencyLevel::ConsistencyAll
            );
            assert!(matches!(
                p.base_policy.read_touch_ttl,
                ReadTouchTTL::Percent(75)
            ));
        });
    }
}
