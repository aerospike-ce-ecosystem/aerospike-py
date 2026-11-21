//! Query/scan policy parsing from Python dicts.

use aerospike_core::query::PartitionFilter;
use aerospike_core::QueryPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{
    extract_filter_expression, extract_policy_fields, parse_partition_filter, parse_query_duration,
    parse_read_mode_ap, parse_read_touch_ttl, parse_replica,
};

/// Refuse a `record_queue_size` no queue can have.
///
/// The queue between the node readers and the consumer is a Tokio channel,
/// and that panics when asked for more slots than its semaphore can count
/// (`usize::MAX >> 3`). Nobody has that many records to queue: a number this
/// large is a mistake, and is reported as one instead of as a panic.
fn check_record_queue_size(record_queue_size: usize) -> PyResult<()> {
    let most = tokio::sync::Semaphore::MAX_PERMITS;
    if record_queue_size > most {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "record_queue_size is too large: {record_queue_size} (the most a queue can hold is {most})"
        )));
    }
    Ok(())
}

/// Parse a Python policy dict into a `(QueryPolicy, PartitionFilter)` pair.
///
/// `PartitionFilter` is a positional argument to
/// `aerospike_core::Client::query()`, not a `QueryPolicy` field, so we return
/// it alongside. When `policy["partition_filter"]` is absent we default to
/// `PartitionFilter::all()`, matching the prior behavior.
pub fn parse_query_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
) -> PyResult<(QueryPolicy, PartitionFilter)> {
    trace!("Parsing query policy");
    let mut policy = QueryPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok((policy, PartitionFilter::all())),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "sleep_between_retries" => policy.base_policy.sleep_between_retries;
        "timeout_delay" => policy.base_policy.timeout_delay;
        "max_records" => policy.max_records;
        "records_per_second" => policy.records_per_second;
        "max_concurrent_nodes" => policy.max_concurrent_nodes;
        "record_queue_size" => policy.record_queue_size;
        "include_bin_data" => policy.include_bin_data
    });
    super::check_max_retries(policy.base_policy.max_retries)?;
    check_record_queue_size(policy.record_queue_size)?;

    if let Some(val) = dict.get_item("replica")? {
        policy.base_policy.replica = parse_replica(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.read_mode_ap = parse_read_mode_ap(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.base_policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }
    if let Some(val) = dict.get_item("expected_duration")? {
        policy.expected_duration = parse_query_duration(val.extract::<i32>()?)?;
    }

    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    let partition_filter = parse_partition_filter(dict)?.unwrap_or_else(PartitionFilter::all);

    Ok((policy, partition_filter))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::partition_filter::partition_filter_by_range;
    use aerospike_core::policy::{QueryDuration, Replica};
    use aerospike_core::{ReadModeAp, ReadTouchTtl};

    fn build_dict<'py>(
        py: Python<'py>,
        build: impl FnOnce(&Bound<'py, PyDict>),
    ) -> Bound<'py, PyDict> {
        let d = PyDict::new(py);
        build(&d);
        d
    }

    #[test]
    fn parse_query_policy_default_when_dict_none() {
        let (policy, pf) = parse_query_policy(None).unwrap();
        assert_eq!(pf.begin, 0);
        assert_eq!(pf.count, 4096);
        assert!(policy.include_bin_data);
    }

    #[test]
    fn parse_query_policy_with_replica() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("replica", 2i32).unwrap();
            });
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.replica, Replica::PreferRack);
        });
    }

    #[test]
    fn parse_query_policy_with_timeout_delay() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("timeout_delay", 500u32).unwrap();
            });
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.timeout_delay, 500);
        });
    }

    #[test]
    fn parse_query_policy_with_sleep_between_retries() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("sleep_between_retries", 250u32).unwrap();
            });
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.sleep_between_retries, 250);
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
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.read_mode_ap, ReadModeAp::All);
            assert!(matches!(
                p.base_policy.read_touch_ttl,
                ReadTouchTtl::Percent(75)
            ));
        });
    }

    #[test]
    fn parse_query_policy_expected_duration_short() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("expected_duration", 1i32).unwrap();
            });
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert_eq!(p.expected_duration, QueryDuration::Short);
        });
    }

    #[test]
    fn parse_query_policy_rejects_unknown_expected_duration() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("expected_duration", 99i32).unwrap();
            });
            let err = match parse_query_policy(Some(&d)) {
                Ok(_) => panic!("an unknown expected_duration must be rejected"),
                Err(err) => err,
            };
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
        });
    }

    #[test]
    fn parse_query_policy_include_bin_data_false() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("include_bin_data", false).unwrap();
            });
            let (p, _) = parse_query_policy(Some(&d)).unwrap();
            assert!(!p.include_bin_data);
        });
    }

    #[test]
    fn parse_query_policy_partition_filter_round_trip() {
        Python::initialize();
        Python::attach(|py| {
            let pf = partition_filter_by_range(100, 256).unwrap();
            let pf_obj = Py::new(py, pf).unwrap();
            let dict = PyDict::new(py);
            dict.set_item("partition_filter", pf_obj).unwrap();
            let (_p, partition_filter) = parse_query_policy(Some(&dict)).unwrap();
            assert_eq!(partition_filter.begin, 100);
            assert_eq!(partition_filter.count, 256);
        });
    }
}
