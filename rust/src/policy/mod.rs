pub mod admin_policy;
pub mod batch_policy;
pub mod client_policy;
pub mod query_policy;
pub mod read_policy;
pub mod write_policy;

use aerospike_core::expressions::Expression;
use aerospike_core::policy::Replica;
use aerospike_core::{
    CommitLevel, ConsistencyLevel, GenerationPolicy, ReadTouchTTL, RecordExistsAction,
};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::expressions::{is_expression, py_to_expression};

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

/// Extract `filter_expression` from a policy dict, returning `Some(Expression)`
/// if the key is present and is a valid expression, `None` otherwise.
pub fn extract_filter_expression(dict: &Bound<'_, PyDict>) -> PyResult<Option<Expression>> {
    if let Some(val) = dict.get_item("filter_expression")? {
        if is_expression(&val) {
            return Ok(Some(py_to_expression(&val)?));
        }
    }
    Ok(None)
}

/// Map a `POLICY_EXISTS_*` integer constant to a [`RecordExistsAction`].
///
/// Unknown values fall back to [`RecordExistsAction::Update`] to mirror
/// pre-existing behavior in `parse_write_policy`.
pub(crate) fn parse_record_exists_action(val: i32) -> RecordExistsAction {
    match val {
        0 => RecordExistsAction::Update,
        1 => RecordExistsAction::UpdateOnly,
        2 => RecordExistsAction::Replace,
        3 => RecordExistsAction::ReplaceOnly,
        4 => RecordExistsAction::CreateOnly,
        _ => RecordExistsAction::Update,
    }
}

/// Map a `POLICY_GEN_*` integer constant to a [`GenerationPolicy`].
///
/// Unknown values fall back to [`GenerationPolicy::None`].
pub(crate) fn parse_generation_policy(val: i32) -> GenerationPolicy {
    match val {
        0 => GenerationPolicy::None,
        1 => GenerationPolicy::ExpectGenEqual,
        2 => GenerationPolicy::ExpectGenGreater,
        _ => GenerationPolicy::None,
    }
}

/// Map a `POLICY_COMMIT_LEVEL_*` integer constant to a [`CommitLevel`].
///
/// Unknown values fall back to [`CommitLevel::CommitAll`].
pub(crate) fn parse_commit_level(val: i32) -> CommitLevel {
    match val {
        0 => CommitLevel::CommitAll,
        1 => CommitLevel::CommitMaster,
        _ => CommitLevel::CommitAll,
    }
}

/// Map a `POLICY_REPLICA_*` integer constant to a [`Replica`].
///
/// Unknown values fall back to [`Replica::Sequence`] (the aerospike-core default),
/// mirroring the lenient behavior of `parse_record_exists_action`.
pub(crate) fn parse_replica(val: i32) -> Replica {
    match val {
        0 => Replica::Master,
        1 => Replica::Sequence,
        2 => Replica::PreferRack,
        _ => Replica::Sequence,
    }
}

/// Map a `POLICY_READ_MODE_AP_*` integer constant to a [`ConsistencyLevel`].
///
/// Unknown values fall back to [`ConsistencyLevel::ConsistencyOne`].
pub(crate) fn parse_consistency_level(val: i32) -> ConsistencyLevel {
    match val {
        0 => ConsistencyLevel::ConsistencyOne,
        1 => ConsistencyLevel::ConsistencyAll,
        _ => ConsistencyLevel::ConsistencyOne,
    }
}

/// Convert a `read_touch_ttl_percent` integer to a [`ReadTouchTTL`] enum.
///
/// Special values: `0` = `ServerDefault`, `-1` = `DontReset`, `1..=100` = `Percent(N)`.
/// Out-of-range values return an `InvalidArgError` rather than silently clamping —
/// this surfaces config typos early and matches the strictness of `parse_ttl`.
pub(crate) fn parse_read_touch_ttl(val: i64) -> PyResult<ReadTouchTTL> {
    match val {
        0 => Ok(ReadTouchTTL::ServerDefault),
        -1 => Ok(ReadTouchTTL::DontReset),
        n if (1..=100).contains(&n) => Ok(ReadTouchTTL::Percent(n as u8)),
        n => Err(crate::errors::InvalidArgError::new_err(format!(
            "read_touch_ttl_percent out of range: {n} (valid: 0=ServerDefault, -1=DontReset, 1-100=Percent)"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_replica_known_values() {
        assert_eq!(parse_replica(0), Replica::Master);
        assert_eq!(parse_replica(1), Replica::Sequence);
        assert_eq!(parse_replica(2), Replica::PreferRack);
    }

    #[test]
    fn parse_replica_unknown_falls_back_to_sequence() {
        assert_eq!(parse_replica(99), Replica::Sequence);
        assert_eq!(parse_replica(-1), Replica::Sequence);
    }

    #[test]
    fn parse_consistency_level_known_and_unknown() {
        assert_eq!(parse_consistency_level(0), ConsistencyLevel::ConsistencyOne);
        assert_eq!(parse_consistency_level(1), ConsistencyLevel::ConsistencyAll);
        assert_eq!(
            parse_consistency_level(99),
            ConsistencyLevel::ConsistencyOne
        );
    }

    #[test]
    fn parse_read_touch_ttl_special_values() {
        assert!(matches!(
            parse_read_touch_ttl(0).unwrap(),
            ReadTouchTTL::ServerDefault
        ));
        assert!(matches!(
            parse_read_touch_ttl(-1).unwrap(),
            ReadTouchTTL::DontReset
        ));
        assert!(matches!(
            parse_read_touch_ttl(50).unwrap(),
            ReadTouchTTL::Percent(50)
        ));
        assert!(matches!(
            parse_read_touch_ttl(1).unwrap(),
            ReadTouchTTL::Percent(1)
        ));
        assert!(matches!(
            parse_read_touch_ttl(100).unwrap(),
            ReadTouchTTL::Percent(100)
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
