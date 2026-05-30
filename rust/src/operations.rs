//! Conversion of Python operation dicts to `aerospike_core::Operation` values.
//!
//! Each operation is represented as a Python dict with at minimum an `"op"` key
//! (integer operation code). This module dispatches on that code to construct
//! the corresponding Rust `Operation` for basic CRUD, List CDT, and Map CDT ops.

use aerospike_core::{
    operations,
    operations::bitwise::{self as bit_ops, BitPolicy, BitwiseOverflowActions, BitwiseResizeFlags},
    operations::hll::{self as hll_ops, HLLPolicy},
    operations::lists::{
        self as list_ops, ListOrderType, ListPolicy, ListReturnType, ListSortFlags,
    },
    operations::maps::{self as map_ops, MapOrder, MapPolicy, MapReturnType, MapWriteMode},
    operations::Operation,
    Bin, Value,
};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::constants::*;
use crate::types::value::py_to_value;

// ── Helper functions ────────────────────────────────────────────

/// Require a bin name, returning a descriptive error if absent.
fn require_bin(bin_name: &Option<String>, op_name: &str) -> PyResult<String> {
    bin_name.clone().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("{op_name} operation requires 'bin'"))
    })
}

/// Require a `val` for a bitwise op-dispatch arm.
///
/// The raw op-dict path used to default a missing `val` to `Value::Nil`,
/// which the C-protocol layer happily encoded as an empty/Nil payload —
/// silently producing a no-op or wrong-result bit operation instead of a
/// clear error. The Python facade in `aerospike_py.bit_operations` already
/// requires `value` as a positional argument, so this guards callers who
/// build op dicts directly (or bypass the facade) and mirrors the explicit
/// `require_bin` style used for the bin name.
fn require_bitwise_value(val: Option<Value>, op_name: &str) -> PyResult<Value> {
    val.ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("{op_name} requires 'val'")))
}

/// Require a `val` for an HLL, list-by-value, or map-by-value op-dispatch arm.
///
/// Same failure mode as the bitwise variant: a missing `val` used to default
/// to `Value::Nil`, which downstream helpers like `values_from_list` happily
/// coerce into a single-element `[Nil]` list. For `hll_add` that silently
/// means "add zero values" (the HLL bin is created on first use but no
/// elements register); for `hll_get_union` / `_union_count` / `_intersect_count`
/// / `_similarity` / `_set_union` it means "compare against zero HLL bins",
/// quietly producing a 0/1.0 result that the caller cannot distinguish from
/// an empty input. For `map_put_items` it bypassed the `Value::HashMap` arm
/// and fell through to the ambiguous "map_put_items requires a dict value"
/// error even though the real bug was a missing `val` key. For
/// `list_get_by_value` / `list_remove_by_value` / `map_get_by_value` /
/// `map_remove_by_value` (and their `_list` variants), the dispatch happily
/// queries the bin for `Nil` matches, silently returning an empty result
/// instead of the records the caller actually expected. All the corresponding
/// Python facade helpers already require their values/items as positional
/// arguments, so this only fires for callers who construct op dicts directly.
fn require_hll_value(val: Option<Value>, op_name: &str) -> PyResult<Value> {
    val.ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("{op_name} requires 'val'")))
}

fn get_index(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("index")?
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Operation requires 'index'"))?
        .extract()
}

fn get_rank(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    // Try "rank" key first, fall back to "index" for backward compatibility
    if let Some(v) = dict.get_item("rank")? {
        return v.extract();
    }
    dict.get_item("index")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Operation requires 'rank' or 'index'")
        })?
        .extract()
}

fn get_count(dict: &Bound<'_, PyDict>) -> PyResult<Option<i64>> {
    dict.get_item("count")?
        .and_then(|v| if v.is_none() { None } else { Some(v) })
        .map(|v| v.extract())
        .transpose()
}

fn get_return_type(dict: &Bound<'_, PyDict>) -> PyResult<i32> {
    dict.get_item("return_type")?
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Operation requires 'return_type'"))?
        .extract()
}

fn get_map_key(dict: &Bound<'_, PyDict>) -> PyResult<Value> {
    let v = dict
        .get_item("map_key")?
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Operation requires 'map_key'"))?;
    py_to_value(&v)
}

fn get_val_end(dict: &Bound<'_, PyDict>) -> PyResult<Value> {
    dict.get_item("val_end")?
        .and_then(|v| if v.is_none() { None } else { Some(v) })
        .map(|v| py_to_value(&v))
        .transpose()
        .map(|v| v.unwrap_or(Value::Infinity))
}

/// Map a Python integer to a [`ListReturnType`] enum variant.
fn int_to_list_return_type(v: i32) -> ListReturnType {
    match v {
        0 => ListReturnType::None,
        1 => ListReturnType::Index,
        2 => ListReturnType::ReverseIndex,
        3 => ListReturnType::Rank,
        4 => ListReturnType::ReverseRank,
        5 => ListReturnType::Count,
        7 => ListReturnType::Values,
        13 => ListReturnType::Exists,
        _ => ListReturnType::None,
    }
}

/// Map a Python integer to a [`MapReturnType`] enum variant.
fn int_to_map_return_type(v: i32) -> MapReturnType {
    match v {
        0 => MapReturnType::None,
        1 => MapReturnType::Index,
        2 => MapReturnType::ReverseIndex,
        3 => MapReturnType::Rank,
        4 => MapReturnType::ReverseRank,
        5 => MapReturnType::Count,
        6 => MapReturnType::Key,
        7 => MapReturnType::Value,
        8 => MapReturnType::KeyValue,
        13 => MapReturnType::Exists,
        _ => MapReturnType::None,
    }
}

/// Parse an optional `list_policy` sub-dict from an operation dict.
fn parse_list_policy(dict: &Bound<'_, PyDict>) -> PyResult<ListPolicy> {
    if let Some(policy_obj) = dict.get_item("list_policy")? {
        if policy_obj.is_none() {
            return Ok(ListPolicy::default());
        }
        let policy_dict = policy_obj.cast::<PyDict>()?;
        let order: i32 = policy_dict
            .get_item("order")?
            .map(|v| v.extract())
            .transpose()?
            .unwrap_or(0);
        let flags: u8 = policy_dict
            .get_item("flags")?
            .map(|v| v.extract())
            .transpose()?
            .unwrap_or(0);
        let order_type = match order {
            1 => ListOrderType::Ordered,
            _ => ListOrderType::Unordered,
        };
        Ok(ListPolicy {
            attributes: order_type,
            flags,
        })
    } else {
        Ok(ListPolicy::default())
    }
}

/// Parse an optional `map_policy` sub-dict from an operation dict.
fn parse_map_policy(dict: &Bound<'_, PyDict>) -> PyResult<MapPolicy> {
    if let Some(policy_obj) = dict.get_item("map_policy")? {
        if policy_obj.is_none() {
            return Ok(MapPolicy::default());
        }
        let policy_dict = policy_obj.cast::<PyDict>()?;
        let order: i32 = policy_dict
            .get_item("order")?
            .map(|v| v.extract())
            .transpose()?
            .unwrap_or(0);
        let write_mode: i32 = policy_dict
            .get_item("write_mode")?
            .map(|v| v.extract())
            .transpose()?
            .unwrap_or(0);
        let map_order = match order {
            1 => MapOrder::KeyOrdered,
            3 => MapOrder::KeyValueOrdered,
            _ => MapOrder::Unordered,
        };
        let mode = match write_mode {
            1 => MapWriteMode::CreateOnly,
            2 => MapWriteMode::UpdateOnly,
            _ => MapWriteMode::Update,
        };
        Ok(MapPolicy::new(map_order, mode))
    } else {
        Ok(MapPolicy::default())
    }
}

/// Parse an optional `hll_policy` sub-dict from an operation dict.
fn parse_hll_policy(dict: &Bound<'_, PyDict>) -> PyResult<HLLPolicy> {
    if let Some(policy_obj) = dict.get_item("hll_policy")? {
        if policy_obj.is_none() {
            return Ok(HLLPolicy::default());
        }
        let policy_dict = policy_obj.cast::<PyDict>()?;
        let flags: i64 = policy_dict
            .get_item("flags")?
            .map(|v| v.extract())
            .transpose()?
            .unwrap_or(0);
        Ok(HLLPolicy { flags })
    } else {
        Ok(HLLPolicy::default())
    }
}

