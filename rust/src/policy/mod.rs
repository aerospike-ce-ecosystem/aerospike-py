pub mod admin_policy;
pub mod batch_policy;
pub mod client_policy;
pub mod query_policy;
pub mod read_policy;
pub mod write_policy;

use aerospike_core::expressions::Expression;
use aerospike_core::policy::{QueryDuration, Replica};
use aerospike_core::query::PartitionFilter;
use aerospike_core::{CommitLevel, GenerationPolicy, ReadModeAp, ReadTouchTtl, RecordExistsAction};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::expressions::{is_expression, py_to_expression};
use crate::types::partition_filter::PyPartitionFilter;

/// Extract simple typed fields from a Python dict into a policy struct.
///
/// Each field's type is inferred from the assignment target.
/// Complex conversions (enum matching, expression filters) should remain inline.
macro_rules! extract_policy_fields {
    ($dict:expr, { $( $key:literal => $($target:tt).+ );* $(;)? }) => {
        $(
            if let Some(val) = $dict.get_item($key)? {
                $($target).+ = val.extract()?;
            }
        )*
    };
}

pub(crate) use extract_policy_fields;

/// Extract `filter_expression` from a policy dict: `Some(Expression)` when one
/// is given, `None` when the key is absent or `None`.
///
/// Anything else is refused. It used to be ignored, and a filter that is
/// ignored lets through exactly the writes and reads it was there to stop:
/// `put(key, bins, policy={"filter_expression": "v == 1"})` wrote the record
/// unconditionally.
pub fn extract_filter_expression(dict: &Bound<'_, PyDict>) -> PyResult<Option<Expression>> {
    let Some(val) = dict.get_item("filter_expression")? else {
        return Ok(None);
    };
    if val.is_none() {
        return Ok(None);
    }
    if !is_expression(&val) {
        let given = val
            .get_type()
            .name()
            .map_or_else(|_| "?".to_string(), |name| name.to_string());
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "filter_expression must be an expression built with aerospike_py.exp, got {given}"
        )));
    }
    Ok(Some(py_to_expression(&val)?))
}

/// Refuse the one `max_retries` aerospike-core cannot count with.
///
/// It makes `max_retries + 1` attempts. For the largest value that sum wraps
/// to zero, and the command fails with "Timeout after 0 tries" without ever
/// being sent.
pub(crate) fn check_max_retries(max_retries: usize) -> PyResult<()> {
    if max_retries == usize::MAX {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "max_retries is too large: {max_retries}"
        )));
    }
    Ok(())
}

/// Build the `InvalidArgError` raised for a policy constant no enum variant matches.
///
/// An unknown value used to fall back to the enum's default, so a typo such as
/// `exists=9` silently turned a create-only write into a plain update. The
/// request is now rejected before anything is sent.
fn unknown_policy_value(name: &str, val: i32, valid: &str) -> PyErr {
    crate::errors::InvalidArgError::new_err(format!("invalid {name} value: {val} (valid: {valid})"))
}

/// Map a `POLICY_EXISTS_*` integer constant to a [`RecordExistsAction`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_record_exists_action(val: i32) -> PyResult<RecordExistsAction> {
    match val {
        0 => Ok(RecordExistsAction::Update),
        1 => Ok(RecordExistsAction::UpdateOnly),
        2 => Ok(RecordExistsAction::Replace),
        3 => Ok(RecordExistsAction::ReplaceOnly),
        4 => Ok(RecordExistsAction::CreateOnly),
        _ => Err(unknown_policy_value(
            "exists",
            val,
            "POLICY_EXISTS_IGNORE=0, POLICY_EXISTS_UPDATE_ONLY=1, POLICY_EXISTS_REPLACE=2, \
             POLICY_EXISTS_REPLACE_ONLY=3, POLICY_EXISTS_CREATE_ONLY=4",
        )),
    }
}

