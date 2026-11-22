//! Read policy parsing from Python dicts.

use std::sync::LazyLock;

use aerospike_core::ReadPolicy;
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{
    extract_filter_expression, extract_policy_fields, parse_read_mode_ap, parse_read_touch_ttl,
    parse_replica,
};

/// Lazily-initialized default read policy used when no policy dict is provided.
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
        "sleep_between_retries" => policy.base_policy.sleep_between_retries;
        "timeout_delay" => policy.base_policy.timeout_delay
    });
    super::check_max_retries(policy.base_policy.max_retries)?;

    if let Some(val) = dict.get_item("replica")? {
        policy.base_policy.replica = parse_replica(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.read_mode_ap = parse_read_mode_ap(val.extract::<i32>()?)?;
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
    fn parse_read_policy_with_replica_prefer_rack() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("replica", 2i32).unwrap();
            });
            let p = parse_read_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.replica, Replica::PreferRack);
        });
    }

    #[test]
    fn parse_read_policy_with_read_mode_ap_all() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_mode_ap", 1i32).unwrap();
            });
            let p = parse_read_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.read_mode_ap, ReadModeAp::All);
        });
    }

    #[test]
    fn parse_read_policy_with_read_touch_ttl_percent_50() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_touch_ttl_percent", 50i64).unwrap();
            });
            let p = parse_read_policy(Some(&d)).unwrap();
            assert!(matches!(
                p.base_policy.read_touch_ttl,
                ReadTouchTtl::Percent(50)
            ));
        });
    }

    #[test]
    fn parse_read_policy_rejects_out_of_range_ttl_percent() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_touch_ttl_percent", 200i64).unwrap();
            });
            let err = parse_read_policy(Some(&d)).expect_err("must error");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
        });
    }

    #[test]
    fn parse_read_policy_with_timeout_delay() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("timeout_delay", 500u32).unwrap();
            });
            let p = parse_read_policy(Some(&d)).unwrap();
            assert_eq!(p.base_policy.timeout_delay, 500);
        });
    }

    #[test]
    fn parse_read_policy_default_when_dict_is_none() {
        let p = parse_read_policy(None).unwrap();
        assert_eq!(p.base_policy.replica, Replica::Sequence);
        assert_eq!(p.base_policy.read_mode_ap, ReadModeAp::One);
        assert!(matches!(
            p.base_policy.read_touch_ttl,
            ReadTouchTtl::ServerDefault
        ));
    }
}