/// Parse a `BitPolicy` from an operation dict's `"bit_policy"` key.
fn parse_bit_policy(dict: &Bound<'_, PyDict>) -> PyResult<BitPolicy> {
    if let Some(flags_obj) = dict.get_item("bit_policy")? {
        if flags_obj.is_none() {
            return Ok(BitPolicy::default());
        }
        let flags: u8 = flags_obj.extract()?;
        Ok(BitPolicy::new(flags))
    } else {
        Ok(BitPolicy::default())
    }
}

fn get_bit_offset(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("bit_offset")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit operation requires 'bit_offset'")
        })?
        .extract()
}

fn get_bit_size(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("bit_size")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit operation requires 'bit_size'")
        })?
        .extract()
}

fn get_byte_size(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("byte_size")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit operation requires 'byte_size'")
        })?
        .extract()
}

fn get_byte_offset(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("byte_offset")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit operation requires 'byte_offset'")
        })?
        .extract()
}

fn get_shift(dict: &Bound<'_, PyDict>) -> PyResult<i64> {
    dict.get_item("shift")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit shift operation requires 'shift'")
        })?
        .extract()
}

fn get_signed(dict: &Bound<'_, PyDict>) -> PyResult<bool> {
    match dict.get_item("signed")? {
        Some(v) => v.extract(),
        None => Ok(false),
    }
}

fn get_overflow_action(dict: &Bound<'_, PyDict>) -> PyResult<BitwiseOverflowActions> {
    let action: i32 = dict
        .get_item("action")?
        .map(|v| v.extract())
        .transpose()?
        .unwrap_or(0);
    Ok(match action {
        2 => BitwiseOverflowActions::Saturate,
        4 => BitwiseOverflowActions::Wrap,
        _ => BitwiseOverflowActions::Fail,
    })
}

fn get_resize_flags(dict: &Bound<'_, PyDict>) -> PyResult<Option<BitwiseResizeFlags>> {
    let flags: Option<i32> = dict
        .get_item("resize_flags")?
        .map(|v| v.extract())
        .transpose()?;
    // `BitwiseResizeFlags` is a plain enum in aerospike-core — it cannot
    // represent OR-composed flags. An unrecognized value (e.g. the composed
    // `GROW_ONLY | FROM_FRONT` == 3) previously collapsed to `Default`,
    // silently dropping every requested flag — a resize meant to grow-only
    // could then shrink and truncate data. Reject it loudly instead.
    flags
        .map(|f| match f {
            0 => Ok(BitwiseResizeFlags::Default),
            1 => Ok(BitwiseResizeFlags::FromFront),
            2 => Ok(BitwiseResizeFlags::GrowOnly),
            4 => Ok(BitwiseResizeFlags::ShrinkOnly),
            other => Err(pyo3::exceptions::PyValueError::new_err(format!(
                "bit_resize 'resize_flags' must be a single flag \
                 (0=DEFAULT, 1=FROM_FRONT, 2=GROW_ONLY, 4=SHRINK_ONLY); \
                 OR-composed values are not supported, got {other}"
            ))),
        })
        .transpose()
}

fn get_scan_value(dict: &Bound<'_, PyDict>) -> PyResult<bool> {
    dict.get_item("val")?
        .map(|v| v.extract())
        .transpose()?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("Bit scan operation requires 'val' (bool)")
        })
}

/// Unwrap a `Value::List` into its inner `Vec`, or wrap a single value in a `Vec`.
fn values_from_list(val: &Value) -> Vec<Value> {
    match val {
        Value::List(v) => v.clone(),
        _ => vec![val.clone()],
    }
}

/// Resolve the `val` of a `list_increment` op to the i64 increment amount.
///
/// Mirrors the bit-op (`OP_BIT_ADD`/`OP_BIT_SUBTRACT`) handling: a missing or
/// `Nil` `val` defaults to `+1`; an integer `val` is used as-is; any other type
/// is a type error rather than being silently collapsed to `1`.
fn parse_increment_value(val: &Option<Value>) -> PyResult<i64> {
    match val {
        None | Some(Value::Nil) => Ok(1),
        Some(Value::Int(i)) => Ok(*i),
        Some(other) => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "list_increment requires an integer value, got {other:?}"
        ))),
    }
}

/// Resolve the `val` of a top-level `increment` (`OP_INCR`) op to a numeric value.
///
/// Mirrors the `client.increment()` guard (`parse_increment_offset` in
/// `client_common.rs`): the documented `val` for an increment op is an `int` or
/// `float`. A missing or `Nil` `val` defaults to `+1`. Without this guard a
/// non-numeric `val` (string, list, dict, bytes, …) went through the generic
/// `py_to_value` and was shipped to the server, which fails the `add` operation
/// with an opaque `BinTypeError` instead of a clear client-side error.
fn parse_incr_value(val: Option<Value>) -> PyResult<Value> {
    match val {
        None | Some(Value::Nil) => Ok(Value::Int(1)),
        Some(v @ (Value::Int(_) | Value::Float(_))) => Ok(v),
        Some(other) => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "increment 'val' must be an int or float, got {other:?}"
        ))),
    }
}

/// Parse an operation flag value that should be a small integer (i32).
///
/// Missing/None values default to `0`.
fn parse_i32_flag(val: &Option<Value>, op_name: &str, field_name: &str) -> PyResult<i32> {
    match val {
        None | Some(Value::Nil) => Ok(0),
        Some(Value::Int(i)) => i32::try_from(*i).map_err(|_| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "{op_name} operation '{field_name}' must fit in i32 range, got {i}"
            ))
        }),
        Some(other) => Err(pyo3::exceptions::PyTypeError::new_err(format!(
            "{op_name} operation '{field_name}' must be int, got {other:?}"
        ))),
    }
}

// ── Main conversion ─────────────────────────────────────────────

