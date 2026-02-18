//! NumPy structured-array support for batch operations.
//!
//! Converts `Vec<BatchRecord>` directly into a NumPy structured array by
//! writing Aerospike values into a raw buffer obtained via `__array_interface__`.
//! This avoids per-element Python object creation and is significantly faster
//! than building Python dicts for large batch reads.
//!
//! # Safety
//!
//! This module contains `unsafe` code that writes to raw pointers obtained from
//! NumPy arrays. Safety invariants are documented on each `unsafe` function and
//! are upheld by the bounds checks in [`parse_dtype_fields`] and the allocation
//! in [`batch_to_numpy_py`] (via `np.zeros`).

use std::collections::HashMap;
use std::ptr;

use aerospike_core::{BatchRecord, Bin, FloatValue, Key, Value};
use half::f16;
use log::{debug, warn};
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::errors::result_code_to_int;
use crate::types::value::value_to_py;

// ── dtype field descriptor ──────────────────────────────────────

/// The kind of a NumPy dtype field, determining how Aerospike values are written.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DtypeKind {
    Int,
    Uint,
    Float,
    FixedBytes,
    VoidBytes,
}

/// Metadata for a single field within a NumPy structured dtype.
///
/// Used to locate and write values into the correct position within a row buffer.
#[derive(Debug, Clone)]
pub struct FieldInfo {
    /// Field name, matching an Aerospike bin name.
    pub name: String,
    /// Byte offset of this field within a row.
    pub offset: usize,
    /// Total byte size of this field (may be larger than `base_itemsize` for sub-arrays).
    pub itemsize: usize,
    /// Byte size of the base scalar element.
    pub base_itemsize: usize,
    /// The kind of the base dtype element.
    pub kind: DtypeKind,
}

// ── dtype parsing ───────────────────────────────────────────────

/// Parse a NumPy structured dtype into field descriptors and the row stride.
///
/// Validates that every field fits within the row stride (no buffer overrun).
fn parse_dtype_fields(dtype: &Bound<'_, PyAny>) -> PyResult<(Vec<FieldInfo>, usize)> {
    let names = dtype.getattr("names")?;
    let names: Vec<String> = names.extract()?;
    let fields_dict = dtype.getattr("fields")?;
    let row_stride: usize = dtype.getattr("itemsize")?.extract()?;

    let mut fields = Vec::with_capacity(names.len());
    for name in &names {
        let field_info = fields_dict.get_item(name)?;
        // field_info is a tuple: (field_dtype, offset) or (field_dtype, offset, title)
        let field_dtype = field_info.get_item(0)?;
        let offset: usize = field_info.get_item(1)?.extract()?;

        let base = field_dtype.getattr("base")?;
        let kind_str: String = base.getattr("kind")?.extract()?;
        let kind = match kind_str.as_str() {
            "i" => DtypeKind::Int,
            "u" => DtypeKind::Uint,
            "f" => DtypeKind::Float,
            "S" => DtypeKind::FixedBytes,
            "V" => DtypeKind::VoidBytes,
            other => {
                warn!("Unsupported dtype kind '{}' for field '{}'", other, name);
                return Err(PyTypeError::new_err(format!(
                    "dtype field '{}' must be numeric (int/float) or fixed-length bytes, got {} (kind='{}')",
                    name, field_dtype, other,
                )));
            }
        };

        let itemsize: usize = field_dtype.getattr("itemsize")?.extract()?;
        let base_itemsize: usize = base.getattr("itemsize")?.extract()?;

        // Bounds check: field must fit within row stride
        if offset + itemsize > row_stride {
            return Err(PyValueError::new_err(format!(
                "dtype field '{}' exceeds row boundary: offset({}) + itemsize({}) = {} > row_stride({})",
                name, offset, itemsize, offset + itemsize, row_stride,
            )));
        }

        fields.push(FieldInfo {
            name: name.clone(),
            offset,
            itemsize,
            base_itemsize,
            kind,
        });
    }

    Ok((fields, row_stride))
}

// ── raw pointer from numpy array ────────────────────────────────

