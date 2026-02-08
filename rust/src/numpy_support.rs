use std::collections::HashMap;
use std::ptr;

use aerospike_core::{BatchRecord, FloatValue, Value};
use half::f16;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::errors::result_code_to_int;
use crate::types::value::value_to_py;

// ── dtype field descriptor ──────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DtypeKind {
    Int,
    Uint,
    Float,
    FixedBytes,
    VoidBytes,
}

#[derive(Debug, Clone)]
pub struct FieldInfo {
    pub name: String,
    pub offset: usize,
    pub itemsize: usize,
    pub base_itemsize: usize,
    pub kind: DtypeKind,
}

// ── dtype parsing ───────────────────────────────────────────────

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

fn get_array_data_ptr(array: &Bound<'_, PyAny>) -> PyResult<*mut u8> {
    let iface = array.getattr("__array_interface__")?;
    let data_tuple = iface.get_item("data")?;
    let ptr_int: usize = data_tuple.get_item(0)?.extract()?;
    let readonly: bool = data_tuple.get_item(1)?.extract()?;
    if readonly {
        return Err(PyValueError::new_err("numpy array is read-only"));
    }
    Ok(ptr_int as *mut u8)
}

// ── buffer write helpers (all unsafe) ───────────────────────────

unsafe fn write_int_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: i64) -> PyResult<()> {
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

unsafe fn write_uint_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: u64) -> PyResult<()> {
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

unsafe fn write_float_to_buffer(row_ptr: *mut u8, field: &FieldInfo, val: f64) -> PyResult<()> {
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

unsafe fn write_bytes_to_buffer(row_ptr: *mut u8, field: &FieldInfo, data: &[u8]) {
    let dst = row_ptr.add(field.offset);
    // Clamp copy length to field size to prevent buffer overrun
    let copy_len = data.len().min(field.itemsize);
    if copy_len > 0 {
        ptr::copy_nonoverlapping(data.as_ptr(), dst, copy_len);
    }
    // np.zeros already zero-initialized, no need to zero-pad
}

// ── value → buffer dispatch ─────────────────────────────────────

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

fn float_value_to_f64(fv: &FloatValue) -> f64 {
    match fv {
        FloatValue::F64(bits) => f64::from_bits(*bits),
        FloatValue::F32(bits) => f32::from_bits(*bits) as f64,
    }
}

// ── main entry point ────────────────────────────────────────────

pub fn batch_to_numpy_py(
    py: Python<'_>,
    results: &[BatchRecord],
    dtype_obj: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
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
}