/// Map a `POLICY_GEN_*` integer constant to a [`GenerationPolicy`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_generation_policy(val: i32) -> PyResult<GenerationPolicy> {
    match val {
        0 => Ok(GenerationPolicy::None),
        1 => Ok(GenerationPolicy::ExpectGenEqual),
        2 => Ok(GenerationPolicy::ExpectGenGreater),
        _ => Err(unknown_policy_value(
            "gen",
            val,
            "POLICY_GEN_IGNORE=0, POLICY_GEN_EQ=1, POLICY_GEN_GT=2",
        )),
    }
}

/// Map a `POLICY_COMMIT_LEVEL_*` integer constant to a [`CommitLevel`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_commit_level(val: i32) -> PyResult<CommitLevel> {
    match val {
        0 => Ok(CommitLevel::CommitAll),
        1 => Ok(CommitLevel::CommitMaster),
        _ => Err(unknown_policy_value(
            "commit_level",
            val,
            "POLICY_COMMIT_LEVEL_ALL=0, POLICY_COMMIT_LEVEL_MASTER=1",
        )),
    }
}

/// Map a `POLICY_REPLICA_*` integer constant to a [`Replica`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_replica(val: i32) -> PyResult<Replica> {
    match val {
        0 => Ok(Replica::Master),
        1 => Ok(Replica::Sequence),
        2 => Ok(Replica::PreferRack),
        _ => Err(unknown_policy_value(
            "replica",
            val,
            "POLICY_REPLICA_MASTER=0, POLICY_REPLICA_SEQUENCE=1, POLICY_REPLICA_PREFER_RACK=2",
        )),
    }
}

/// Map a `POLICY_READ_MODE_AP_*` integer constant to a [`ReadModeAp`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_read_mode_ap(val: i32) -> PyResult<ReadModeAp> {
    match val {
        0 => Ok(ReadModeAp::One),
        1 => Ok(ReadModeAp::All),
        _ => Err(unknown_policy_value(
            "read_mode_ap",
            val,
            "POLICY_READ_MODE_AP_ONE=0, POLICY_READ_MODE_AP_ALL=1",
        )),
    }
}

/// Map a `QUERY_DURATION_*` integer constant to a [`QueryDuration`].
///
/// Unknown values are rejected with `InvalidArgError`.
pub(crate) fn parse_query_duration(val: i32) -> PyResult<QueryDuration> {
    match val {
        0 => Ok(QueryDuration::Long),
        1 => Ok(QueryDuration::Short),
        2 => Ok(QueryDuration::LongRelaxAp),
        _ => Err(unknown_policy_value(
            "expected_duration",
            val,
            "QUERY_DURATION_LONG=0, QUERY_DURATION_SHORT=1, QUERY_DURATION_LONG_RELAX_AP=2",
        )),
    }
}

/// Extract a `PartitionFilter` from a query policy dict.
///
/// Returns `Ok(None)` when the key is absent. Returns `Err` when the value is
/// present but not a `PyPartitionFilter` instance. We clone the inner filter
/// so the user's handle is not mutated by query execution.
pub fn parse_partition_filter(dict: &Bound<'_, PyDict>) -> PyResult<Option<PartitionFilter>> {
    let Some(val) = dict.get_item("partition_filter")? else {
        return Ok(None);
    };
    let pf: PyPartitionFilter = val.extract().map_err(|_| {
        pyo3::exceptions::PyTypeError::new_err(
            "policy['partition_filter'] must be a PartitionFilter instance \
             returned by aerospike_py.partition_filter_all/_by_id/_by_range",
        )
    })?;
    Ok(Some(pf.clone_inner()))
}