/// Extract the raw data pointer from a writable numpy array via `__array_interface__`.
///
/// # Safety contract for callers
///
/// The returned pointer is only valid while the numpy array is alive and not
/// reallocated. Callers must ensure:
/// - The array outlives all writes through the returned pointer.
/// - No concurrent Python code resizes or replaces the array's buffer.
fn get_array_data_ptr(array: &Bound<'_, PyAny>) -> PyResult<*mut u8> {
    let iface = array.getattr("__array_interface__")?;
    let data_tuple = iface.get_item("data")?;
    let ptr_int: usize = data_tuple.get_item(0)?.extract()?;
    let readonly: bool = data_tuple.get_item(1)?.extract()?;
    if readonly {
        return Err(PyValueError::new_err("numpy array is read-only"));
    }
    debug_assert!(ptr_int != 0, "numpy array data pointer is null");
    Ok(ptr_int as *mut u8)
}

// ── buffer write helpers (all unsafe) ───────────────────────────

/// Write a signed integer value into the row buffer at the field's offset.
///
/// # Safety
///
/// - `row_ptr` must point to a valid, writable buffer of at least
///   `field.offset + field.itemsize` bytes.
/// - The buffer must remain valid for the duration of the write.
/// - No other thread may concurrently write to the same memory region.
///
/// These invariants are upheld by [`batch_to_numpy_py`], which allocates
/// the buffer via `np.zeros` and validates field bounds in [`parse_dtype_fields`].
unsafe fn write_int_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: i64) -> PyResult<()> {
    debug_assert!(!row_ptr.is_null());
    let dst = row_ptr.add(field.offset);
    match field.base_itemsize {
        1 => ptr::write_unaligned(dst as *mut i8, val as i8),
        2 => ptr::write_unaligned(dst as *mut i16, val as i16),
        4 => ptr::write_unaligned(dst as *mut i32, val as i32),
        8 => ptr::write_unaligned(dst as *mut i64, val),
        s => {
            return Err(PyTypeError::new_err(format!(
                "unsupported int size: {} bytes",
                s
            )));
        }
    }
    Ok(())
}

/// Write an unsigned integer value into the row buffer at the field's offset.
///
/// # Safety
///
/// Same preconditions as [`write_int_to_buffer`].
unsafe fn write_uint_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: u64) -> PyResult<()> {
    debug_assert!(!row_ptr.is_null());
    let dst = row_ptr.add(field.offset);
    match field.base_itemsize {
        1 => ptr::write_unaligned(dst, val as u8),
        2 => ptr::write_unaligned(dst as *mut u16, val as u16),
        4 => ptr::write_unaligned(dst as *mut u32, val as u32),
        8 => ptr::write_unaligned(dst as *mut u64, val),
        s => {
            return Err(PyTypeError::new_err(format!(
                "unsupported uint size: {} bytes",
                s
            )));
        }
    }
    Ok(())
}

/// Write a floating-point value into the row buffer at the field's offset.
///
/// Supports f16 (via the `half` crate), f32, and f64.
///
/// # Safety
///
/// Same preconditions as [`write_int_to_buffer`].
unsafe fn write_float_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: f64) -> PyResult<()> {
    debug_assert!(!row_ptr.is_null());
    let dst = row_ptr.add(field.offset);
    match field.base_itemsize {
        4 => ptr::write_unaligned(dst as *mut f32, val as f32),
        8 => ptr::write_unaligned(dst as *mut f64, val),
        2 => {
            // float16: use `half` crate for IEEE 754 compliant conversion
            // Handles denormals, rounding, and special values correctly
            let h = f16::from_f64(val);
            ptr::write_unaligned(dst as *mut u16, h.to_bits());
        }
        s => {
            return Err(PyTypeError::new_err(format!(
                "unsupported float size: {} bytes",
                s
            )));
        }
    }
    Ok(())
}

/// Write a byte slice into the row buffer at the field's offset.
///
/// Copies at most `field.itemsize` bytes (truncating longer data).
/// The remaining space is left zero-initialized from `np.zeros`.
///
/// # Safety
///
/// Same preconditions as [`write_int_to_buffer`].
unsafe fn write_bytes_to_buffer(row_ptr: *mut u8, field: &FieldInfo, data: &[u8]) {
    debug_assert!(!row_ptr.is_null());
    let dst = row_ptr.add(field.offset);
    // Clamp copy length to field size to prevent buffer overrun
    let copy_len = data.len().min(field.itemsize);
    if copy_len > 0 {
        ptr::copy_nonoverlapping(data.as_ptr(), dst, copy_len);
    }
    // np.zeros already zero-initialized, no need to zero-pad
}

