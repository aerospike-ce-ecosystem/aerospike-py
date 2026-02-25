pub mod admin_policy;
pub mod batch_policy;
pub mod client_policy;
pub mod query_policy;
pub mod read_policy;
pub mod write_policy;

use aerospike_core::expressions::Expression;
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
