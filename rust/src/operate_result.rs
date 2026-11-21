//! Shaping the result of a single-record `operate` for Python.
//!
//! Both clients and both calls (`operate`, `operate_ordered`) go through this
//! module, so the sync and the async client cannot drift apart.
//!
//! # What the server sends, and what Python gets
//!
//! Rust client 3.0 asks the server to answer **every** operation whenever the
//! request contains a write, and reports the answers twice on the record:
//! `results` holds one value per answered operation in request order (`Nil`
//! for an operation that returns nothing), and `bins` groups the same answers
//! by bin name, a bin answered more than once holding a `MultiResult`.
//!
//! The official Python client asks for every answer only when the request
//! contains a map, bit, HLL or expression operation. That difference must not
//! leak into Python, so the answers are filtered here by what the *request*
//! was, not by what the server happened to send:
//!
//! - `operate_ordered` follows the official client: one `(bin, value)` entry
//!   per operation in request order. In a request with a map, bit or HLL
//!   operation every operation that names a bin appears, with `None` when it
//!   has no value. In any other request only operations that returned a value
//!   appear. An operation that names no bin (`touch`, `delete`) never appears.
//! - `operate` keeps the shape it always had: a dict with the value of each
//!   bin that returned something — the value itself when the bin was answered
//!   once, a list when it was answered several times.

use aerospike_core::{Record, Value};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::constants::OP_READ;
use crate::record_helpers::record_to_meta;
use crate::types::key::key_to_py;
use crate::types::value::value_to_py;

/// The answer of an operation that has none.
static NIL: Value = Value::Nil;

/// Whether an operation makes the official client ask for an answer to every
/// operation of the request: the map (2xxx), HLL (3xxx) and bit (4xxx)
/// families. List operations (1xxx) and the basic ones do not.
///
/// The binding has no expression operation; the official client treats that
/// family the same way.
fn op_code_answers_every_op(op_code: i32) -> bool {
    (2000..5000).contains(&op_code)
}

/// What `operate_ordered` has to remember about its request to lay out the
/// result: aerospike-core does not expose the bin an `Operation` names.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct OrderedPlan {
    /// Per operation, in request order: the bin it names, if it names one.
    bins: Vec<Option<String>>,
    /// The request contains a map, HLL or bit operation.
    answers_every_op: bool,
    /// The request contains a read of the whole record (`OPERATOR_READ`
    /// without a bin), whose answers are the record's bins rather than one
    /// value.
    reads_whole_record: bool,
}

impl OrderedPlan {
    pub fn with_capacity(operations: usize) -> Self {
        Self {
            bins: Vec::with_capacity(operations),
            ..Self::default()
        }
    }

    /// Record the next operation of the request.
    pub fn note(&mut self, op_code: i32, bin: Option<&str>) {
        self.answers_every_op |= op_code_answers_every_op(op_code);
        self.reads_whole_record |= op_code == OP_READ && bin.is_none();
        self.bins.push(bin.map(str::to_owned));
    }

    /// The `(bin, value)` entries of `operate_ordered`, in request order.
    pub fn entries<'a>(&'a self, record: &'a Record) -> Vec<(&'a str, &'a Value)> {
        if self.reads_whole_record {
            // The answers of a whole-record read are bins, not one value per
            // operation, so there is no request order to restore.
            return record
                .bins
                .iter()
                .filter(|(_, value)| !matches!(value, Value::Nil))
                .map(|(name, value)| (name.as_str(), value))
                .collect();
        }

        let mut entries = Vec::with_capacity(self.bins.len());
        let mut keep = |name: &'a str, value: &'a Value| {
            if self.answers_every_op || !matches!(value, Value::Nil) {
                entries.push((name, value));
            }
        };