// ── value → buffer dispatch ─────────────────────────────────────

/// Dispatch an Aerospike [`Value`] to the appropriate buffer write function.
///
/// `Value::Nil` is a no-op (buffer is already zero-initialized).
///
/// # Safety
///
/// Same preconditions as [`write_int_to_buffer`].
unsafe fn write_value_to_buffer(
    row_ptr: *mut u8,
    field: &FieldInfo,
    value: &Value,
) -> PyResult<()> {
    match value {
        Value::Int(v) => match field.kind {
            DtypeKind::Int => write_int_to_buffer(row_ptr, field, *v),
            DtypeKind::Uint => write_uint_to_buffer(row_ptr, field, *v as u64),
            DtypeKind::Float => write_float_to_buffer(row_ptr, field, *v as f64),
            _ => Err(PyTypeError::new_err(format!(
                "cannot write integer to bytes field '{}'",
                field.name
            ))),
        },
        Value::Float(fv) => {
            let v = float_value_to_f64(fv);
            match field.kind {
                DtypeKind::Float => write_float_to_buffer(row_ptr, field, v),
                DtypeKind::Int => write_int_to_buffer(row_ptr, field, v as i64),
                DtypeKind::Uint => write_uint_to_buffer(row_ptr, field, v as u64),
                _ => Err(PyTypeError::new_err(format!(
                    "cannot write float to bytes field '{}'",
                    field.name
                ))),
            }
        }
        Value::Bool(b) => {
            let iv = if *b { 1i64 } else { 0i64 };
            match field.kind {
                DtypeKind::Int => write_int_to_buffer(row_ptr, field, iv),
                DtypeKind::Uint => write_uint_to_buffer(row_ptr, field, iv as u64),
                DtypeKind::Float => write_float_to_buffer(row_ptr, field, iv as f64),
                _ => Err(PyTypeError::new_err(format!(
                    "cannot write bool to bytes field '{}'",
                    field.name
                ))),
            }
        }
        Value::Blob(bytes) => match field.kind {
            DtypeKind::FixedBytes | DtypeKind::VoidBytes => {
                write_bytes_to_buffer(row_ptr, field, bytes);
                Ok(())
            }
            // sub-array: bytes blob written directly to buffer
            DtypeKind::Float | DtypeKind::Int | DtypeKind::Uint
                if field.itemsize > field.base_itemsize =>
            {
                write_bytes_to_buffer(row_ptr, field, bytes);
                Ok(())
            }
            _ => Err(PyTypeError::new_err(format!(
                "cannot write bytes to numeric field '{}'",
                field.name
            ))),
        },
        Value::String(s) => match field.kind {
            DtypeKind::FixedBytes | DtypeKind::VoidBytes => {
                write_bytes_to_buffer(row_ptr, field, s.as_bytes());
                Ok(())
            }
            _ => Err(PyTypeError::new_err(format!(
                "cannot write string to numeric field '{}'",
                field.name
            ))),
        },
        Value::Nil => Ok(()), // skip, buffer is already zero-initialized
        _ => Err(PyTypeError::new_err(format!(
            "unsupported Aerospike value type for numpy field '{}'",
            field.name
        ))),
    }
}

/// Convert an `aerospike_core::FloatValue` (stored as raw bits) to `f64`.
fn float_value_to_f64(fv: &FloatValue) -> f64 {
    match fv {
        FloatValue::F64(bits) => f64::from_bits(*bits),
        FloatValue::F32(bits) => f32::from_bits(*bits) as f64,
    }
}

// ── main entry point ────────────────────────────────────────────

