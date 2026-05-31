//! Conversion of Python expression dict trees to `aerospike_core::Expression`.
//!
//! Expressions are represented in Python as nested dicts with an `"__expr__"` key
//! identifying the expression type (e.g. `"eq"`, `"int_bin"`, `"and"`).
//! The `aerospike_py.exp` Python module provides builder functions that produce
//! these dicts; this module recursively converts them to Rust `Expression` values.

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
    crate::query::validate_bin_name(&name)?;
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
        _ => crate::bug_report::internal_bug!(
            "expressions::convert_bin_accessor",
            "unexpected op: {op}"
        ),
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
        _ => crate::bug_report::internal_bug!(
            "expressions::convert_binary_comparison",
            "unexpected op: {op}"
        ),
    }
}

/// Convert variadic operations that take a Vec<Expression> from "exprs".
///
/// Every operation in this group requires at least one operand. An empty
/// `exprs` list (e.g. from a no-argument `exp.and_()` / `exp.num_add()` call)
/// produces a structurally invalid expression: the underlying `aerospike-core`
/// builders emit an empty argument sequence that the server rejects with an
/// opaque parse error far from the call site. Reject it eagerly here with a
/// precise message, in the same spirit as the arity guards already applied to
/// unary (`convert_unary_op`) and binary-pair (`convert_binary_pair_op`)
/// operations — using the more specific `InvalidArgError` for this
/// argument-validation failure (those siblings raise a plain `ValueError`).
///
/// `cond` and `let` additionally carry a structural operand shape (an odd
/// `cond` chain of `(condition, action)` pairs plus a default; a `let` body of
/// definitions plus a scope expression) that is likewise validated here.
fn convert_variadic_op(op: &str, dict: &Bound<'_, PyDict>) -> PyResult<Expression> {
    let exprs = parse_sub_expr_list(dict, "exprs")?;
    if exprs.is_empty() {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "Expression '{op}' requires at least one operand, got an empty 'exprs' list"
        )));
    }
    // `cond` and `let` are not simple "one or more operands" ops: they carry a
    // structural shape that the underlying `aerospike-core` builder does not
    // validate, so a malformed operand count is only rejected later by the
    // server with an opaque parse error far from the call site.
    //
    // `cond(bool1, action1, ..., default)` requires pairs of (condition,
    // action) followed by a single default action — i.e. an odd count of at
    // least 3. An even count leaves a dangling condition with no action; a
    // count of 1 is a bare default with no condition.
    if op == "cond" && (exprs.len() < 3 || exprs.len() % 2 == 0) {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "Expression 'cond' requires an odd number of operands (>= 3): pairs of \
             (condition, action) followed by a default action, got {} operand(s)",
            exprs.len()
        )));
    }
    // `let(def1, def2, ..., scope_expr)` requires at least one variable
    // definition followed by a scope expression — i.e. at least 2 operands.
    if op == "let" && exprs.len() < 2 {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "Expression 'let' requires at least 2 operands: one or more variable \
             definitions followed by a scope expression, got {} operand(s)",
            exprs.len()
        )));
    }
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
        _ => crate::bug_report::internal_bug!(
            "expressions::convert_variadic_op",
            "unexpected op: {op}"
        ),
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
        _ => {
            crate::bug_report::internal_bug!("expressions::convert_unary_op", "unexpected op: {op}")
        }
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
        _ => crate::bug_report::internal_bug!(
            "expressions::convert_binary_pair_op",
            "unexpected op: {op}"
        ),
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