/// Convert a `read_touch_ttl_percent` integer to a [`ReadTouchTtl`] enum.
///
/// Special values: `0` = `ServerDefault`, `-1` = `DontReset`, `1..=100` = `Percent(N)`.
/// Out-of-range values return an `InvalidArgError` rather than silently clamping —
/// this surfaces config typos early and matches the strictness of `parse_ttl`.
pub(crate) fn parse_read_touch_ttl(val: i64) -> PyResult<ReadTouchTtl> {
    match val {
        0 => Ok(ReadTouchTtl::ServerDefault),
        -1 => Ok(ReadTouchTtl::DontReset),
        n if (1..=100).contains(&n) => Ok(ReadTouchTtl::Percent(n as u8)),
        n => Err(crate::errors::InvalidArgError::new_err(format!(
            "read_touch_ttl_percent out of range: {n} (valid: 0=ServerDefault, -1=DontReset, 1-100=Percent)"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_invalid_arg<T: std::fmt::Debug>(result: PyResult<T>, needle: &str) {
        Python::initialize();
        Python::attach(|py| {
            let err = result.expect_err("an unknown policy value must be rejected");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            let msg = err.value(py).to_string();
            assert!(msg.contains(needle), "message {msg:?} lacks {needle:?}");
        });
    }

    #[test]
    fn parse_replica_known_values() {
        assert_eq!(parse_replica(0).unwrap(), Replica::Master);
        assert_eq!(parse_replica(1).unwrap(), Replica::Sequence);
        assert_eq!(parse_replica(2).unwrap(), Replica::PreferRack);
    }

    #[test]
    fn parse_replica_rejects_unknown_values() {
        assert_invalid_arg(parse_replica(99), "invalid replica value: 99");
        assert_invalid_arg(parse_replica(-1), "invalid replica value: -1");
    }

    #[test]
    fn parse_consistency_level_known_and_unknown() {
        assert_eq!(parse_read_mode_ap(0).unwrap(), ReadModeAp::One);
        assert_eq!(parse_read_mode_ap(1).unwrap(), ReadModeAp::All);
        assert_invalid_arg(parse_read_mode_ap(99), "invalid read_mode_ap value: 99");
    }

    #[test]
    fn parse_record_exists_action_known_and_unknown() {
        assert!(matches!(
            parse_record_exists_action(0).unwrap(),
            RecordExistsAction::Update
        ));
        assert!(matches!(
            parse_record_exists_action(4).unwrap(),
            RecordExistsAction::CreateOnly
        ));
        // A typo must not degrade to a plain update.
        assert_invalid_arg(parse_record_exists_action(5), "invalid exists value: 5");
        assert_invalid_arg(parse_record_exists_action(-1), "invalid exists value: -1");
    }

    #[test]
    fn parse_generation_policy_known_and_unknown() {
        assert!(matches!(
            parse_generation_policy(1).unwrap(),
            GenerationPolicy::ExpectGenEqual
        ));
        assert!(matches!(
            parse_generation_policy(2).unwrap(),
            GenerationPolicy::ExpectGenGreater
        ));
        // A typo must not silently disable the generation check.
        assert_invalid_arg(parse_generation_policy(3), "invalid gen value: 3");
    }

    #[test]
    fn parse_commit_level_and_query_duration_reject_unknown_values() {
        assert!(matches!(
            parse_commit_level(1).unwrap(),
            CommitLevel::CommitMaster
        ));
        assert_invalid_arg(parse_commit_level(2), "invalid commit_level value: 2");
        assert!(matches!(
            parse_query_duration(1).unwrap(),
            QueryDuration::Short
        ));
        assert_invalid_arg(
            parse_query_duration(3),
            "invalid expected_duration value: 3",
        );
    }

    #[test]
    fn parse_read_touch_ttl_special_values() {
        assert!(matches!(
            parse_read_touch_ttl(0).unwrap(),
            ReadTouchTtl::ServerDefault
        ));
        assert!(matches!(
            parse_read_touch_ttl(-1).unwrap(),
            ReadTouchTtl::DontReset
        ));
        assert!(matches!(
            parse_read_touch_ttl(50).unwrap(),
            ReadTouchTtl::Percent(50)
        ));
        assert!(matches!(
            parse_read_touch_ttl(1).unwrap(),
            ReadTouchTtl::Percent(1)
        ));
        assert!(matches!(
            parse_read_touch_ttl(100).unwrap(),
            ReadTouchTtl::Percent(100)
        ));
    }

    #[test]
    fn parse_read_touch_ttl_rejects_out_of_range() {
        Python::initialize();
        Python::attach(|py| {
            let err = parse_read_touch_ttl(-100).expect_err("must reject -100");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            let err = parse_read_touch_ttl(200).expect_err("must reject 200");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            let err = parse_read_touch_ttl(101).expect_err("boundary 101 must reject");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
        });
    }
}