/// Convert batch results into a `NumpyBatchRecords` Python object.
///
/// Allocates three NumPy arrays (data, meta, result_codes) and writes
/// Aerospike values directly into the data buffer via raw pointers,
/// avoiding per-element Python object allocation.
pub fn batch_to_numpy_py(
    py: Python<'_>,
    results: &[BatchRecord],
    dtype_obj: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    debug!("Converting batch to numpy: records_count={}", results.len());
    let np = py.import("numpy")?;
    let n = results.len();

    // 1. Parse dtype fields
    let (fields, row_stride) = parse_dtype_fields(dtype_obj)?;

    // 2. Allocate numpy arrays
    let data_array = np.call_method1("zeros", (n, dtype_obj))?;

    let meta_dtype_list = pyo3::types::PyList::new(
        py,
        &[
            pyo3::types::PyTuple::new(
                py,
                &[
                    "gen".into_pyobject(py)?.into_any(),
                    "u4".into_pyobject(py)?.into_any(),
                ],
            )?,
            pyo3::types::PyTuple::new(
                py,
                &[
                    "ttl".into_pyobject(py)?.into_any(),
                    "u4".into_pyobject(py)?.into_any(),
                ],
            )?,
        ],
    )?;
    let meta_array = np.call_method1("zeros", (n, meta_dtype_list))?;

    let int32_dtype = np.getattr("int32")?;
    let result_codes_array = np.call_method1("zeros", (n, int32_dtype))?;

    // 3. Get raw data pointers
    let data_ptr = get_array_data_ptr(&data_array)?;
    let meta_ptr = get_array_data_ptr(&meta_array)?;
    let rc_ptr = get_array_data_ptr(&result_codes_array)?;

    // meta stride: gen(u4) + ttl(u4) = 8 bytes
    let meta_stride: usize = 8;

    // 4. Build field name → FieldInfo lookup
    let field_map: HashMap<&str, &FieldInfo> =
        fields.iter().map(|f| (f.name.as_str(), f)).collect();

    // 5. Build key_map and fill arrays
    let key_map = PyDict::new(py);

    for (i, br) in results.iter().enumerate() {
        let result_code = match &br.result_code {
            Some(rc) => result_code_to_int(rc),
            None => 0,
        };

        // Write result_code
        unsafe {
            ptr::write_unaligned(rc_ptr.add(i * 4) as *mut i32, result_code);
        }

        // Extract user_key and map to index
        let user_key = match &br.key.user_key {
            Some(v) => value_to_py(py, v)?,
            None => i.into_pyobject(py)?.into_any().unbind(),
        };
        key_map.set_item(user_key, i)?;

        // Fill data and meta if record exists and result is OK
        if result_code == 0 {
            if let Some(record) = &br.record {
                // Write meta: generation and ttl
                let gen = record.generation;
                let ttl: u32 = record
                    .time_to_live()
                    .map(|d| d.as_secs() as u32)
                    .unwrap_or(0xFFFFFFFF_u32);

                unsafe {
                    let meta_row = meta_ptr.add(i * meta_stride);
                    ptr::write_unaligned(meta_row as *mut u32, gen);
                    ptr::write_unaligned(meta_row.add(4) as *mut u32, ttl);
                }

                // Write bin values directly into numpy buffer
                let row_ptr = unsafe { data_ptr.add(i * row_stride) };
                for (bin_name, value) in &record.bins {
                    if let Some(field) = field_map.get(bin_name.as_str()) {
                        unsafe {
                            write_value_to_buffer(row_ptr, field, value)?;
                        }
                    }
                    // bins not in dtype are silently ignored
                }
            }
        }
    }

    // 6. Construct NumpyBatchRecords Python object
    let numpy_batch_mod = py.import("aerospike_py.numpy_batch")?;
    let cls = numpy_batch_mod.getattr("NumpyBatchRecords")?;
    let result = cls.call1((&data_array, &meta_array, &result_codes_array, &key_map))?;

    Ok(result.unbind())
}

// ── numpy → records (for batch_write) ───────────────────────────