        match record.results.as_deref() {
            // One answer per operation: the positions line up with the request.
            Some(results) if results.len() == self.bins.len() => {
                for (bin, value) in self.bins.iter().zip(results) {
                    if let Some(name) = bin {
                        keep(name, value);
                    }
                }
            }
            // Fewer answers than operations. That only happens for a request
            // of plain reads (any write makes the server answer everything),
            // where the server leaves out a bin that does not exist. The
            // answers are then matched to the operations bin by bin.
            _ => {
                for (position, bin) in self.bins.iter().enumerate() {
                    let Some(name) = bin else { continue };
                    let earlier = self.bins[..position]
                        .iter()
                        .filter(|other| other.as_deref() == Some(name.as_str()))
                        .count();
                    match record.bins.get(name.as_str()) {
                        Some(Value::MultiResult(answers)) => {
                            // A read of the same bin gives the same value, so
                            // an operation beyond the answers reuses the last.
                            if let Some(value) = answers.get(earlier).or(answers.last()) {
                                keep(name, value);
                            }
                        }
                        Some(value) => keep(name, value),
                        None => keep(name, &NIL),
                    }
                }
            }
        }
        entries
    }
}

/// The key tuple of an operate result: the key the server sent back when it
/// did (`POLICY_KEY_SEND`), otherwise the request's.
fn result_key(py: Python<'_>, record: &Record, request_key: Py<PyAny>) -> PyResult<Py<PyAny>> {
    match &record.key {
        Some(key) => key_to_py(py, key),
        None => Ok(request_key),
    }
}

/// Convert an `operate_ordered` result to `(key, meta, [(bin, value), ...])`.
pub fn ordered_record_to_py(
    py: Python<'_>,
    record: &Record,
    plan: &OrderedPlan,
    request_key: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let key_py = result_key(py, record, request_key)?;
    let meta = record_to_meta(py, record)?;
    let items: Vec<Py<PyAny>> = plan
        .entries(record)
        .into_iter()
        .map(|(name, value)| {
            let pair = PyTuple::new(
                py,
                [
                    name.into_pyobject(py)?.into_any().unbind(),
                    value_to_py(py, value)?,
                ],
            )?;
            Ok(pair.into_any().unbind())
        })
        .collect::<PyResult<_>>()?;
    let ordered_bins = PyList::new(py, &items)?;
    let result = PyTuple::new(py, [key_py, meta, ordered_bins.into_any().unbind()])?;
    Ok(result.into_any().unbind())
}

/// The value `operate` reports for one bin, or `None` when the bin's
/// operations returned nothing.
enum BinAnswer<'a> {
    One(&'a Value),
    Many(Vec<&'a Value>),
}

fn bin_answer(value: &Value) -> Option<BinAnswer<'_>> {
    match value {
        Value::Nil => None,
        Value::MultiResult(answers) => {
            let mut present: Vec<&Value> = answers
                .iter()
                .filter(|answer| !matches!(answer, Value::Nil))
                .collect();
            match present.len() {
                0 => None,
                1 => present.pop().map(BinAnswer::One),
                _ => Some(BinAnswer::Many(present)),
            }
        }
        other => Some(BinAnswer::One(other)),
    }
}