/// Map a Python integer to an [`ExpType`] enum variant used by key expressions.
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a `{"__expr__": op, "exprs": [...]}` dict from a list of operand
    /// expression dicts.
    fn variadic_dict<'py>(
        py: Python<'py>,
        op: &str,
        operands: Vec<Bound<'py, PyDict>>,
    ) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("__expr__", op).unwrap();
        let list = PyList::empty(py);
        for o in operands {
            list.append(o).unwrap();
        }
        dict.set_item("exprs", list).unwrap();
        dict
    }

    /// A simple `int_val` leaf operand to populate variadic operand lists.
    fn int_val_dict(py: Python<'_>, n: i64) -> Bound<'_, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("__expr__", "int_val").unwrap();
        dict.set_item("val", n).unwrap();
        dict
    }

    /// Every variadic op with an empty `exprs` list must raise `InvalidArgError`
    /// instead of constructing a malformed expression that the server rejects
    /// far from the call site.
    #[test]
    fn empty_variadic_exprs_raise_invalid_arg() {
        Python::initialize();
        Python::attach(|py| {
            for op in [
                "and", "or", "xor", "num_add", "num_sub", "num_mul", "num_div", "min", "max",
                "int_and", "int_or", "int_xor", "cond", "let",
            ] {
                let dict = variadic_dict(py, op, vec![]);
                let err = py_to_expression(dict.as_any())
                    .expect_err(&format!("empty '{op}' must be rejected"));
                assert!(
                    err.is_instance_of::<crate::errors::InvalidArgError>(py),
                    "empty '{op}' must raise InvalidArgError, got {err:?}"
                );
                assert!(
                    err.to_string().contains("at least one operand"),
                    "empty '{op}' error must mention the arity requirement"
                );
            }
        });
    }

    /// A non-empty variadic op still converts successfully (the guard does not
    /// reject legitimate expressions).
    #[test]
    fn non_empty_variadic_exprs_convert() {
        Python::initialize();
        Python::attach(|py| {
            let dict = variadic_dict(
                py,
                "num_add",
                vec![int_val_dict(py, 1), int_val_dict(py, 2)],
            );
            py_to_expression(dict.as_any()).expect("non-empty num_add should convert");
        });
    }

    /// `cond` requires an odd number of operands (>= 3): pairs of
    /// `(condition, action)` followed by a default action. A count of 1, or any
    /// even count, is structurally malformed and must be rejected client-side.
    #[test]
    fn cond_rejects_non_odd_or_too_few_operands() {
        Python::initialize();
        Python::attach(|py| {
            // 1 operand (bare default, no condition) and 2/4 operands (dangling
            // condition with no action) are all invalid.
            for n in [1usize, 2, 4] {
                let operands: Vec<_> = (0..n).map(|i| int_val_dict(py, i as i64)).collect();
                let dict = variadic_dict(py, "cond", operands);
                let err = py_to_expression(dict.as_any())
                    .expect_err(&format!("cond with {n} operand(s) must be rejected"));
                assert!(
                    err.is_instance_of::<crate::errors::InvalidArgError>(py),
                    "cond with {n} operand(s) must raise InvalidArgError, got {err:?}"
                );
                assert!(
                    err.to_string().contains("odd number of operands"),
                    "cond arity error must mention the odd-count requirement: {err:?}"
                );
            }
        });
    }

    /// A well-formed `cond` (odd count >= 3) still converts successfully.
    #[test]
    fn cond_accepts_odd_operand_count() {
        Python::initialize();
        Python::attach(|py| {
            for n in [3usize, 5] {
                let operands: Vec<_> = (0..n).map(|i| int_val_dict(py, i as i64)).collect();
                let dict = variadic_dict(py, "cond", operands);
                py_to_expression(dict.as_any())
                    .unwrap_or_else(|e| panic!("cond with {n} operands should convert: {e:?}"));
            }
        });
    }

    /// `let` requires at least 2 operands: one or more variable definitions
    /// followed by a scope expression. A single operand is malformed.
    #[test]
    fn let_rejects_single_operand() {
        Python::initialize();
        Python::attach(|py| {
            let dict = variadic_dict(py, "let", vec![int_val_dict(py, 1)]);
            let err = py_to_expression(dict.as_any())
                .expect_err("let with a single operand must be rejected");
            assert!(
                err.is_instance_of::<crate::errors::InvalidArgError>(py),
                "single-operand let must raise InvalidArgError, got {err:?}"
            );
            assert!(
                err.to_string().contains("at least 2 operands"),
                "let arity error must mention the 2-operand requirement: {err:?}"
            );
        });
    }

    /// A well-formed `let` (>= 2 operands) still converts successfully.
    #[test]
    fn let_accepts_two_or_more_operands() {
        Python::initialize();
        Python::attach(|py| {
            let dict = variadic_dict(py, "let", vec![int_val_dict(py, 1), int_val_dict(py, 2)]);
            py_to_expression(dict.as_any()).expect("two-operand let should convert");
        });
    }

    /// Build a bin-accessor dict `{"__expr__": op, "name": name}`.
    fn bin_accessor_dict<'py>(py: Python<'py>, op: &str, name: &str) -> Bound<'py, PyDict> {
        let dict = PyDict::new(py);
        dict.set_item("__expr__", op).unwrap();
        dict.set_item("name", name).unwrap();
        dict
    }

    /// A bin-accessor expression with an empty bin name must be rejected
    /// client-side with `InvalidArgError`, instead of being forwarded to the
    /// server where it fails far from the call site.
    #[test]
    fn bin_accessor_rejects_empty_bin_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = bin_accessor_dict(py, "int_bin", "");
            let err = py_to_expression(dict.as_any())
                .expect_err("empty bin name must be rejected for int_bin");
            assert!(
                err.is_instance_of::<crate::errors::InvalidArgError>(py),
                "empty bin name must raise InvalidArgError, got {err:?}"
            );
            assert!(
                err.to_string().contains("Bin name"),
                "error must mention the bin name: {err:?}"
            );
        });
    }

    /// A bin-accessor expression with a non-empty bin name still converts.
    #[test]
    fn bin_accessor_accepts_non_empty_bin_name() {
        Python::initialize();
        Python::attach(|py| {
            let dict = bin_accessor_dict(py, "int_bin", "age");
            py_to_expression(dict.as_any()).expect("non-empty bin name must convert");
        });
    }
}