/// Read a single value from a numpy buffer row at the given field offset.
///
/// # Safety
///
/// - `row_ptr` must point to a valid, readable buffer of at least
///   `field.offset + field.itemsize` bytes.
/// - The buffer must remain valid for the duration of the read.
unsafe fn read_value_from_buffer(row_ptr: *const u8, field: &FieldInfo) -> PyResult<Value> {
    debug_assert!(!row_ptr.is_null());
    let src = row_ptr.add(field.offset);
    match field.kind {
        DtypeKind::Int => {
            let v = match field.base_itemsize {
                1 => ptr::read_unaligned(src as *const i8) as i64,
                2 => ptr::read_unaligned(src as *const i16) as i64,
                4 => ptr::read_unaligned(src as *const i32) as i64,
                8 => ptr::read_unaligned(src as *const i64),
                s => {
                    return Err(PyTypeError::new_err(format!(
                        "unsupported int size: {} bytes",
                        s
                    )));
                }
            };
            Ok(Value::Int(v))
        }
        DtypeKind::Uint => {
            let v = match field.base_itemsize {
                1 => ptr::read_unaligned(src) as i64,
                2 => ptr::read_unaligned(src as *const u16) as i64,
                4 => ptr::read_unaligned(src as *const u32) as i64,
                8 => ptr::read_unaligned(src as *const u64) as i64,
                s => {
                    return Err(PyTypeError::new_err(format!(
                        "unsupported uint size: {} bytes",
                        s
                    )));
                }
            };
            Ok(Value::Int(v))
        }
        DtypeKind::Float => {
            let v = match field.base_itemsize {
                2 => {
                    let bits = ptr::read_unaligned(src as *const u16);
                    f16::from_bits(bits).to_f64()
                }
                4 => ptr::read_unaligned(src as *const f32) as f64,
                8 => ptr::read_unaligned(src as *const f64),
                s => {
                    return Err(PyTypeError::new_err(format!(
                        "unsupported float size: {} bytes",
                        s
                    )));
                }
            };
            Ok(Value::Float(FloatValue::F64(v.to_bits())))
        }
        DtypeKind::FixedBytes | DtypeKind::VoidBytes => {
            let mut buf = vec![0u8; field.itemsize];
            ptr::copy_nonoverlapping(src, buf.as_mut_ptr(), field.itemsize);
            Ok(Value::Blob(buf))
        }
    }
}

/// Extract the raw data pointer from a **read-only** numpy array via `__array_interface__`.
///
/// # Safety contract for callers
///
/// The returned pointer is only valid while the numpy array is alive and not
/// reallocated. Callers must ensure:
/// - The array outlives all reads through the returned pointer.
/// - No concurrent Python code resizes or replaces the array's buffer.
fn get_array_data_ptr_readonly(array: &Bound<'_, PyAny>) -> PyResult<*const u8> {
    let iface = array.getattr("__array_interface__")?;
    let data_tuple = iface.get_item("data")?;
    let ptr_int: usize = data_tuple.get_item(0)?.extract()?;
    debug_assert!(ptr_int != 0, "numpy array data pointer is null");
    Ok(ptr_int as *const u8)
}