/// Convert a Python list of operation dicts to Rust Operations.
/// Each operation is a dict: {"op": int, "bin": str, "val": any, ...}
pub fn py_ops_to_rust(ops_list: &Bound<'_, PyList>) -> PyResult<Vec<Operation>> {
    trace!("Converting {} Python operations to Rust", ops_list.len());
    let mut rust_ops: Vec<Operation> = Vec::with_capacity(ops_list.len());

    for item in ops_list.iter() {
        let dict = item.cast::<PyDict>()?;

        let op_code: i32 = dict
            .get_item("op")?
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Operation must have 'op' key"))?
            .extract()?;

        let bin_name: Option<String> = dict
            .get_item("bin")?
            .and_then(|v| if v.is_none() { None } else { Some(v) })
            .map(|v| v.extract())
            .transpose()?;

        let val: Option<Value> = dict
            .get_item("val")?
            .and_then(|v| if v.is_none() { None } else { Some(v) })
            .map(|v| py_to_value(&v))
            .transpose()?;

        let op = match op_code {
            // ── Basic operations ─────────────────────────────
            OP_READ => {
                if let Some(name) = &bin_name {
                    operations::get_bin(name)
                } else {
                    operations::get()
                }
            }
            OP_WRITE => {
                let name = require_bin(&bin_name, "Write")?;
                let v = val.unwrap_or(Value::Nil);
                let bin = Bin::new(name, v);
                operations::put(&bin)
            }
            OP_INCR => {
                let name = require_bin(&bin_name, "Increment")?;
                let v = parse_incr_value(val)?;
                let bin = Bin::new(name, v);
                operations::add(&bin)
            }
            OP_APPEND => {
                let name = require_bin(&bin_name, "Append")?;
                let v = val.unwrap_or(Value::String(String::new()));
                let bin = Bin::new(name, v);
                operations::append(&bin)
            }
            OP_PREPEND => {
                let name = require_bin(&bin_name, "Prepend")?;
                let v = val.unwrap_or(Value::String(String::new()));
                let bin = Bin::new(name, v);
                operations::prepend(&bin)
            }
            OP_TOUCH => operations::touch(),
            OP_DELETE => operations::delete(),

            // ── List CDT operations ──────────────────────────
            OP_LIST_APPEND => {
                let name = require_bin(&bin_name, "list_append")?;
                let policy = parse_list_policy(dict)?;
                let v = val.unwrap_or(Value::Nil);
                list_ops::append(&policy, &name, v)
            }
            OP_LIST_APPEND_ITEMS => {
                let name = require_bin(&bin_name, "list_append_items")?;
                let policy = parse_list_policy(dict)?;
                let v = val.unwrap_or(Value::Nil);
                list_ops::append_items(&policy, &name, values_from_list(&v))
            }
            OP_LIST_INSERT => {
                let name = require_bin(&bin_name, "list_insert")?;
                let policy = parse_list_policy(dict)?;
                let index = get_index(dict)?;
                let v = val.unwrap_or(Value::Nil);
                list_ops::insert(&policy, &name, index, v)
            }
            OP_LIST_INSERT_ITEMS => {
                let name = require_bin(&bin_name, "list_insert_items")?;
                let policy = parse_list_policy(dict)?;
                let index = get_index(dict)?;
                let v = val.unwrap_or(Value::Nil);
                list_ops::insert_items(&policy, &name, index, values_from_list(&v))
            }
            OP_LIST_POP => {
                let name = require_bin(&bin_name, "list_pop")?;
                let index = get_index(dict)?;
                list_ops::pop(&name, index)
            }
            OP_LIST_POP_RANGE => {
                let name = require_bin(&bin_name, "list_pop_range")?;
                let index = get_index(dict)?;
                let count = get_count(dict)?.unwrap_or(1);
                list_ops::pop_range(&name, index, count)
            }
            OP_LIST_REMOVE => {
                let name = require_bin(&bin_name, "list_remove")?;
                let index = get_index(dict)?;
                list_ops::remove(&name, index)
            }
            OP_LIST_REMOVE_RANGE => {
                let name = require_bin(&bin_name, "list_remove_range")?;
                let index = get_index(dict)?;
                let count = get_count(dict)?.unwrap_or(1);
                list_ops::remove_range(&name, index, count)
            }
            OP_LIST_SET => {
                let name = require_bin(&bin_name, "list_set")?;
                let index = get_index(dict)?;
                let v = val.unwrap_or(Value::Nil);
                list_ops::set(&name, index, v)
            }
            OP_LIST_TRIM => {
                let name = require_bin(&bin_name, "list_trim")?;
                let index = get_index(dict)?;
                // `count` is mandatory for list_trim: a missing key defaulting to
                // 0 would silently truncate the bin to an empty list, which is
                // almost never what a caller constructing the op dict directly
                // intends. Sibling range ops (pop_range/remove_range/get_range)
                // default to 1 for convenience; `list_trim` errors instead so
                // the destructive shape of the call is always explicit.
                let count = get_count(dict)?.ok_or_else(|| {
                    pyo3::exceptions::PyValueError::new_err("list_trim requires 'count'")
                })?;
                list_ops::trim(&name, index, count)
            }
            OP_LIST_CLEAR => {
                let name = require_bin(&bin_name, "list_clear")?;
                list_ops::clear(&name)
            }
            OP_LIST_SIZE => {
                let name = require_bin(&bin_name, "list_size")?;
                list_ops::size(&name)
            }
            OP_LIST_GET => {
                let name = require_bin(&bin_name, "list_get")?;
                let index = get_index(dict)?;
                list_ops::get(&name, index)
            }
            OP_LIST_GET_RANGE => {
                let name = require_bin(&bin_name, "list_get_range")?;
                let index = get_index(dict)?;
                let count = get_count(dict)?.unwrap_or(1);
                list_ops::get_range(&name, index, count)
            }
            OP_LIST_GET_BY_VALUE => {
                let name = require_bin(&bin_name, "list_get_by_value")?;
                let v = require_hll_value(val, "list_get_by_value")?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::get_by_value(&name, v, rt)
            }
            OP_LIST_GET_BY_INDEX => {
                let name = require_bin(&bin_name, "list_get_by_index")?;
                let index = get_index(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::get_by_index(&name, index, rt)
            }
            OP_LIST_GET_BY_INDEX_RANGE => {
                let name = require_bin(&bin_name, "list_get_by_index_range")?;
                let index = get_index(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                match get_count(dict)? {
                    Some(count) => list_ops::get_by_index_range_count(&name, index, count, rt),
                    None => list_ops::get_by_index_range(&name, index, rt),
                }
            }
            OP_LIST_GET_BY_RANK => {
                let name = require_bin(&bin_name, "list_get_by_rank")?;
                let rank = get_rank(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::get_by_rank(&name, rank, rt)
            }
            OP_LIST_GET_BY_RANK_RANGE => {
                let name = require_bin(&bin_name, "list_get_by_rank_range")?;
                let rank = get_rank(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                match get_count(dict)? {
                    Some(count) => list_ops::get_by_rank_range_count(&name, rank, count, rt),
                    None => list_ops::get_by_rank_range(&name, rank, rt),
                }
            }
            OP_LIST_GET_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "list_get_by_value_list")?;
                let v = require_hll_value(val, "list_get_by_value_list")?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::get_by_value_list(&name, values_from_list(&v), rt)
            }
            OP_LIST_GET_BY_VALUE_RANGE => {
                let name = require_bin(&bin_name, "list_get_by_value_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::get_by_value_range(&name, begin, end, rt)
            }
            OP_LIST_REMOVE_BY_VALUE => {
                let name = require_bin(&bin_name, "list_remove_by_value")?;
                let v = require_hll_value(val, "list_remove_by_value")?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_value(&name, v, rt)
            }
            OP_LIST_REMOVE_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "list_remove_by_value_list")?;
                let v = require_hll_value(val, "list_remove_by_value_list")?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_value_list(&name, values_from_list(&v), rt)
            }
            OP_LIST_REMOVE_BY_VALUE_RANGE => {
                let name = require_bin(&bin_name, "list_remove_by_value_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_value_range(&name, rt, begin, end)
            }
            OP_LIST_REMOVE_BY_INDEX => {
                let name = require_bin(&bin_name, "list_remove_by_index")?;
                let index = get_index(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_index(&name, index, rt)
            }
            OP_LIST_REMOVE_BY_INDEX_RANGE => {
                let name = require_bin(&bin_name, "list_remove_by_index_range")?;
                let index = get_index(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                match get_count(dict)? {
                    Some(count) => list_ops::remove_by_index_range_count(&name, index, count, rt),
                    None => list_ops::remove_by_index_range(&name, index, rt),
                }
            }
            OP_LIST_REMOVE_BY_RANK => {
                let name = require_bin(&bin_name, "list_remove_by_rank")?;
                let rank = get_rank(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_rank(&name, rank, rt)
            }
            OP_LIST_REMOVE_BY_RANK_RANGE => {
                let name = require_bin(&bin_name, "list_remove_by_rank_range")?;
                let rank = get_rank(dict)?;
                let rt = int_to_list_return_type(get_return_type(dict)?);
                match get_count(dict)? {
                    Some(count) => list_ops::remove_by_rank_range_count(&name, rank, count, rt),
                    None => list_ops::remove_by_rank_range(&name, rank, rt),
                }
            }
            OP_LIST_INCREMENT => {
                let name = require_bin(&bin_name, "list_increment")?;
                let policy = parse_list_policy(dict)?;
                let index = get_index(dict)?;
                let v: i64 = parse_increment_value(&val)?;
                list_ops::increment(&policy, &name, index, v)
            }
            OP_LIST_SORT => {
                let name = require_bin(&bin_name, "list_sort")?;
                let flags = parse_i32_flag(&val, "list_sort", "val")?;
                let sort_flags = match flags {
                    2 => ListSortFlags::DropDuplicates,
                    _ => ListSortFlags::Default,
                };
                list_ops::sort(&name, sort_flags)
            }
            OP_LIST_SET_ORDER => {
                let name = require_bin(&bin_name, "list_set_order")?;
                let order = parse_i32_flag(&val, "list_set_order", "val")?;
                let order_type = match order {
                    1 => ListOrderType::Ordered,
                    _ => ListOrderType::Unordered,
                };
                list_ops::set_order(&name, order_type)
            }

            // ── Map CDT operations ───────────────────────────
            OP_MAP_SET_ORDER => {
                let name = require_bin(&bin_name, "map_set_order")?;
                let order = parse_i32_flag(&val, "map_set_order", "val")?;
                let map_order = match order {
                    1 => MapOrder::KeyOrdered,
                    3 => MapOrder::KeyValueOrdered,
                    _ => MapOrder::Unordered,
                };
                map_ops::set_order(&name, map_order)
            }
            OP_MAP_PUT => {
                let name = require_bin(&bin_name, "map_put")?;
                let policy = parse_map_policy(dict)?;
                let key = get_map_key(dict)?;
                let v = val.unwrap_or(Value::Nil);
                map_ops::put(&policy, &name, key, v)
            }
            OP_MAP_PUT_ITEMS => {
                let name = require_bin(&bin_name, "map_put_items")?;
                let policy = parse_map_policy(dict)?;
                // Reject a missing `val` explicitly. The old fallback to
                // `Value::Nil` here landed in the catch-all arm below and
                // produced the misleading "map_put_items requires a dict
                // value" error, even though the real bug was a missing
                // top-level `val` key.
                let v = require_hll_value(val, "map_put_items")?;
                // Convert Value::HashMap to HashMap
                match v {
                    Value::HashMap(map) => map_ops::put_items(&policy, &name, map),
                    _ => {
                        return Err(pyo3::exceptions::PyValueError::new_err(
                            "map_put_items requires a dict value",
                        ))
                    }
                }
            }
            OP_MAP_INCREMENT => {
                let name = require_bin(&bin_name, "map_increment")?;
                let policy = parse_map_policy(dict)?;
                let key = get_map_key(dict)?;
                let v = val.unwrap_or(Value::Int(1));
                map_ops::increment_value(&policy, &name, key, v)
            }
            OP_MAP_DECREMENT => {
                let name = require_bin(&bin_name, "map_decrement")?;
                let policy = parse_map_policy(dict)?;
                let key = get_map_key(dict)?;
                let v = val.unwrap_or(Value::Int(1));
                map_ops::decrement_value(&policy, &name, key, v)
            }
            OP_MAP_CLEAR => {
                let name = require_bin(&bin_name, "map_clear")?;
                map_ops::clear(&name)
            }
            OP_MAP_REMOVE_BY_KEY => {
                let name = require_bin(&bin_name, "map_remove_by_key")?;
                let key = get_map_key(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_key(&name, key, rt)
            }
            OP_MAP_REMOVE_BY_KEY_LIST => {
                let name = require_bin(&bin_name, "map_remove_by_key_list")?;
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_key_list(&name, values_from_list(&v), rt)
            }
            OP_MAP_REMOVE_BY_KEY_RANGE => {
                let name = require_bin(&bin_name, "map_remove_by_key_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_key_range(&name, begin, end, rt)
            }
            OP_MAP_REMOVE_BY_VALUE => {
                let name = require_bin(&bin_name, "map_remove_by_value")?;
                let v = require_hll_value(val, "map_remove_by_value")?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_value(&name, v, rt)
            }
            OP_MAP_REMOVE_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "map_remove_by_value_list")?;
                let v = require_hll_value(val, "map_remove_by_value_list")?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_value_list(&name, values_from_list(&v), rt)
            }
            OP_MAP_REMOVE_BY_VALUE_RANGE => {
                let name = require_bin(&bin_name, "map_remove_by_value_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_value_range(&name, begin, end, rt)
            }
            OP_MAP_REMOVE_BY_INDEX => {
                let name = require_bin(&bin_name, "map_remove_by_index")?;
                let index = get_index(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_index(&name, index, rt)
            }
            OP_MAP_REMOVE_BY_INDEX_RANGE => {
                let name = require_bin(&bin_name, "map_remove_by_index_range")?;
                let index = get_index(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                // An omitted `count` means "to the end of the map" — use the
                // open-ended variant rather than silently collapsing to count=1.
                match get_count(dict)? {
                    Some(count) => map_ops::remove_by_index_range(&name, index, count, rt),
                    None => map_ops::remove_by_index_range_from(&name, index, rt),
                }
            }
            OP_MAP_REMOVE_BY_RANK => {
                let name = require_bin(&bin_name, "map_remove_by_rank")?;
                let rank = get_rank(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_rank(&name, rank, rt)
            }
            OP_MAP_REMOVE_BY_RANK_RANGE => {
                let name = require_bin(&bin_name, "map_remove_by_rank_range")?;
                let rank = get_rank(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                // An omitted `count` means "to the last ranked item" — use the
                // open-ended variant rather than silently collapsing to count=1.
                match get_count(dict)? {
                    Some(count) => map_ops::remove_by_rank_range(&name, rank, count, rt),
                    None => map_ops::remove_by_rank_range_from(&name, rank, rt),
                }
            }
            OP_MAP_SIZE => {
                let name = require_bin(&bin_name, "map_size")?;
                map_ops::size(&name)
            }
            OP_MAP_GET_BY_KEY => {
                let name = require_bin(&bin_name, "map_get_by_key")?;
                let key = get_map_key(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_key(&name, key, rt)
            }
            OP_MAP_GET_BY_KEY_RANGE => {
                let name = require_bin(&bin_name, "map_get_by_key_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_key_range(&name, begin, end, rt)
            }
            OP_MAP_GET_BY_VALUE => {
                let name = require_bin(&bin_name, "map_get_by_value")?;
                let v = require_hll_value(val, "map_get_by_value")?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_value(&name, v, rt)
            }
            OP_MAP_GET_BY_VALUE_RANGE => {
                let name = require_bin(&bin_name, "map_get_by_value_range")?;
                let begin = val.unwrap_or(Value::Nil);
                let end = get_val_end(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_value_range(&name, begin, end, rt)
            }
            OP_MAP_GET_BY_INDEX => {
                let name = require_bin(&bin_name, "map_get_by_index")?;
                let index = get_index(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_index(&name, index, rt)
            }
            OP_MAP_GET_BY_INDEX_RANGE => {
                let name = require_bin(&bin_name, "map_get_by_index_range")?;
                let index = get_index(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                // An omitted `count` means "to the end of the map" — use the
                // open-ended variant rather than silently collapsing to count=1.
                match get_count(dict)? {
                    Some(count) => map_ops::get_by_index_range(&name, index, count, rt),
                    None => map_ops::get_by_index_range_from(&name, index, rt),
                }
            }
            OP_MAP_GET_BY_RANK => {
                let name = require_bin(&bin_name, "map_get_by_rank")?;
                let rank = get_rank(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_rank(&name, rank, rt)
            }
            OP_MAP_GET_BY_RANK_RANGE => {
                let name = require_bin(&bin_name, "map_get_by_rank_range")?;
                let rank = get_rank(dict)?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                // An omitted `count` means "to the last ranked item" — use the
                // open-ended variant rather than silently collapsing to count=1.
                match get_count(dict)? {
                    Some(count) => map_ops::get_by_rank_range(&name, rank, count, rt),
                    None => map_ops::get_by_rank_range_from(&name, rank, rt),
                }
            }
            OP_MAP_GET_BY_KEY_LIST => {
                let name = require_bin(&bin_name, "map_get_by_key_list")?;
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_key_list(&name, values_from_list(&v), rt)
            }
            OP_MAP_GET_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "map_get_by_value_list")?;
                let v = require_hll_value(val, "map_get_by_value_list")?;
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_value_list(&name, values_from_list(&v), rt)
            }

            // ── HLL CDT operations ───────────────────────────
            OP_HLL_INIT => {
                let name = require_bin(&bin_name, "hll_init")?;
                let policy = parse_hll_policy(dict)?;
                let index_bit_count: i64 = dict
                    .get_item("index_bit_count")?
                    .ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err(
                            "hll_init requires 'index_bit_count'",
                        )
                    })?
                    .extract()?;
                let minhash_bit_count: i64 = dict
                    .get_item("minhash_bit_count")?
                    .map(|v| v.extract())
                    .transpose()?
                    .unwrap_or(-1);
                hll_ops::init_with_min_hash(&policy, &name, index_bit_count, minhash_bit_count)
            }
            OP_HLL_ADD => {
                let name = require_bin(&bin_name, "hll_add")?;
                let policy = parse_hll_policy(dict)?;
                // Reject missing `val` rather than defaulting to `Value::Nil`,
                // which `values_from_list` coerces to an empty list — silently
                // turning `hll_add` into a no-op that still creates the bin.
                let v = require_hll_value(val, "hll_add")?;
                let list = values_from_list(&v);
                let index_bit_count: i64 = dict
                    .get_item("index_bit_count")?
                    .map(|v| v.extract())
                    .transpose()?
                    .unwrap_or(-1);
                let minhash_bit_count: i64 = dict
                    .get_item("minhash_bit_count")?
                    .map(|v| v.extract())
                    .transpose()?
                    .unwrap_or(-1);
                hll_ops::add_with_index_and_min_hash(
                    &policy,
                    &name,
                    list,
                    index_bit_count,
                    minhash_bit_count,
                )
            }
            OP_HLL_GET_COUNT => {
                let name = require_bin(&bin_name, "hll_get_count")?;
                hll_ops::get_count(&name)
            }
            OP_HLL_GET_UNION => {
                let name = require_bin(&bin_name, "hll_get_union")?;
                // Missing `val` would degrade to "union with zero HLL bins"
                // and return the bin contents unchanged — see require_hll_value
                // for the full rationale.
                let v = require_hll_value(val, "hll_get_union")?;
                hll_ops::get_union(&name, values_from_list(&v))
            }
            OP_HLL_GET_UNION_COUNT => {
                let name = require_bin(&bin_name, "hll_get_union_count")?;
                let v = require_hll_value(val, "hll_get_union_count")?;
                hll_ops::get_union_count(&name, values_from_list(&v))
            }
            OP_HLL_GET_INTERSECT_COUNT => {
                let name = require_bin(&bin_name, "hll_get_intersect_count")?;
                let v = require_hll_value(val, "hll_get_intersect_count")?;
                hll_ops::get_intersect_count(&name, values_from_list(&v))
            }
            OP_HLL_GET_SIMILARITY => {
                let name = require_bin(&bin_name, "hll_get_similarity")?;
                let v = require_hll_value(val, "hll_get_similarity")?;
                hll_ops::get_similarity(&name, values_from_list(&v))
            }
            OP_HLL_DESCRIBE => {
                let name = require_bin(&bin_name, "hll_describe")?;
                hll_ops::describe(&name)
            }
            OP_HLL_FOLD => {
                let name = require_bin(&bin_name, "hll_fold")?;
                let index_bit_count: i64 = dict
                    .get_item("index_bit_count")?
                    .ok_or_else(|| {
                        pyo3::exceptions::PyValueError::new_err(
                            "hll_fold requires 'index_bit_count'",
                        )
                    })?
                    .extract()?;
                hll_ops::fold(&name, index_bit_count)
            }
            OP_HLL_SET_UNION => {
                let name = require_bin(&bin_name, "hll_set_union")?;
                let policy = parse_hll_policy(dict)?;
                // Missing `val` would replace the bin with the union of zero
                // HLL bins (i.e. silently clear it). Force the caller to
                // supply the list explicitly.
                let v = require_hll_value(val, "hll_set_union")?;
                hll_ops::set_union(&policy, &name, values_from_list(&v))
            }

            // ── Bitwise CDT operations ─────────────────────────
            OP_BIT_RESIZE => {
                let name = require_bin(&bin_name, "bit_resize")?;
                let byte_size = get_byte_size(dict)?;
                let resize_flags = get_resize_flags(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::resize(&name, byte_size, resize_flags, &policy)
            }
            OP_BIT_INSERT => {
                let name = require_bin(&bin_name, "bit_insert")?;
                let byte_offset = get_byte_offset(dict)?;
                let v = require_bitwise_value(val, "bit_insert")?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::insert(&name, byte_offset, v, &policy)
            }
            OP_BIT_REMOVE => {
                let name = require_bin(&bin_name, "bit_remove")?;
                let byte_offset = get_byte_offset(dict)?;
                let byte_size = get_byte_size(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::remove(&name, byte_offset, byte_size, &policy)
            }
            OP_BIT_SET => {
                let name = require_bin(&bin_name, "bit_set")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let v = require_bitwise_value(val, "bit_set")?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::set(&name, bit_offset, bit_size, v, &policy)
            }
            OP_BIT_OR => {
                let name = require_bin(&bin_name, "bit_or")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let v = require_bitwise_value(val, "bit_or")?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::or(&name, bit_offset, bit_size, v, &policy)
            }
            OP_BIT_XOR => {
                let name = require_bin(&bin_name, "bit_xor")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let v = require_bitwise_value(val, "bit_xor")?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::xor(&name, bit_offset, bit_size, v, &policy)
            }
            OP_BIT_AND => {
                let name = require_bin(&bin_name, "bit_and")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let v = require_bitwise_value(val, "bit_and")?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::and(&name, bit_offset, bit_size, v, &policy)
            }
            OP_BIT_NOT => {
                let name = require_bin(&bin_name, "bit_not")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::not(&name, bit_offset, bit_size, &policy)
            }
            OP_BIT_LSHIFT => {
                let name = require_bin(&bin_name, "bit_lshift")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let shift = get_shift(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::lshift(&name, bit_offset, bit_size, shift, &policy)
            }
            OP_BIT_RSHIFT => {
                let name = require_bin(&bin_name, "bit_rshift")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let shift = get_shift(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::rshift(&name, bit_offset, bit_size, shift, &policy)
            }
            OP_BIT_ADD => {
                let name = require_bin(&bin_name, "bit_add")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let value_int: i64 = match &val {
                    Some(Value::Int(i)) => *i,
                    Some(other) => {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "bit operation requires an integer value, got {:?}",
                            other
                        )))
                    }
                    None => {
                        return Err(pyo3::exceptions::PyValueError::new_err(
                            "bit operation requires a 'val' parameter",
                        ))
                    }
                };
                let signed = get_signed(dict)?;
                let action = get_overflow_action(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::add(
                    &name, bit_offset, bit_size, value_int, signed, action, &policy,
                )
            }
            OP_BIT_SUBTRACT => {
                let name = require_bin(&bin_name, "bit_subtract")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let value_int: i64 = match &val {
                    Some(Value::Int(i)) => *i,
                    Some(other) => {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "bit operation requires an integer value, got {:?}",
                            other
                        )))
                    }
                    None => {
                        return Err(pyo3::exceptions::PyValueError::new_err(
                            "bit operation requires a 'val' parameter",
                        ))
                    }
                };
                let signed = get_signed(dict)?;
                let action = get_overflow_action(dict)?;
                let policy = parse_bit_policy(dict)?;
                bit_ops::subtract(
                    &name, bit_offset, bit_size, value_int, signed, action, &policy,
                )
            }
            OP_BIT_SET_INT => {
                let name = require_bin(&bin_name, "bit_set_int")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let value_int: i64 = match &val {
                    Some(Value::Int(i)) => *i,
                    Some(other) => {
                        return Err(pyo3::exceptions::PyValueError::new_err(format!(
                            "bit operation requires an integer value, got {:?}",
                            other
                        )))
                    }
                    None => {
                        return Err(pyo3::exceptions::PyValueError::new_err(
                            "bit operation requires a 'val' parameter",
                        ))
                    }
                };
                let policy = parse_bit_policy(dict)?;
                bit_ops::set_int(&name, bit_offset, bit_size, value_int, &policy)
            }
            OP_BIT_GET => {
                let name = require_bin(&bin_name, "bit_get")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                bit_ops::get(&name, bit_offset, bit_size)
            }
            OP_BIT_COUNT => {
                let name = require_bin(&bin_name, "bit_count")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                bit_ops::count(&name, bit_offset, bit_size)
            }
            OP_BIT_LSCAN => {
                let name = require_bin(&bin_name, "bit_lscan")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let scan_val = get_scan_value(dict)?;
                bit_ops::lscan(&name, bit_offset, bit_size, scan_val)
            }
            OP_BIT_RSCAN => {
                let name = require_bin(&bin_name, "bit_rscan")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let scan_val = get_scan_value(dict)?;
                bit_ops::rscan(&name, bit_offset, bit_size, scan_val)
            }
            OP_BIT_GET_INT => {
                let name = require_bin(&bin_name, "bit_get_int")?;
                let bit_offset = get_bit_offset(dict)?;
                let bit_size = get_bit_size(dict)?;
                let signed = get_signed(dict)?;
                bit_ops::get_int(&name, bit_offset, bit_size, signed)
            }

            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unsupported operation code: {op_code}. Supported codes: \
                     READ={OP_READ}, WRITE={OP_WRITE}, INCR={OP_INCR}, \
                     APPEND={OP_APPEND}, PREPEND={OP_PREPEND}, TOUCH={OP_TOUCH}, DELETE={OP_DELETE}, \
                     List CDT=1001-1031, Map CDT=2001-2027, HLL CDT=3001-3010, Bit CDT=4001-4054"
                )));
            }
        };

        rust_ops.push(op);
    }

    Ok(rust_ops)
}

#[cfg(test)]
mod tests {
    use super::{get_resize_flags, parse_i32_flag, parse_incr_value, parse_increment_value};
    use aerospike_core::operations::bitwise::BitwiseResizeFlags;
    use aerospike_core::Value;
    use pyo3::types::PyDict;
    use pyo3::{exceptions::PyTypeError, exceptions::PyValueError, PyErr, Python};

    #[test]
    fn get_resize_flags_accepts_known_single_flags() {
        Python::initialize();
        Python::attach(|py| {
            // Missing key -> None (no flags requested).
            let empty = PyDict::new(py);
            assert!(get_resize_flags(&empty)
                .expect("missing resize_flags is fine")
                .is_none());

            for (raw, expected) in [
                (0, BitwiseResizeFlags::Default),
                (1, BitwiseResizeFlags::FromFront),
                (2, BitwiseResizeFlags::GrowOnly),
                (4, BitwiseResizeFlags::ShrinkOnly),
            ] {
                let d = PyDict::new(py);
                d.set_item("resize_flags", raw).unwrap();
                let got = get_resize_flags(&d)
                    .expect("known flag should parse")
                    .expect("flag is present");
                // BitwiseResizeFlags is not PartialEq; compare via discriminant.
                assert_eq!(
                    std::mem::discriminant(&got),
                    std::mem::discriminant(&expected),
                    "resize_flags {raw} should map to the matching flag"
                );
            }
        });
    }

    #[test]
    fn get_resize_flags_rejects_composed_or_unknown_value() {
        Python::initialize();
        Python::attach(|py| {
            // 3 == GROW_ONLY | FROM_FRONT — must fail loudly, not silently
            // collapse to Default and risk truncating data on resize.
            for bad in [3, 5, 6, 7, 99] {
                let d = PyDict::new(py);
                d.set_item("resize_flags", bad).unwrap();
                let err = get_resize_flags(&d)
                    .expect_err("composed/unknown resize flag must be rejected");
                assert!(err.is_instance_of::<PyValueError>(py));
            }
        });
    }

    #[test]
    fn parse_i32_flag_defaults_to_zero_for_missing_or_nil() {
        assert_eq!(
            parse_i32_flag(&None, "list_sort", "val").expect("None should default to 0"),
            0
        );
        assert_eq!(
            parse_i32_flag(&Some(Value::Nil), "list_sort", "val").expect("Nil should default to 0"),
            0
        );
    }

    #[test]
    fn parse_i32_flag_accepts_in_range_int() {
        let parsed = parse_i32_flag(&Some(Value::Int(i64::from(i32::MAX))), "list_sort", "val")
            .expect("i32 max should be accepted");
        assert_eq!(parsed, i32::MAX);
    }

    #[test]
    fn parse_i32_flag_rejects_out_of_range_int() {
        Python::initialize();
        let err: PyErr = parse_i32_flag(
            &Some(Value::Int(i64::from(i32::MAX) + 1)),
            "list_sort",
            "val",
        )
        .expect_err("out-of-range int should fail");
        Python::attach(|py| {
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    #[test]
    fn parse_i32_flag_rejects_non_int() {
        let err: PyErr = parse_i32_flag(&Some(Value::String("2".to_string())), "list_sort", "val")
            .expect_err("non-int should fail");
        Python::initialize();
        Python::attach(|py| {
            assert!(err.is_instance_of::<PyTypeError>(py));
        });
    }

    #[test]
    fn parse_increment_value_defaults_to_one_for_missing_or_nil() {
        assert_eq!(
            parse_increment_value(&None).expect("None should default to +1"),
            1
        );
        assert_eq!(
            parse_increment_value(&Some(Value::Nil)).expect("Nil should default to +1"),
            1
        );
    }

    #[test]
    fn parse_increment_value_uses_int_as_is() {
        assert_eq!(
            parse_increment_value(&Some(Value::Int(5))).expect("int should be used as-is"),
            5
        );
        assert_eq!(
            parse_increment_value(&Some(Value::Int(-3))).expect("negative int should be used"),
            -3
        );
    }

    #[test]
    fn parse_increment_value_rejects_non_int() {
        Python::initialize();
        for bad in [
            Value::String("1".to_string()),
            Value::Float(aerospike_core::FloatValue::from(1.5_f64)),
            Value::Bool(true),
        ] {
            let err: PyErr = parse_increment_value(&Some(bad))
                .expect_err("non-int value should raise instead of defaulting to +1");
            Python::attach(|py| {
                assert!(err.is_instance_of::<PyValueError>(py));
            });
        }
    }

    #[test]
    fn parse_incr_value_defaults_to_one_for_missing_or_nil() {
        assert!(matches!(
            parse_incr_value(None).expect("None should default to +1"),
            Value::Int(1)
        ));
        assert!(matches!(
            parse_incr_value(Some(Value::Nil)).expect("Nil should default to +1"),
            Value::Int(1)
        ));
    }

    #[test]
    fn parse_incr_value_accepts_int_and_float() {
        assert!(matches!(
            parse_incr_value(Some(Value::Int(5))).expect("int should be accepted"),
            Value::Int(5)
        ));
        assert!(matches!(
            parse_incr_value(Some(Value::Float(aerospike_core::FloatValue::from(
                0.5_f64
            ))))
            .expect("float should be accepted"),
            Value::Float(_)
        ));
    }

    #[test]
    fn parse_incr_value_rejects_non_numeric() {
        Python::initialize();
        for bad in [
            Value::String("5".to_string()),
            Value::Bool(true),
            Value::List(vec![Value::Int(1)]),
        ] {
            let err: PyErr = parse_incr_value(Some(bad))
                .expect_err("non-numeric val should raise instead of reaching the server");
            Python::attach(|py| {
                assert!(err.is_instance_of::<PyTypeError>(py));
                let msg = err.to_string();
                assert!(
                    msg.contains("increment") && msg.contains("val"),
                    "error should mention 'increment' and 'val', got: {msg}"
                );
            });
        }
    }

    // ── Map index/rank range: omitted `count` must be open-ended ──────────
    //
    // Regression for the bug where `map_get_by_index_range` / `_rank_range`
    // (and the remove variants) with no `count` silently collapsed to
    // `count = 1`, returning a single element instead of "to the end of the
    // map". The open-ended `aerospike-core` variants emit one fewer wire
    // argument (no trailing count `Int`), which we assert via the debug
    // representation of the produced `Operation`.

    use pyo3::prelude::*;
    use pyo3::types::PyList;

    /// Build a single-op `PyList` from `(op_code, extra fields)` and convert it.
    fn convert_one_op<'py>(
        py: Python<'py>,
        op_code: i32,
        with: impl FnOnce(&Bound<'py, PyDict>),
    ) -> aerospike_core::operations::Operation {
        let dict = PyDict::new(py);
        dict.set_item("op", op_code).unwrap();
        dict.set_item("bin", "mybin").unwrap();
        with(&dict);
        let ops = PyList::new(py, [dict]).unwrap();
        let mut converted = super::py_ops_to_rust(&ops).expect("conversion should succeed");
        assert_eq!(converted.len(), 1);
        converted.pop().unwrap()
    }

    /// Count the `CdtArgument::Int(...)` entries in an operation's debug output.
    fn int_arg_count(op: &aerospike_core::operations::Operation) -> usize {
        format!("{op:?}").matches("Int(").count()
    }

    #[test]
    fn map_index_range_omitted_count_is_open_ended() {
        Python::initialize();
        Python::attach(|py| {
            for &op_code in &[
                super::OP_MAP_GET_BY_INDEX_RANGE,
                super::OP_MAP_REMOVE_BY_INDEX_RANGE,
            ] {
                // With an explicit count: return_type, index, count -> 3 Ints.
                let with_count = convert_one_op(py, op_code, |d| {
                    d.set_item("index", 0i64).unwrap();
                    d.set_item("return_type", 7i32).unwrap();
                    d.set_item("count", 3i64).unwrap();
                });
                assert_eq!(
                    int_arg_count(&with_count),
                    3,
                    "op {op_code}: explicit count must keep the count argument"
                );

                // Without count: return_type, index -> 2 Ints (open-ended).
                let no_count = convert_one_op(py, op_code, |d| {
                    d.set_item("index", 0i64).unwrap();
                    d.set_item("return_type", 7i32).unwrap();
                });
                assert_eq!(
                    int_arg_count(&no_count),
                    2,
                    "op {op_code}: omitted count must select to the end of the map, \
                     not collapse to count=1"
                );
            }
        });
    }

    #[test]
    fn map_rank_range_omitted_count_is_open_ended() {
        Python::initialize();
        Python::attach(|py| {
            for &op_code in &[
                super::OP_MAP_GET_BY_RANK_RANGE,
                super::OP_MAP_REMOVE_BY_RANK_RANGE,
            ] {
                let with_count = convert_one_op(py, op_code, |d| {
                    d.set_item("rank", 1i64).unwrap();
                    d.set_item("return_type", 7i32).unwrap();
                    d.set_item("count", 2i64).unwrap();
                });
                assert_eq!(
                    int_arg_count(&with_count),
                    3,
                    "op {op_code}: explicit count must keep the count argument"
                );

                let no_count = convert_one_op(py, op_code, |d| {
                    d.set_item("rank", 1i64).unwrap();
                    d.set_item("return_type", 7i32).unwrap();
                });
                assert_eq!(
                    int_arg_count(&no_count),
                    2,
                    "op {op_code}: omitted count must select to the last ranked item, \
                     not collapse to count=1"
                );
            }
        });
    }

    // ── list_trim: missing `count` must error, not silently empty the bin ──
    //
    // Regression for the bug where omitting `count` from a `list_trim` op dict
    // defaulted to `0`, which Aerospike interprets as "keep zero elements" —
    // i.e. it destructively empties the list. The fix raises ValueError
    // instead so the destructive shape is always explicit.

    #[test]
    fn list_trim_missing_count_raises_value_error() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("op", super::OP_LIST_TRIM).unwrap();
            dict.set_item("bin", "mybin").unwrap();
            dict.set_item("index", 0i64).unwrap();
            // intentionally omit "count"
            let ops = PyList::new(py, [dict]).unwrap();

            let err = super::py_ops_to_rust(&ops)
                .expect_err("list_trim without 'count' must raise ValueError");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains("count"),
                "error message should mention 'count', got: {msg}"
            );
        });
    }

    #[test]
    fn list_trim_with_count_succeeds() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("op", super::OP_LIST_TRIM).unwrap();
            dict.set_item("bin", "mybin").unwrap();
            dict.set_item("index", 1i64).unwrap();
            dict.set_item("count", 3i64).unwrap();
            let ops = PyList::new(py, [dict]).unwrap();

            let converted =
                super::py_ops_to_rust(&ops).expect("list_trim with explicit count must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    // ── Bitwise ops: missing `val` must error, not silently become Nil ─────
    //
    // Regression for the bug where the OP_BIT_INSERT / OP_BIT_SET /
    // OP_BIT_OR / OP_BIT_XOR / OP_BIT_AND dispatch arms defaulted a missing
    // `val` key to `Value::Nil`. The C-protocol layer happily encoded that
    // as an empty/Nil payload, silently producing a no-op or wrong-result
    // bit operation. The fix raises ValueError("<op> requires 'val'") so a
    // caller building op dicts directly gets a clear failure instead.
    //
    // Each test exercises both the missing-val and explicit-val paths so a
    // future regression in either direction is caught.

    /// Build a single bit-op dict with the given op code and offset/size
    /// keys, optionally setting `val`.
    fn build_bit_op_dict<'py>(
        py: Python<'py>,
        op_code: i32,
        with_val: Option<&[u8]>,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("op", op_code).unwrap();
        dict.set_item("bin", "mybin").unwrap();
        // OP_BIT_INSERT uses byte_offset; the other four use bit_offset+bit_size.
        // Setting all three keys is harmless because each arm reads only the
        // ones it needs.
        dict.set_item("byte_offset", 0i64).unwrap();
        dict.set_item("bit_offset", 0i64).unwrap();
        dict.set_item("bit_size", 8i64).unwrap();
        if let Some(bytes) = with_val {
            dict.set_item("val", bytes).unwrap();
        }
        dict
    }

    fn assert_bit_op_missing_val_errors(op_code: i32, op_name: &str) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_bit_op_dict(py, op_code, None);
            let ops = PyList::new(py, [dict]).unwrap();
            let err = super::py_ops_to_rust(&ops)
                .expect_err("missing 'val' must raise ValueError, not silently become Nil");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains(op_name) && msg.contains("val"),
                "error message should mention '{op_name}' and 'val', got: {msg}"
            );
        });
    }

    fn assert_bit_op_with_val_succeeds(op_code: i32) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_bit_op_dict(py, op_code, Some(b"\xff"));
            let ops = PyList::new(py, [dict]).unwrap();
            let converted =
                super::py_ops_to_rust(&ops).expect("bit op with explicit val must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    #[test]
    fn bit_insert_missing_val_raises_value_error() {
        assert_bit_op_missing_val_errors(super::OP_BIT_INSERT, "bit_insert");
        assert_bit_op_with_val_succeeds(super::OP_BIT_INSERT);
    }

    #[test]
    fn bit_set_missing_val_raises_value_error() {
        assert_bit_op_missing_val_errors(super::OP_BIT_SET, "bit_set");
        assert_bit_op_with_val_succeeds(super::OP_BIT_SET);
    }

    #[test]
    fn bit_or_missing_val_raises_value_error() {
        assert_bit_op_missing_val_errors(super::OP_BIT_OR, "bit_or");
        assert_bit_op_with_val_succeeds(super::OP_BIT_OR);
    }

    #[test]
    fn bit_xor_missing_val_raises_value_error() {
        assert_bit_op_missing_val_errors(super::OP_BIT_XOR, "bit_xor");
        assert_bit_op_with_val_succeeds(super::OP_BIT_XOR);
    }

    #[test]
    fn bit_and_missing_val_raises_value_error() {
        assert_bit_op_missing_val_errors(super::OP_BIT_AND, "bit_and");
        assert_bit_op_with_val_succeeds(super::OP_BIT_AND);
    }

    // ── HLL ops: missing `val` must error, not silently become Nil ────────
    //
    // Regression for the bug where the OP_HLL_ADD / OP_HLL_GET_UNION /
    // OP_HLL_GET_UNION_COUNT / OP_HLL_GET_INTERSECT_COUNT /
    // OP_HLL_GET_SIMILARITY / OP_HLL_SET_UNION arms defaulted a missing
    // `val` key to `Value::Nil`. Downstream `values_from_list` coerces Nil
    // to an empty list, so `hll_add` silently registered zero elements
    // (while still creating the bin) and the get_* ops compared against
    // zero HLL bins — producing a 0/1.0 result the caller could not
    // distinguish from a genuinely empty input. The fix raises
    // ValueError("<op> requires 'val'") so a caller building op dicts
    // directly gets a clear failure instead.

    /// Build a single HLL-op dict with the given op code, optionally setting
    /// `val` to a list of byte payloads (each payload represents an HLL bin
    /// value or, for `hll_add`, an item to register).
    fn build_hll_op_dict<'py>(
        py: Python<'py>,
        op_code: i32,
        with_val: Option<Vec<&[u8]>>,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("op", op_code).unwrap();
        dict.set_item("bin", "mybin").unwrap();
        if let Some(items) = with_val {
            let list = PyList::new(py, items).unwrap();
            dict.set_item("val", list).unwrap();
        }
        dict
    }

    fn assert_hll_op_missing_val_errors(op_code: i32, op_name: &str) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_hll_op_dict(py, op_code, None);
            let ops = PyList::new(py, [dict]).unwrap();
            let err = super::py_ops_to_rust(&ops)
                .expect_err("missing 'val' must raise ValueError, not silently become Nil");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains(op_name) && msg.contains("val"),
                "error message should mention '{op_name}' and 'val', got: {msg}"
            );
        });
    }

    fn assert_hll_op_with_val_succeeds(op_code: i32) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_hll_op_dict(py, op_code, Some(vec![b"\x00\x01"]));
            let ops = PyList::new(py, [dict]).unwrap();
            let converted =
                super::py_ops_to_rust(&ops).expect("HLL op with explicit val must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    #[test]
    fn hll_add_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(super::OP_HLL_ADD, "hll_add");
        assert_hll_op_with_val_succeeds(super::OP_HLL_ADD);
    }

    #[test]
    fn hll_get_union_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(super::OP_HLL_GET_UNION, "hll_get_union");
        assert_hll_op_with_val_succeeds(super::OP_HLL_GET_UNION);
    }

    #[test]
    fn hll_get_union_count_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(super::OP_HLL_GET_UNION_COUNT, "hll_get_union_count");
        assert_hll_op_with_val_succeeds(super::OP_HLL_GET_UNION_COUNT);
    }

    #[test]
    fn hll_get_intersect_count_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(
            super::OP_HLL_GET_INTERSECT_COUNT,
            "hll_get_intersect_count",
        );
        assert_hll_op_with_val_succeeds(super::OP_HLL_GET_INTERSECT_COUNT);
    }

    #[test]
    fn hll_get_similarity_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(super::OP_HLL_GET_SIMILARITY, "hll_get_similarity");
        assert_hll_op_with_val_succeeds(super::OP_HLL_GET_SIMILARITY);
    }

    #[test]
    fn hll_set_union_missing_val_raises_value_error() {
        assert_hll_op_missing_val_errors(super::OP_HLL_SET_UNION, "hll_set_union");
        assert_hll_op_with_val_succeeds(super::OP_HLL_SET_UNION);
    }

    // ── map_put_items: missing `val` must error with a clear message ──────
    //
    // Regression for the bug where omitting `val` from a `map_put_items`
    // op dict landed in the `Value::Nil` catch-all arm and produced the
    // misleading "map_put_items requires a dict value" error, even though
    // the real bug was a missing top-level `val` key. The fix raises
    // ValueError("map_put_items requires 'val'") before the type check, so
    // the error always names the actual missing key.

    #[test]
    fn map_put_items_missing_val_raises_value_error_with_val_in_message() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("op", super::OP_MAP_PUT_ITEMS).unwrap();
            dict.set_item("bin", "mybin").unwrap();
            // intentionally omit "val"
            let ops = PyList::new(py, [dict]).unwrap();

            let err = super::py_ops_to_rust(&ops)
                .expect_err("map_put_items without 'val' must raise ValueError");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains("map_put_items") && msg.contains("val"),
                "error message should mention 'map_put_items' and 'val' (not just \
                 'requires a dict value'), got: {msg}"
            );
        });
    }

    #[test]
    fn map_put_items_with_dict_val_succeeds() {
        Python::initialize();
        Python::attach(|py| {
            let dict = PyDict::new(py);
            dict.set_item("op", super::OP_MAP_PUT_ITEMS).unwrap();
            dict.set_item("bin", "mybin").unwrap();
            let items = PyDict::new(py);
            items.set_item("a", 1i64).unwrap();
            items.set_item("b", 2i64).unwrap();
            dict.set_item("val", items).unwrap();
            let ops = PyList::new(py, [dict]).unwrap();

            let converted = super::py_ops_to_rust(&ops)
                .expect("map_put_items with explicit dict val must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    // ── list/map BY_VALUE ops: missing `val` must error, not silently Nil ──
    //
    // Regression for the bug where the OP_LIST_GET_BY_VALUE,
    // OP_LIST_GET_BY_VALUE_LIST, OP_LIST_REMOVE_BY_VALUE,
    // OP_LIST_REMOVE_BY_VALUE_LIST, OP_MAP_GET_BY_VALUE, OP_MAP_REMOVE_BY_VALUE
    // and OP_MAP_REMOVE_BY_VALUE_LIST arms defaulted a missing `val` key to
    // `Value::Nil`. For the singular-value variants the dispatch quietly
    // queried the bin for `Nil` matches; for the `_list` variants
    // `values_from_list(&Nil)` collapsed to `[Nil]`, so the op also matched
    // against a single nonsense value. In both cases the call returned an
    // empty result the caller could not distinguish from a genuinely missing
    // record. The fix raises ValueError("<op> requires 'val'") instead, so
    // callers building op dicts directly get a clear failure.
    //
    // The `*_BY_VALUE_RANGE` and `*_BY_KEY_RANGE` arms are intentionally NOT
    // covered here — distinguishing a missing key from `val=None` (unbounded
    // begin) needs a separate `val` extractor and is deferred.

    /// Build a single list/map BY_VALUE op dict with the given op code,
    /// optionally setting `val` to an arbitrary Python int. The `return_type`
    /// key is always set so the arm's `get_return_type` call succeeds.
    fn build_by_value_op_dict<'py>(
        py: Python<'py>,
        op_code: i32,
        with_val: Option<i64>,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("op", op_code).unwrap();
        dict.set_item("bin", "mybin").unwrap();
        dict.set_item("return_type", 0i32).unwrap();
        if let Some(v) = with_val {
            dict.set_item("val", v).unwrap();
        }
        dict
    }

    /// Build a single list/map BY_VALUE_LIST op dict, optionally setting `val`
    /// to a Python list of ints.
    fn build_by_value_list_op_dict<'py>(
        py: Python<'py>,
        op_code: i32,
        with_val: Option<Vec<i64>>,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("op", op_code).unwrap();
        dict.set_item("bin", "mybin").unwrap();
        dict.set_item("return_type", 0i32).unwrap();
        if let Some(items) = with_val {
            let list = PyList::new(py, items).unwrap();
            dict.set_item("val", list).unwrap();
        }
        dict
    }

    fn assert_by_value_op_missing_val_errors(op_code: i32, op_name: &str) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_by_value_op_dict(py, op_code, None);
            let ops = PyList::new(py, [dict]).unwrap();
            let err = super::py_ops_to_rust(&ops)
                .expect_err("missing 'val' must raise ValueError, not silently become Nil");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains(op_name) && msg.contains("val"),
                "error message should mention '{op_name}' and 'val', got: {msg}"
            );
        });
    }

    fn assert_by_value_op_with_val_succeeds(op_code: i32) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_by_value_op_dict(py, op_code, Some(42));
            let ops = PyList::new(py, [dict]).unwrap();
            let converted =
                super::py_ops_to_rust(&ops).expect("BY_VALUE op with explicit val must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    fn assert_by_value_list_op_missing_val_errors(op_code: i32, op_name: &str) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_by_value_list_op_dict(py, op_code, None);
            let ops = PyList::new(py, [dict]).unwrap();
            let err = super::py_ops_to_rust(&ops)
                .expect_err("missing 'val' must raise ValueError, not silently become Nil");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(
                msg.contains(op_name) && msg.contains("val"),
                "error message should mention '{op_name}' and 'val', got: {msg}"
            );
        });
    }

    fn assert_by_value_list_op_with_val_succeeds(op_code: i32) {
        Python::initialize();
        Python::attach(|py| {
            let dict = build_by_value_list_op_dict(py, op_code, Some(vec![1, 2, 3]));
            let ops = PyList::new(py, [dict]).unwrap();
            let converted = super::py_ops_to_rust(&ops)
                .expect("BY_VALUE_LIST op with explicit val must succeed");
            assert_eq!(converted.len(), 1);
        });
    }

    #[test]
    fn list_get_by_value_missing_val_raises_value_error() {
        assert_by_value_op_missing_val_errors(super::OP_LIST_GET_BY_VALUE, "list_get_by_value");
        assert_by_value_op_with_val_succeeds(super::OP_LIST_GET_BY_VALUE);
    }

    #[test]
    fn list_get_by_value_list_missing_val_raises_value_error() {
        assert_by_value_list_op_missing_val_errors(
            super::OP_LIST_GET_BY_VALUE_LIST,
            "list_get_by_value_list",
        );
        assert_by_value_list_op_with_val_succeeds(super::OP_LIST_GET_BY_VALUE_LIST);
    }

    #[test]
    fn list_remove_by_value_missing_val_raises_value_error() {
        assert_by_value_op_missing_val_errors(
            super::OP_LIST_REMOVE_BY_VALUE,
            "list_remove_by_value",
        );
        assert_by_value_op_with_val_succeeds(super::OP_LIST_REMOVE_BY_VALUE);
    }

    #[test]
    fn list_remove_by_value_list_missing_val_raises_value_error() {
        assert_by_value_list_op_missing_val_errors(
            super::OP_LIST_REMOVE_BY_VALUE_LIST,
            "list_remove_by_value_list",
        );
        assert_by_value_list_op_with_val_succeeds(super::OP_LIST_REMOVE_BY_VALUE_LIST);
    }

    #[test]
    fn map_get_by_value_missing_val_raises_value_error() {
        assert_by_value_op_missing_val_errors(super::OP_MAP_GET_BY_VALUE, "map_get_by_value");
        assert_by_value_op_with_val_succeeds(super::OP_MAP_GET_BY_VALUE);
    }

    #[test]
    fn map_remove_by_value_missing_val_raises_value_error() {
        assert_by_value_op_missing_val_errors(super::OP_MAP_REMOVE_BY_VALUE, "map_remove_by_value");
        assert_by_value_op_with_val_succeeds(super::OP_MAP_REMOVE_BY_VALUE);
    }

    #[test]
    fn map_remove_by_value_list_missing_val_raises_value_error() {
        assert_by_value_list_op_missing_val_errors(
            super::OP_MAP_REMOVE_BY_VALUE_LIST,
            "map_remove_by_value_list",
        );
        assert_by_value_list_op_with_val_succeeds(super::OP_MAP_REMOVE_BY_VALUE_LIST);
    }

    #[test]
    fn map_get_by_value_list_missing_val_raises_value_error() {
        assert_by_value_list_op_missing_val_errors(
            super::OP_MAP_GET_BY_VALUE_LIST,
            "map_get_by_value_list",
        );
        assert_by_value_list_op_with_val_succeeds(super::OP_MAP_GET_BY_VALUE_LIST);
    }
}
