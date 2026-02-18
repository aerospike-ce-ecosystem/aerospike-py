use aerospike_core::expressions::{self, ExpType, Expression};
use aerospike_core::Value;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::types::value::py_to_value;

/// Convert a Python expression dict tree into an aerospike-core Expression.
pub fn py_to_expression(obj: &Bound<'_, PyAny>) -> PyResult<Expression> {
    let dict = obj.cast::<PyDict>().map_err(|_| {
        pyo3::exceptions::PyTypeError::new_err(
            "Expression must be a dict with '__expr__' key (use aerospike_py.exp builder functions)",
        )
    })?;

    let op: String = dict
        .get_item("__expr__")?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(
                "Expression dict missing '__expr__' key. Use aerospike_py.exp builder functions.",
            )
        })?
        .extract()?;

    match op.as_str() {
        // ── Value constructors ──
        "int_val" => Ok(expressions::int_val(get_required(dict, "val")?)),
        "float_val" => Ok(expressions::float_val(get_required(dict, "val")?)),
        "string_val" => Ok(expressions::string_val(get_required::<String>(
            dict, "val",
        )?)),
        "bool_val" => Ok(expressions::bool_val(get_required(dict, "val")?)),
        "blob_val" => Ok(expressions::blob_val(get_required::<Vec<u8>>(dict, "val")?)),
        "list_val" => Ok(expressions::list_val(py_list_to_values(
            &get_required_any(dict, "val")?,
        )?)),
        "map_val" => Ok(expressions::map_val(py_dict_to_hashmap(
            &get_required_any(dict, "val")?,
        )?)),
        "geo_val" => Ok(expressions::geo_val(get_required::<String>(dict, "val")?)),
        "nil" => Ok(expressions::nil()),
        "infinity" => Ok(expressions::infinity()),
        "wildcard" => Ok(expressions::wildcard()),

        // ── Bin accessors ──
        "int_bin" | "float_bin" | "string_bin" | "blob_bin" | "list_bin" | "map_bin"
        | "geo_bin" | "hll_bin" | "bin_exists" | "bin_type" | "bool_bin" => {
            convert_bin_accessor(op.as_str(), dict)
        }

        // ── Record metadata ──
        "key" => Ok(expressions::key(int_to_exp_type(get_required(
            dict, "exp_type",
        )?)?)),
        "key_exists" => Ok(expressions::key_exists()),
        "set_name" => Ok(expressions::set_name()),
        "record_size" => Ok(expressions::record_size()),
        "last_update" => Ok(expressions::last_update()),
        "since_update" => Ok(expressions::since_update()),
        "void_time" => Ok(expressions::void_time()),
        "ttl" => Ok(expressions::ttl()),
        "is_tombstone" => Ok(expressions::is_tombstone()),
        "digest_modulo" => Ok(expressions::digest_modulo(get_required(dict, "modulo")?)),

        // ── Comparison operations (binary: left + right) ──
        "eq" | "ne" | "gt" | "ge" | "lt" | "le" | "geo_compare" => {
            convert_binary_comparison(op.as_str(), dict)
        }

        // ── Logical operations ──
        "not" => Ok(expressions::not(parse_sub_expr(dict, "expr")?)),

        // ── Variadic operations (take Vec<Expression>) ──
        "and" | "or" | "xor" | "num_add" | "num_sub" | "num_mul" | "num_div" | "min" | "max"
        | "int_and" | "int_or" | "int_xor" | "cond" | "let" => {
            convert_variadic_op(op.as_str(), dict)
        }

        // ── Unary operations (take single Expression from "exprs" list) ──
        "num_abs" | "num_floor" | "num_ceil" | "to_int" | "to_float" | "int_not" | "int_count" => {
            convert_unary_op(op.as_str(), dict)
        }

        // ── Binary pair operations (take exactly 2 Expressions from "exprs" list) ──
        "num_mod" | "num_pow" | "num_log" | "int_lshift" | "int_rshift" | "int_arshift"
        | "int_lscan" | "int_rscan" => convert_binary_pair_op(op.as_str(), dict),

        // ── Pattern matching ──
        "regex_compare" => {
            let regex: String = get_required(dict, "regex")?;
            let flags: i64 = get_required(dict, "flags")?;
            let bin_expr = parse_sub_expr(dict, "bin")?;
            Ok(expressions::regex_compare(regex, flags, bin_expr))
        }

        // ── Control flow ──
        "var" => Ok(expressions::var(get_required::<String>(dict, "name")?)),
        "def" => {
            let name: String = get_required(dict, "name")?;
            let value = parse_sub_expr(dict, "value")?;
            Ok(expressions::def(name, value))
        }

        _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Unknown expression type: '{op}'. Use aerospike_py.exp builder functions."
        ))),
    }
}