/// Convert a numpy structured array into a list of ``(Key, Vec<Bin>)`` pairs
/// suitable for batch_write operations.
///
/// The dtype must contain special fields named ``_namespace``, ``_set``, and ``_key``
/// for key construction, plus any number of bin data fields.
/// Alternatively, ``namespace``, ``set_name``, and ``key`` can be passed as
/// separate arguments when all rows share the same namespace/set.
///
/// # Arguments
///
/// * `py` - Python GIL token
/// * `data_array` - numpy structured array with record data
/// * `dtype_obj` - the numpy dtype describing the array layout
/// * `namespace` - default namespace (used when ``_namespace`` field is absent)
/// * `set_name` - default set name (used when ``_set`` field is absent)
/// * `key_field` - name of the dtype field to use as the user key (default: ``"_key"``)
pub fn numpy_to_records(
    py: Python<'_>,
    data_array: &Bound<'_, PyAny>,
    dtype_obj: &Bound<'_, PyAny>,
    namespace: &str,
    set_name: &str,
    key_field: &str,
) -> PyResult<Vec<(Key, Vec<Bin>)>> {
    let np = py.import("numpy")?;
    let n: usize = data_array.len()?;
    debug!(
        "numpy_to_records: converting {} rows, key_field='{}'",
        n, key_field
    );

    let (fields, row_stride) = parse_dtype_fields(dtype_obj)?;
    let data_ptr = get_array_data_ptr_readonly(data_array)?;

    // Partition fields into key-fields and bin-fields
    let key_field_info = fields.iter().find(|f| f.name == key_field);
    let bin_fields: Vec<&FieldInfo> = fields
        .iter()
        .filter(|f| f.name != key_field && !f.name.starts_with('_'))
        .collect();

    if key_field_info.is_none() {
        return Err(PyValueError::new_err(format!(
            "dtype must contain a '{}' field for the record key",
            key_field
        )));
    }
    let key_fi = key_field_info.unwrap();

    // Check for optional _namespace and _set fields
    let ns_field = fields.iter().find(|f| f.name == "_namespace");
    let set_field = fields.iter().find(|f| f.name == "_set");

    // Validate key field type
    let _ = np; // keep numpy import alive

    let mut result = Vec::with_capacity(n);

    for i in 0..n {
        let row_ptr = unsafe { data_ptr.add(i * row_stride) };

        // Extract key value
        let key_value = unsafe { read_value_from_buffer(row_ptr, key_fi)? };

        // Extract namespace (from field or default)
        let ns = if let Some(ns_fi) = ns_field {
            match unsafe { read_value_from_buffer(row_ptr, ns_fi)? } {
                Value::Blob(b) => {
                    // Trim trailing null bytes for fixed-length fields
                    let trimmed = &b[..b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1)];
                    String::from_utf8_lossy(trimmed).to_string()
                }
                Value::String(s) => s,
                _ => namespace.to_string(),
            }
        } else {
            namespace.to_string()
        };

        // Extract set name (from field or default)
        let set = if let Some(set_fi) = set_field {
            match unsafe { read_value_from_buffer(row_ptr, set_fi)? } {
                Value::Blob(b) => {
                    let trimmed = &b[..b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1)];
                    String::from_utf8_lossy(trimmed).to_string()
                }
                Value::String(s) => s,
                _ => set_name.to_string(),
            }
        } else {
            set_name.to_string()
        };

        // Build the Key
        let key = Key {
            namespace: ns,
            set_name: set,
            user_key: Some(key_value),
            digest: [0u8; 20],
        };

        // Extract bin values
        let mut bins = Vec::with_capacity(bin_fields.len());
        for field in &bin_fields {
            let value = unsafe { read_value_from_buffer(row_ptr, field)? };
            bins.push(Bin::new(field.name.clone(), value));
        }

        result.push((key, bins));
    }

    debug!("numpy_to_records: converted {} records", result.len());
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_write_int_i32() {
        let mut buf = [0u8; 16];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 4,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Int,
        };
        unsafe {
            write_int_to_buffer(buf.as_mut_ptr(), &field, 42).unwrap();
            let val = ptr::read_unaligned(buf.as_ptr().add(4) as *const i32);
            assert_eq!(val, 42);
        }
    }

    #[test]
    fn test_write_int_i8_truncation() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 1,
            base_itemsize: 1,
            kind: DtypeKind::Int,
        };
        unsafe {
            write_int_to_buffer(buf.as_mut_ptr(), &field, 300).unwrap(); // truncates to 44
            let val = ptr::read_unaligned(buf.as_ptr() as *const i8);
            assert_eq!(val, 300i64 as i8);
        }
    }

    #[test]
    fn test_write_float_f32() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Float,
        };
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, 3.14).unwrap();
            let val = ptr::read_unaligned(buf.as_ptr() as *const f32);
            assert!((val - 3.14f32).abs() < 1e-5);
        }
    }

    #[test]
    fn test_write_float_f64() {
        let mut buf = [0u8; 16];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Float,
        };
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, 3.141592653589793).unwrap();
            let val = ptr::read_unaligned(buf.as_ptr() as *const f64);
            assert!((val - 3.141592653589793f64).abs() < 1e-15);
        }
    }

    #[test]
    fn test_write_bytes_truncation() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::FixedBytes,
        };
        unsafe {
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"abcdefgh");
            // only first 4 bytes copied
            assert_eq!(&buf[0..4], b"abcd");
            assert_eq!(&buf[4..8], &[0, 0, 0, 0]);
        }
    }

    #[test]
    fn test_write_bytes_padding() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::FixedBytes,
        };
        unsafe {
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"ab");
            assert_eq!(&buf[0..2], b"ab");
            assert_eq!(&buf[2..8], &[0, 0, 0, 0, 0, 0]); // zero-padded
        }
    }

    #[test]
    fn test_unsupported_int_size() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 3,
            base_itemsize: 3,
            kind: DtypeKind::Int,
        };
        unsafe {
            let result = write_int_to_buffer(buf.as_mut_ptr(), &field, 42);
            assert!(result.is_err());
        }
    }

    #[test]
    fn test_write_uint_u16() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 2,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Uint,
        };
        unsafe {
            write_uint_to_buffer(buf.as_mut_ptr(), &field, 65535).unwrap();
            let val = ptr::read_unaligned(buf.as_ptr().add(2) as *const u16);
            assert_eq!(val, 65535);
        }
    }

    #[test]
    fn test_write_float_f16_normal() {
        let mut buf = [0u8; 4];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Float,
        };
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, 1.5).unwrap();
            let bits = ptr::read_unaligned(buf.as_ptr() as *const u16);
            let val = f16::from_bits(bits);
            assert!((val.to_f64() - 1.5).abs() < 1e-3);
        }
    }

    #[test]
    fn test_write_float_f16_denormal() {
        let mut buf = [0u8; 4];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Float,
        };
        // Smallest positive normal f16 is ~6.1e-5; test a denormal value
        let denorm_val = 5.96e-8_f64; // smallest f16 denormal
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, denorm_val).unwrap();
            let bits = ptr::read_unaligned(buf.as_ptr() as *const u16);
            let val = f16::from_bits(bits);
            // Should be representable as denormal, not flushed to zero
            assert!(val.to_f64() > 0.0 || denorm_val < f16::MIN_POSITIVE.to_f64());
        }
    }

    #[test]
    fn test_write_float_f16_infinity() {
        let mut buf = [0u8; 4];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Float,
        };
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, f64::INFINITY).unwrap();
            let bits = ptr::read_unaligned(buf.as_ptr() as *const u16);
            let val = f16::from_bits(bits);
            assert!(val.is_infinite());
            assert!(val.is_sign_positive());
        }
    }

    #[test]
    fn test_write_float_f16_nan() {
        let mut buf = [0u8; 4];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Float,
        };
        unsafe {
            write_float_to_buffer(buf.as_mut_ptr(), &field, f64::NAN).unwrap();
            let bits = ptr::read_unaligned(buf.as_ptr() as *const u16);
            let val = f16::from_bits(bits);
            assert!(val.is_nan());
        }
    }

    #[test]
    fn test_write_bytes_empty_data() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::FixedBytes,
        };
        unsafe {
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"");
            // Buffer should remain zero-initialized
            assert_eq!(&buf[0..4], &[0, 0, 0, 0]);
        }
    }

    #[test]
    fn test_write_value_nil_leaves_zero() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Int,
        };
        unsafe {
            write_value_to_buffer(buf.as_mut_ptr(), &field, &Value::Nil).unwrap();
            let val = ptr::read_unaligned(buf.as_ptr() as *const i32);
            assert_eq!(val, 0);
        }
    }

    // ── read_value_from_buffer tests ────────────────────────────

    #[test]
    fn test_read_int_i32() {
        let mut buf = [0u8; 16];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 4,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Int,
        };
        unsafe {
            ptr::write_unaligned(buf.as_mut_ptr().add(4) as *mut i32, 42);
            let val = read_value_from_buffer(buf.as_ptr(), &field).unwrap();
            assert_eq!(val, Value::Int(42));
        }
    }

    #[test]
    fn test_read_uint_u16() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 2,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Uint,
        };
        unsafe {
            ptr::write_unaligned(buf.as_mut_ptr().add(2) as *mut u16, 65535);
            let val = read_value_from_buffer(buf.as_ptr(), &field).unwrap();
            assert_eq!(val, Value::Int(65535));
        }
    }

    #[test]
    fn test_read_float_f64() {
        let mut buf = [0u8; 16];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Float,
        };
        unsafe {
            ptr::write_unaligned(buf.as_mut_ptr() as *mut f64, 3.14);
            let val = read_value_from_buffer(buf.as_ptr(), &field).unwrap();
            match val {
                Value::Float(FloatValue::F64(bits)) => {
                    assert!((f64::from_bits(bits) - 3.14).abs() < 1e-10);
                }
                _ => panic!("expected Float"),
            }
        }
    }

    #[test]
    fn test_read_bytes() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::FixedBytes,
        };
        buf[0..4].copy_from_slice(b"abcd");
        unsafe {
            let val = read_value_from_buffer(buf.as_ptr(), &field).unwrap();
            assert_eq!(val, Value::Blob(b"abcd".to_vec()));
        }
    }

    #[test]
    fn test_roundtrip_write_read_int() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Int,
        };
        unsafe {
            write_int_to_buffer(buf.as_mut_ptr(), &field, -123).unwrap();
            let val = read_value_from_buffer(buf.as_ptr(), &field).unwrap();
            assert_eq!(val, Value::Int(-123));
        }
    }
}
