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
        "int_val" => {
            let val: i64 = get_required(dict, "val")?;
            Ok(expressions::int_val(val))
        }
        "float_val" => {
            let val: f64 = get_required(dict, "val")?;
            Ok(expressions::float_val(val))
        }
        "string_val" => {
            let val: String = get_required(dict, "val")?;
            Ok(expressions::string_val(val))
        }
        "bool_val" => {
            let val: bool = get_required(dict, "val")?;
            Ok(expressions::bool_val(val))
        }
        "blob_val" => {
            let val: Vec<u8> = get_required(dict, "val")?;
            Ok(expressions::blob_val(val))
        }
        "list_val" => {
            let py_list = get_required_any(dict, "val")?;
            let values = py_list_to_values(&py_list)?;
            Ok(expressions::list_val(values))
        }
        "map_val" => {
            let py_dict = get_required_any(dict, "val")?;
            let map = py_dict_to_hashmap(&py_dict)?;
            Ok(expressions::map_val(map))
        }
        "geo_val" => {
            let val: String = get_required(dict, "val")?;
            Ok(expressions::geo_val(val))
        }
        "nil" => Ok(expressions::nil()),
        "infinity" => Ok(expressions::infinity()),
        "wildcard" => Ok(expressions::wildcard()),

        // ── Bin accessors ──
        "int_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::int_bin(name))
        }
        "float_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::float_bin(name))
        }
        "string_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::string_bin(name))
        }
        "bool_bin" => {
            // aerospike-core doesn't have a dedicated bool_bin; use int_bin (booleans are stored as integers)
            let name: String = get_required(dict, "name")?;
            Ok(expressions::int_bin(name))
        }
        "blob_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::blob_bin(name))
        }
        "list_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::list_bin(name))
        }
        "map_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::map_bin(name))
        }
        "geo_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::geo_bin(name))
        }
        "hll_bin" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::hll_bin(name))
        }
        "bin_exists" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::bin_exists(name))
        }
        "bin_type" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::bin_type(name))
        }

        // ── Record metadata ──
        "key" => {
            let exp_type: i64 = get_required(dict, "exp_type")?;
            Ok(expressions::key(int_to_exp_type(exp_type)?))
        }
        "key_exists" => Ok(expressions::key_exists()),
        "set_name" => Ok(expressions::set_name()),
        "record_size" => Ok(expressions::record_size()),
        "last_update" => Ok(expressions::last_update()),
        "since_update" => Ok(expressions::since_update()),
        "void_time" => Ok(expressions::void_time()),
        "ttl" => Ok(expressions::ttl()),
        "is_tombstone" => Ok(expressions::is_tombstone()),
        "digest_modulo" => {
            let modulo: i64 = get_required(dict, "modulo")?;
            Ok(expressions::digest_modulo(modulo))
        }

        // ── Comparison operations ──
        "eq" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::eq(left, right))
        }
        "ne" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::ne(left, right))
        }
        "gt" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::gt(left, right))
        }
        "ge" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::ge(left, right))
        }
        "lt" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::lt(left, right))
        }
        "le" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::le(left, right))
        }

        // ── Logical operations ──
        "and" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::and(exprs))
        }
        "or" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::or(exprs))
        }
        "not" => {
            let expr = parse_sub_expr(dict, "expr")?;
            Ok(expressions::not(expr))
        }
        "xor" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::xor(exprs))
        }

        // ── Numeric operations ──
        "num_add" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_add(exprs))
        }
        "num_sub" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_sub(exprs))
        }
        "num_mul" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_mul(exprs))
        }
        "num_div" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_div(exprs))
        }
        "num_mod" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            if exprs.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "num_mod requires exactly 2 expressions (numerator, denominator)",
                ));
            }
            let mut iter = exprs.into_iter();
            Ok(expressions::num_mod(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "num_pow" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            if exprs.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "num_pow requires exactly 2 expressions (base, exponent)",
                ));
            }
            let mut iter = exprs.into_iter();
            Ok(expressions::num_pow(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "num_log" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            if exprs.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "num_log requires exactly 2 expressions (num, base)",
                ));
            }
            let mut iter = exprs.into_iter();
            Ok(expressions::num_log(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "num_abs" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_abs(exprs.into_iter().next().unwrap()))
        }
        "num_floor" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_floor(exprs.into_iter().next().unwrap()))
        }
        "num_ceil" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::num_ceil(exprs.into_iter().next().unwrap()))
        }
        "to_int" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::to_int(exprs.into_iter().next().unwrap()))
        }
        "to_float" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::to_float(exprs.into_iter().next().unwrap()))
        }
        "min" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::min(exprs))
        }
        "max" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::max(exprs))
        }

        // ── Integer bitwise operations ──
        "int_and" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::int_and(exprs))
        }
        "int_or" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::int_or(exprs))
        }
        "int_xor" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::int_xor(exprs))
        }
        "int_not" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::int_not(exprs.into_iter().next().unwrap()))
        }
        "int_lshift" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            let mut iter = exprs.into_iter();
            Ok(expressions::int_lshift(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "int_rshift" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            let mut iter = exprs.into_iter();
            Ok(expressions::int_rshift(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "int_arshift" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            let mut iter = exprs.into_iter();
            Ok(expressions::int_arshift(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "int_count" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::int_count(exprs.into_iter().next().unwrap()))
        }
        "int_lscan" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            let mut iter = exprs.into_iter();
            Ok(expressions::int_lscan(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }
        "int_rscan" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            let mut iter = exprs.into_iter();
            Ok(expressions::int_rscan(
                iter.next().unwrap(),
                iter.next().unwrap(),
            ))
        }

        // ── Pattern matching ──
        "regex_compare" => {
            let regex: String = get_required(dict, "regex")?;
            let flags: i64 = get_required(dict, "flags")?;
            let bin_expr = parse_sub_expr(dict, "bin")?;
            Ok(expressions::regex_compare(regex, flags, bin_expr))
        }
        "geo_compare" => {
            let left = parse_sub_expr(dict, "left")?;
            let right = parse_sub_expr(dict, "right")?;
            Ok(expressions::geo_compare(left, right))
        }

        // ── Control flow ──
        "cond" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::cond(exprs))
        }
        "var" => {
            let name: String = get_required(dict, "name")?;
            Ok(expressions::var(name))
        }
        "def" => {
            let name: String = get_required(dict, "name")?;
            let value = parse_sub_expr(dict, "value")?;
            Ok(expressions::def(name, value))
        }
        "let" => {
            let exprs = parse_sub_expr_list(dict, "exprs")?;
            Ok(expressions::exp_let(exprs))
        }

        _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Unknown expression type: '{op}'. Use aerospike_py.exp builder functions."
        ))),
    }
}

// ── Helpers ────────────────────────────────────────────────────────

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
