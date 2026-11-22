//! Shaping the result of a single-record `operate` for Python.
//!
//! Both clients and both calls (`operate`, `operate_ordered`) go through this
//! module, so the sync and the async client cannot drift apart.
//!
//! # What the server sends, and what Python gets
//!
//! Rust client 3.0 asks the server to answer **every** operation whenever the
//! request contains a write, and `operate_ordered` asks for it always. The
//! answers are reported twice on the record: `results` holds one value per
//! answered operation in request order (`Nil` for an operation that returns
//! nothing), and `bins` groups the same answers by bin name, a bin answered
//! more than once holding a `MultiResult`.
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
//!   appear, including a nil list read in a mixed write. A delete appears with
//!   an empty name in respond-all mode; touch never appears.
//! - `operate` keeps the shape it always had: a dict with the value of each
//!   bin that returned something — the value itself when the bin was answered
//!   once, a list when it was answered several times.

use std::collections::HashMap;

use aerospike_core::operations::exp::{read_exp, ExpReadFlags};
use aerospike_core::{expressions, operations::Operation, Record, Value};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::constants::{OP_DELETE, OP_LIST_GET_RANGE, OP_LIST_SIZE, OP_READ, OP_TOUCH};
use crate::operations::op_code_is_write;
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
    operations: Vec<(i32, Option<String>)>,
    answers_every_op: bool,
    reads_whole_record: bool,
    has_write: bool,
    presence_checks: usize,
}

fn may_return_nil_list_element(code: i32) -> bool {
    (1000..2000).contains(&code)
        && !op_code_is_write(code)
        && !matches!(code, OP_LIST_SIZE | OP_LIST_GET_RANGE)
}

impl OrderedPlan {
    pub fn has_write(&self) -> bool {
        self.has_write
    }

    pub fn with_capacity(operations: usize) -> Self {
        Self {
            operations: Vec::with_capacity(operations),
            ..Self::default()
        }
    }

    pub fn note(&mut self, code: i32, bin: Option<&str>) {
        self.answers_every_op |= op_code_answers_every_op(code);
        self.reads_whole_record |= code == OP_READ && bin.unwrap_or_default().is_empty();
        self.has_write |= op_code_is_write(code);
        let name = match code {
            OP_TOUCH => None,
            OP_DELETE => Some(""),
            _ => bin,
        };
        self.operations.push((code, name.map(str::to_owned)));
    }

    /// In a mixed write the official client returns a nil list-read result if
    /// the list exists, but omits a read of an absent list. The core requests
    /// RESPOND_ALL_OPS for all writes, erasing that distinction. Test existence
    /// immediately after the affected operation, in the same atomic command:
    /// later operations may create or delete that bin. The expression returns
    /// a boolean regardless of the list's size.
    pub fn add_presence_checks(&mut self, ops: Vec<Operation>) -> Vec<Operation> {
        if !self.has_write || self.answers_every_op || self.reads_whole_record {
            return ops;
        }
        self.presence_checks = self
            .operations
            .iter()
            .filter(|(code, _)| may_return_nil_list_element(*code))
            .count();
        if self.presence_checks == 0 {
            return ops;
        }
        let mut with_checks = Vec::with_capacity(ops.len() + self.presence_checks);
        for (op, (code, name)) in ops.into_iter().zip(&self.operations) {
            with_checks.push(op);
            if let Some(name) = name
                .as_deref()
                .filter(|_| may_return_nil_list_element(*code))
            {
                with_checks.push(read_exp(
                    name,
                    expressions::bin_exists(name),
                    ExpReadFlags::DEFAULT,
                ));
            }
        }
        with_checks
    }

    /// Public answers in request order. A whole-record read has a variable
    /// number of results and its bin names come directly from the record.
    pub fn entries<'a>(&'a self, record: &'a Record) -> Vec<(&'a str, &'a Value)> {
        if self.reads_whole_record {
            return record
                .bins
                .iter()
                .filter(|(_, value)| !matches!(value, Value::Nil))
                .map(|(name, value)| (name.as_str(), value))
                .collect();
        }

        let mut entries = Vec::with_capacity(self.operations.len());
        // When every op has a slot, positional lookup avoids hashing bin
        // names. Otherwise consume a separate cursor for each named bin:
        // touch, for example, may contribute no response at all.
        let mut positional = record
            .results
            .as_deref()
            .filter(|values| values.len() == self.operations.len() + self.presence_checks)
            .map(|values| values.iter());
        let mut offsets = HashMap::<&str, usize>::new();
        let mut next = |name: &'a str| {
            if let Some(values) = &mut positional {
                return values.next();
            }
            let offset = offsets.entry(name).or_default();
            let i = *offset;
            *offset += 1;
            match record.bins.get(name) {
                Some(Value::MultiResult(values)) => values.get(i),
                Some(value) if i == 0 => Some(value),
                _ => None,
            }
        };
        for (code, name) in &self.operations {
            let Some(name) = name.as_deref() else {
                next("");
                continue;
            };
            let value = next(name);
            let list_exists = self.presence_checks != 0
                && may_return_nil_list_element(*code)
                && matches!(next(name), Some(Value::Bool(true)));
            match value {
                Some(value)
                    if self.answers_every_op || list_exists || !matches!(value, Value::Nil) =>
                {
                    entries.push((name, value));
                }
                None if self.answers_every_op
                    && (!record.bins.contains_key(name) || *code == OP_DELETE) =>
                {
                    entries.push((name, &NIL));
                }
                _ => {}
            }
        }
        entries
    }
}

fn ordered_value_to_py(py: Python<'_>, value: &Value) -> PyResult<Py<PyAny>> {
    if let Value::KeyValueList(pairs) = value {
        let items = PyList::empty(py);
        for (key, value) in pairs {
            items.append(value_to_py(py, key)?)?;
            items.append(value_to_py(py, value)?)?;
        }
        return Ok(items.into_any().unbind());
    }
    value_to_py(py, value)
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
                    ordered_value_to_py(py, value)?,
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
    fn map_requests_include_delete_but_omit_touch() {
        for nameless in [OP_TOUCH, OP_DELETE] {
            let plan = plan(&[(nameless, None), (OP_MAP_SIZE, Some("m"))]);
            let record = answered(&[("", Value::Nil), ("m", Value::Int(1))]);
            let mut expected = vec![("m", Value::Int(1))];
            if nameless == OP_DELETE {
                expected.insert(0, ("", Value::Nil));
            }
            assert_eq!(pairs(&plan.entries(&record)), expected);
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
    fn a_bin_never_gets_more_entries_than_it_has_answers() {
        // Two list reads of one bin, one answer: the other read found nil and
        // the server left it out. Reporting the answer for both would claim a
        // value for an element that has none.
        let plan = plan(&[
            (OP_READ, Some("c")),
            (OP_READ, Some("nope")),
            (OP_READ, Some("c")),
        ]);
        let record = answered(&[("c", Value::Int(3))]);
        assert_eq!(pairs(&plan.entries(&record)), vec![("c", Value::Int(3))]);
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