// ── Dispatch helpers ──────────────────────────────────────────────

/// Convert bin accessor operations that all take a single "name" field.
fn convert_bin_accessor(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let name: String = get_required(dict, "name")?;
    match op {
        "int_bin" => Ok(expressions::int_bin(name)),
        "float_bin" => Ok(expressions::float_bin(name)),
        "string_bin" => Ok(expressions::string_bin(name)),
        "bool_bin" => Ok(expressions::int_bin(name)), // booleans are stored as integers
        "blob_bin" => Ok(expressions::blob_bin(name)),
        "list_bin" => Ok(expressions::list_bin(name)),
        "map_bin" => Ok(expressions::map_bin(name)),
        "geo_bin" => Ok(expressions::geo_bin(name)),
        "hll_bin" => Ok(expressions::hll_bin(name)),
        "bin_exists" => Ok(expressions::bin_exists(name)),
        "bin_type" => Ok(expressions::bin_type(name)),
        _ => unreachable!("convert_bin_accessor called with unexpected op: {op}"),
    }
}

/// Convert binary comparison operations that take "left" and "right" sub-expressions.
fn convert_binary_comparison(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let left = parse_sub_expr(dict, "left")?;
    let right = parse_sub_expr(dict, "right")?;
    match op {
        "eq" => Ok(expressions::eq(left, right)),
        "ne" => Ok(expressions::ne(left, right)),
        "gt" => Ok(expressions::gt(left, right)),
        "ge" => Ok(expressions::ge(left, right)),
        "lt" => Ok(expressions::lt(left, right)),
        "le" => Ok(expressions::le(left, right)),
        "geo_compare" => Ok(expressions::geo_compare(left, right)),
        _ => unreachable!("convert_binary_comparison called with unexpected op: {op}"),
    }
}

/// Convert variadic operations that take a Vec<Expression> from "exprs".
fn convert_variadic_op(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let exprs = parse_sub_expr_list(dict, "exprs")?;
    match op {
        "and" => Ok(expressions::and(exprs)),
        "or" => Ok(expressions::or(exprs)),
        "xor" => Ok(expressions::xor(exprs)),
        "num_add" => Ok(expressions::num_add(exprs)),
        "num_sub" => Ok(expressions::num_sub(exprs)),
        "num_mul" => Ok(expressions::num_mul(exprs)),
        "num_div" => Ok(expressions::num_div(exprs)),
        "min" => Ok(expressions::min(exprs)),
        "max" => Ok(expressions::max(exprs)),
        "int_and" => Ok(expressions::int_and(exprs)),
        "int_or" => Ok(expressions::int_or(exprs)),
        "int_xor" => Ok(expressions::int_xor(exprs)),
        "cond" => Ok(expressions::cond(exprs)),
        "let" => Ok(expressions::exp_let(exprs)),
        _ => unreachable!("convert_variadic_op called with unexpected op: {op}"),
    }
}

/// Convert unary operations that take a single Expression from "exprs" list.
fn convert_unary_op(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let exprs = parse_sub_expr_list(dict, "exprs")?;
    let expr = exprs.into_iter().next().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "{op} requires at least 1 expression in 'exprs'"
        ))
    })?;
    match op {
        "num_abs" => Ok(expressions::num_abs(expr)),
        "num_floor" => Ok(expressions::num_floor(expr)),
        "num_ceil" => Ok(expressions::num_ceil(expr)),
        "to_int" => Ok(expressions::to_int(expr)),
        "to_float" => Ok(expressions::to_float(expr)),
        "int_not" => Ok(expressions::int_not(expr)),
        "int_count" => Ok(expressions::int_count(expr)),
        _ => unreachable!("convert_unary_op called with unexpected op: {op}"),
    }
}

