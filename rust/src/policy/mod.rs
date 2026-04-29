pub mod admin_policy;
pub mod batch_policy;
pub mod client_policy;
pub mod query_policy;
pub mod read_policy;
pub mod write_policy;

use aerospike_core::expressions::Expression;
use aerospike_core::{CommitLevel, GenerationPolicy, RecordExistsAction};
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
