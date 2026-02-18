//! Conversion of Python operation dicts to `aerospike_core::Operation` values.
//!
//! Each operation is represented as a Python dict with at minimum an `"op"` key
//! (integer operation code). This module dispatches on that code to construct
//! the corresponding Rust `Operation` for basic CRUD, List CDT, and Map CDT ops.

use aerospike_core::{
    operations,
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

/// Unwrap a `Value::List` into its inner `Vec`, or wrap a single value in a `Vec`.
fn values_from_list(val: &Value) -> Vec<Value> {
    match val {
        Value::List(v) => v.clone(),
        _ => vec![val.clone()],
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
                let v = val.unwrap_or(Value::Int(1));
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
                let count = get_count(dict)?.unwrap_or(0);
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
                let v = val.unwrap_or(Value::Nil);
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
                let v = val.unwrap_or(Value::Nil);
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
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_list_return_type(get_return_type(dict)?);
                list_ops::remove_by_value(&name, v, rt)
            }
            OP_LIST_REMOVE_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "list_remove_by_value_list")?;
                let v = val.unwrap_or(Value::Nil);
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
                let v: i64 = match &val {
                    Some(Value::Int(i)) => *i,
                    _ => 1,
                };
                list_ops::increment(&policy, &name, index, v)
            }
            OP_LIST_SORT => {
                let name = require_bin(&bin_name, "list_sort")?;
                let flags: i32 = match &val {
                    Some(Value::Int(i)) => *i as i32,
                    _ => 0,
                };
                let sort_flags = match flags {
                    2 => ListSortFlags::DropDuplicates,
                    _ => ListSortFlags::Default,
                };
                list_ops::sort(&name, sort_flags)
            }
            OP_LIST_SET_ORDER => {
                let name = require_bin(&bin_name, "list_set_order")?;
                let order: i32 = match &val {
                    Some(Value::Int(i)) => *i as i32,
                    _ => 0,
                };
                let order_type = match order {
                    1 => ListOrderType::Ordered,
                    _ => ListOrderType::Unordered,
                };
                list_ops::set_order(&name, order_type, vec![])
            }

            // ── Map CDT operations ───────────────────────────
            OP_MAP_SET_ORDER => {
                let name = require_bin(&bin_name, "map_set_order")?;
                let order: i32 = match &val {
                    Some(Value::Int(i)) => *i as i32,
                    _ => 0,
                };
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
                let v = val.unwrap_or(Value::Nil);
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
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::remove_by_value(&name, v, rt)
            }
            OP_MAP_REMOVE_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "map_remove_by_value_list")?;
                let v = val.unwrap_or(Value::Nil);
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
                let count = get_count(dict)?.unwrap_or(1);
                map_ops::remove_by_index_range(&name, index, count, rt)
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
                let count = get_count(dict)?.unwrap_or(1);
                map_ops::remove_by_rank_range(&name, rank, count, rt)
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
                let v = val.unwrap_or(Value::Nil);
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
                let count = get_count(dict)?.unwrap_or(1);
                map_ops::get_by_index_range(&name, index, count, rt)
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
                let count = get_count(dict)?.unwrap_or(1);
                map_ops::get_by_rank_range(&name, rank, count, rt)
            }
            OP_MAP_GET_BY_KEY_LIST => {
                let name = require_bin(&bin_name, "map_get_by_key_list")?;
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_key_list(&name, values_from_list(&v), rt)
            }
            OP_MAP_GET_BY_VALUE_LIST => {
                let name = require_bin(&bin_name, "map_get_by_value_list")?;
                let v = val.unwrap_or(Value::Nil);
                let rt = int_to_map_return_type(get_return_type(dict)?);
                map_ops::get_by_value_list(&name, values_from_list(&v), rt)
            }

            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "Unsupported operation code: {op_code}. Supported codes: \
                     READ={OP_READ}, WRITE={OP_WRITE}, INCR={OP_INCR}, \
                     APPEND={OP_APPEND}, PREPEND={OP_PREPEND}, TOUCH={OP_TOUCH}, DELETE={OP_DELETE}, \
                     List CDT=1001-1031, Map CDT=2001-2027"
                )));
            }
        };

        rust_ops.push(op);
    }

    Ok(rust_ops)
}