/// Convert binary pair operations that take exactly 2 Expressions from "exprs" list.
fn convert_binary_pair_op(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let exprs = parse_sub_expr_list(dict, "exprs")?;
    if exprs.len() != 2 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "{op} requires exactly 2 expressions, got {}",
            exprs.len()
        )));
    }
    let mut iter = exprs.into_iter();
    let first = iter.next().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("{op}: missing first expression"))
    })?;
    let second = iter.next().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("{op}: missing second expression"))
    })?;
    match op {
        "num_mod" => Ok(expressions::num_mod(first, second)),
        "num_pow" => Ok(expressions::num_pow(first, second)),
        "num_log" => Ok(expressions::num_log(first, second)),
        "int_lshift" => Ok(expressions::int_lshift(first, second)),
        "int_rshift" => Ok(expressions::int_rshift(first, second)),
        "int_arshift" => Ok(expressions::int_arshift(first, second)),
        "int_lscan" => Ok(expressions::int_lscan(first, second)),
        "int_rscan" => Ok(expressions::int_rscan(first, second)),
        _ => unreachable!("convert_binary_pair_op called with unexpected op: {op}"),
    }
}

// ── Field extraction helpers ──────────────────────────────────────

fn get_required<'py, T: for<'a> FromPyObject<'a, 'py, Error = PyErr>>(
    dict: &Bound<'py, PyDict>,
    key: &str,
) -> PyResult<T> {
    dict.get_item(key)?
        .ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Expression missing required field: '{key}'"
            ))
        })?
        .extract()
}

fn get_required_any<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?.ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!(
            "Expression missing required field: '{key}'"
        ))
    })
}

fn parse_sub_expr(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Expression> {
    let obj = get_required_any(dict, key)?;
    py_to_expression(&obj)
}

fn parse_sub_expr_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<Expression>> {
    let obj = get_required_any(dict, key)?;
    let list = obj.cast::<PyList>().map_err(|_| {
        pyo3::exceptions::PyTypeError::new_err(format!("'{key}' must be a list of expressions"))
    })?;
    let mut result = Vec::with_capacity(list.len());
    for item in list.iter() {
        result.push(py_to_expression(&item)?);
    }
    Ok(result)
}

fn int_to_exp_type(val: i64) -> PyResult<ExpType> {
    match val {
        0 => Ok(ExpType::NIL),
        1 => Ok(ExpType::BOOL),
        2 => Ok(ExpType::INT),
        3 => Ok(ExpType::STRING),
        4 => Ok(ExpType::LIST),
        5 => Ok(ExpType::MAP),
        6 => Ok(ExpType::BLOB),
        7 => Ok(ExpType::FLOAT),
        8 => Ok(ExpType::GEO),
        9 => Ok(ExpType::HLL),
        _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Invalid ExpType value: {val}. Expected 0-9."
        ))),
    }
}

fn py_list_to_values(obj: &Bound<'_, PyAny>) -> PyResult<Vec<Value>> {
    let list = obj
        .cast::<PyList>()
        .map_err(|_| pyo3::exceptions::PyTypeError::new_err("Expected a list for list_val"))?;
    let mut values = Vec::with_capacity(list.len());
    for item in list.iter() {
        values.push(py_to_value(&item)?);
    }
    Ok(values)
}

fn py_dict_to_hashmap(obj: &Bound<'_, PyAny>) -> PyResult<std::collections::HashMap<Value, Value>> {
    let dict = obj
        .cast::<PyDict>()
        .map_err(|_| pyo3::exceptions::PyTypeError::new_err("Expected a dict for map_val"))?;
    let mut map = std::collections::HashMap::new();
    for (k, v) in dict.iter() {
        map.insert(py_to_value(&k)?, py_to_value(&v)?);
    }
    Ok(map)
}

/// Check if a Python object is an expression dict (has "__expr__" key).
pub fn is_expression(obj: &Bound<'_, PyAny>) -> bool {
    if let Ok(dict) = obj.cast::<PyDict>() {
        dict.get_item("__expr__").ok().flatten().is_some()
    } else {
        false
    }
}