/// Convert an `operate` result to `(key, meta, {bin: value})`.
pub fn operate_record_to_py(
    py: Python<'_>,
    record: &Record,
    request_key: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let key_py = result_key(py, record, request_key)?;
    let meta = record_to_meta(py, record)?;
    let bins = PyDict::new(py);
    for (name, value) in &record.bins {
        match bin_answer(value) {
            None => {}
            Some(BinAnswer::One(only)) => bins.set_item(name, value_to_py(py, only)?)?,
            Some(BinAnswer::Many(several)) => {
                let items: Vec<Py<PyAny>> = several
                    .into_iter()
                    .map(|answer| value_to_py(py, answer))
                    .collect::<PyResult<_>>()?;
                bins.set_item(name, PyList::new(py, &items)?)?;
            }
        }
    }
    let result = PyTuple::new(py, [key_py, meta, bins.into_any().unbind()])?;
    Ok(result.into_any().unbind())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::constants::{
        OP_BIT_COUNT, OP_DELETE, OP_HLL_ADD, OP_INCR, OP_LIST_APPEND, OP_LIST_CLEAR, OP_LIST_SIZE,
        OP_MAP_PUT, OP_MAP_SIZE, OP_TOUCH, OP_WRITE,
    };
    use aerospike_core::IndexMap;

    fn plan(ops: &[(i32, Option<&str>)]) -> OrderedPlan {
        let mut plan = OrderedPlan::with_capacity(ops.len());
        for (code, bin) in ops {
            plan.note(*code, *bin);
        }
        plan
    }

    /// The record aerospike-core builds for an operate whose operations were
    /// all answered: `answers` are `(bin the reply names, value)` in order.
    fn answered(answers: &[(&str, Value)]) -> Record {
        let mut bins: IndexMap<String, Value> = IndexMap::new();
        let mut results = Vec::new();
        for (name, value) in answers {
            results.push(value.clone());
            if name.is_empty() {
                continue;
            }
            match bins.get_mut(*name) {
                None => {
                    bins.insert((*name).to_string(), value.clone());
                }
                Some(Value::MultiResult(list)) => list.push(value.clone()),
                Some(previous) => {
                    *previous = Value::MultiResult(vec![previous.clone(), value.clone()]);
                }
            }
        }
        Record::new(None, bins, Some(results), 1, 0)
    }

    fn pairs<'a>(entries: &'a [(&'a str, &'a Value)]) -> Vec<(&'a str, Value)> {
        entries
            .iter()
            .map(|(name, value)| (*name, (*value).clone()))
            .collect()
    }

    #[test]
    fn only_map_hll_and_bit_operations_ask_for_every_answer() {
        for code in [OP_MAP_PUT, OP_MAP_SIZE, OP_HLL_ADD, OP_BIT_COUNT] {
            assert!(op_code_answers_every_op(code), "{code}");
        }
        for code in [
            OP_READ,
            OP_WRITE,
            OP_INCR,
            OP_TOUCH,
            OP_DELETE,
            OP_LIST_APPEND,
            OP_LIST_SIZE,
        ] {
            assert!(!op_code_answers_every_op(code), "{code}");
        }
    }

    #[test]
    fn repeated_reads_keep_request_order() {
        let plan = plan(&[
            (OP_READ, Some("c")),
            (OP_READ, Some("a")),
            (OP_READ, Some("c")),
            (OP_READ, Some("b")),
        ]);
        let record = answered(&[
            ("c", Value::Int(3)),
            ("a", Value::Int(1)),
            ("c", Value::Int(3)),
            ("b", Value::Int(2)),
        ]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![
                ("c", Value::Int(3)),
                ("a", Value::Int(1)),
                ("c", Value::Int(3)),
                ("b", Value::Int(2)),
            ]
        );
    }

    #[test]
    fn a_write_without_a_value_is_left_out() {
        let plan = plan(&[(OP_INCR, Some("x")), (OP_READ, Some("x"))]);
        let record = answered(&[("x", Value::Nil), ("x", Value::Int(3))]);
        assert_eq!(pairs(&plan.entries(&record)), vec![("x", Value::Int(3))]);
    }

    #[test]
    fn a_request_of_writes_only_has_no_entries() {
        let plan = plan(&[(OP_WRITE, Some("x"))]);
        let record = answered(&[("x", Value::Nil)]);
        assert!(plan.entries(&record).is_empty());
    }

    #[test]
    fn list_operations_do_not_make_valueless_operations_appear() {
        let plan = plan(&[(OP_LIST_CLEAR, Some("l")), (OP_READ, Some("l"))]);
        let record = answered(&[("l", Value::Nil), ("l", Value::List(vec![]))]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![("l", Value::List(vec![]))]
        );
    }

    #[test]
    fn a_list_write_and_a_read_of_the_same_bin_both_appear() {
        let plan = plan(&[(OP_LIST_APPEND, Some("l")), (OP_READ, Some("l"))]);
        let list = Value::List(vec![Value::Int(1), Value::Int(3)]);
        let record = answered(&[("l", Value::Int(2)), ("l", list.clone())]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![("l", Value::Int(2)), ("l", list)]
        );
    }

    #[test]
    fn a_map_operation_makes_every_named_operation_appear() {
        let plan = plan(&[
            (OP_INCR, Some("x")),
            (OP_READ, Some("x")),
            (OP_MAP_SIZE, Some("m")),
        ]);
        let record = answered(&[
            ("x", Value::Nil),
            ("x", Value::Int(3)),
            ("m", Value::Int(1)),
        ]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![
                ("x", Value::Nil),
                ("x", Value::Int(3)),
                ("m", Value::Int(1)),
            ]
        );
    }

    #[test]
    fn an_operation_without_a_bin_never_appears() {
        for nameless in [OP_TOUCH, OP_DELETE] {
            let plan = plan(&[(nameless, None), (OP_MAP_SIZE, Some("m"))]);
            let record = answered(&[("", Value::Nil), ("m", Value::Int(1))]);
            assert_eq!(pairs(&plan.entries(&record)), vec![("m", Value::Int(1))]);
        }
    }

    #[test]
    fn a_missing_bin_is_left_out_when_the_server_skips_it() {
        // Plain reads: the server answers only the bin that exists, so there
        // are fewer answers than operations.
        let plan = plan(&[(OP_READ, Some("nope")), (OP_READ, Some("b"))]);
        let record = answered(&[("b", Value::Int(2))]);
        assert_eq!(pairs(&plan.entries(&record)), vec![("b", Value::Int(2))]);
    }

    #[test]
    fn a_bin_answered_once_serves_every_read_of_it() {
        let plan = plan(&[
            (OP_READ, Some("c")),
            (OP_READ, Some("nope")),
            (OP_READ, Some("c")),
        ]);
        let record = answered(&[("c", Value::Int(3))]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![("c", Value::Int(3)), ("c", Value::Int(3))]
        );
    }

    #[test]
    fn a_whole_record_read_reports_the_bins_it_returned() {
        let plan = plan(&[(OP_READ, None)]);
        let record = answered(&[("a", Value::Int(1)), ("b", Value::Int(2))]);
        assert_eq!(
            pairs(&plan.entries(&record)),
            vec![("a", Value::Int(1)), ("b", Value::Int(2))]
        );
    }

    // ── operate(): the dict shape ───────────────────────────────

    fn answer_of(value: &Value) -> Option<Vec<Value>> {
        bin_answer(value).map(|answer| match answer {
            BinAnswer::One(only) => vec![only.clone()],
            BinAnswer::Many(several) => several.into_iter().cloned().collect(),
        })
    }

    #[test]
    fn operate_reports_a_bin_answered_once_as_its_value() {
        assert_eq!(answer_of(&Value::Int(7)), Some(vec![Value::Int(7)]));
        assert!(matches!(
            bin_answer(&Value::Int(7)),
            Some(BinAnswer::One(_))
        ));
    }

    #[test]
    fn operate_drops_a_bin_whose_operations_returned_nothing() {
        assert_eq!(answer_of(&Value::Nil), None);
        assert_eq!(
            answer_of(&Value::MultiResult(vec![Value::Nil, Value::Nil])),
            None
        );
    }

    #[test]
    fn operate_reports_the_single_value_among_valueless_answers() {
        // increment then read: [Nil, 15] is 15, as it was before the server
        // was asked to answer the increment too.
        let value = Value::MultiResult(vec![Value::Nil, Value::Int(15)]);
        assert!(matches!(bin_answer(&value), Some(BinAnswer::One(_))));
        assert_eq!(answer_of(&value), Some(vec![Value::Int(15)]));
    }

    #[test]
    fn operate_reports_several_values_as_a_list() {
        let value = Value::MultiResult(vec![Value::Int(2), Value::Nil, Value::Int(4)]);
        assert!(matches!(bin_answer(&value), Some(BinAnswer::Many(_))));
        assert_eq!(answer_of(&value), Some(vec![Value::Int(2), Value::Int(4)]));
    }
}
