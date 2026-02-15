use aerospike_core::{Bin, Value};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::value::py_to_value;

/// Convert a Python dict of bins to a Vec<Bin>.
/// Bin values of None (Nil) are skipped, matching the official client behavior
/// where None means "delete this bin" — but for put(), we filter them out
/// to avoid confusing server errors.
pub fn py_dict_to_bins(dict: &Bound<'_, PyDict>) -> PyResult<Vec<Bin>> {
    let mut bins = Vec::with_capacity(dict.len());
    for (key, val) in dict.iter() {
        let name: String = key.extract()?;
        let value = py_to_value(&val)?;
        // Skip Nil bins: putting None for a bin value is treated as a no-op
        // rather than sending a Nil that triggers a confusing RecordNotFound.
        // Use client.remove_bin() to explicitly delete bins.
        if value == Value::Nil {
            continue;
        }
        bins.push(Bin::new(name, value));
    }
    Ok(bins)
}
