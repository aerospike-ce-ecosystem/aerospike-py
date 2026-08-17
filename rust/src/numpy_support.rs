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
use std::marker::PhantomData;
use std::ptr;

use aerospike_core::{BatchRecord, Bin, FloatValue, Key, Value};
use half::f16;
use log::{debug, warn};
use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::errors::result_code_to_int;
use crate::record_helpers::record_ttl_seconds;
use crate::types::key::compute_bytes_key_digest;
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

/// The NumPy byte-order character matching this build's native endianness.
///
/// NumPy normally normalises a native-endian scalar to `'='`, but an explicitly
/// spelled `'<i4'` can still surface the concrete character, so the host's own
/// marker is accepted alongside `'='`.
const NATIVE_BYTEORDER_CHAR: &str = if cfg!(target_endian = "little") {
    "<"
} else {
    ">"
};

/// Reject a dtype field whose base scalar is not stored in native byte order.
///
/// Every buffer helper in this module reads and writes native Rust scalars via
/// `ptr::read_unaligned` / `ptr::write_unaligned`, i.e. always **native**-endian.
/// Byte order was previously never inspected, so a byte-swapped field such as
/// `>i4` passed validation as `kind='i', itemsize=4` and then round-tripped
/// silently corrupted numbers in both directions: `to_numpy(dtype)` handed back
/// wrong values (native `1` reads back as `16777216`), and `batch_write_numpy`
/// wrote wrong values *into the database* — no exception, no warning.
///
/// Accepted: `'='` (native), `'|'` (not applicable — `S`, `V`, and single-byte
/// `i1`/`u1`), and [`NATIVE_BYTEORDER_CHAR`]. Anything else is rejected loudly,
/// following the client-side input-rejection pattern used elsewhere in the
/// crate.
///
/// # Not recursive
///
/// This checks one level. A **nested structured** field —
/// `np.dtype([('a', [('b', '>i4')])])` — reports `kind='V'`, `byteorder='|'`,
/// and `base is self`, so it is accepted and the inner `>i4` is never inspected.
/// That is deliberate rather than a hole: a `V` field is handled as opaque
/// fixed-width bytes by [`write_bytes_to_buffer`] / [`read_value_from_buffer`],
/// so its payload is copied verbatim in both directions and round-trips
/// byte-identically whatever the inner byte order. Do not assume recursive
/// coverage here; if `V` fields ever gain per-member interpretation, this check
/// has to recurse with them.
fn check_native_byteorder(base: &Bound<'_, PyAny>, name: &str) -> PyResult<()> {
    let byteorder: String = base.getattr("byteorder")?.extract()?;
    if byteorder == "=" || byteorder == "|" || byteorder == NATIVE_BYTEORDER_CHAR {
        return Ok(());
    }
    warn!(
        "Non-native dtype byteorder '{}' for field '{}'",
        byteorder, name
    );
    Err(PyValueError::new_err(format!(
        "dtype field '{}' has non-native byte order (byteorder='{}', base dtype {}): \
         this buffer is read and written natively, so a byte-swapped field would \
         silently round-trip corrupted values. Convert the array first with \
         `arr.astype(arr.dtype.newbyteorder('='))`, or declare the field natively \
         (e.g. 'i4' / '=i4' instead of '>i4').",
        name, byteorder, base,
    )))
}

/// Parse a NumPy structured dtype into field descriptors and the row stride.
///
/// Validates that every field is a supported kind, is stored in native byte
/// order, and fits within the row stride (no buffer overrun).
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

        check_native_byteorder(&base, name)?;

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
///
/// Callers index rows as `ptr.add(i * row_stride)`, which assumes packed
/// C-contiguous storage. This function rejects strided / non-contiguous
/// arrays up front so that assumption always holds.
fn get_array_data_ptr(array: &Bound<'_, PyAny>) -> PyResult<*mut u8> {
    let iface = array.getattr("__array_interface__")?;

    // Guardrail: callers assume packed C-contiguous rows. A non-None `strides`
    // entry means the array is sliced / strided / reversed, so the
    // `ptr.add(i * row_stride)` arithmetic would read the wrong bytes.
    let strides_obj = iface.get_item("strides")?;
    if !strides_obj.is_none() {
        return Err(PyValueError::new_err(format!(
            "numpy array must be C-contiguous, got strides {}",
            strides_obj
        )));
    }

    let data_tuple = iface.get_item("data")?;
    let ptr_int: usize = data_tuple.get_item(0)?.extract()?;
    let readonly: bool = data_tuple.get_item(1)?.extract()?;
    if readonly {
        return Err(PyValueError::new_err("numpy array is read-only"));
    }
    if ptr_int == 0 {
        return Err(PyValueError::new_err("numpy array data pointer is null"));
    }
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
    debug_assert!(
        field.offset.checked_add(field.base_itemsize).is_some(),
        "field '{}': offset + base_itemsize overflows",
        field.name
    );
    if row_ptr.is_null() {
        return Err(PyValueError::new_err(
            "null buffer pointer in write_int_to_buffer",
        ));
    }
    // SAFETY: caller guarantees row_ptr + field.offset is valid and within bounds
    let dst = unsafe { row_ptr.add(field.offset) };
    match field.base_itemsize {
        1 => {
            if val < i8::MIN as i64 || val > i8::MAX as i64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in i8 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 1 byte of writable memory
            unsafe { ptr::write_unaligned(dst as *mut i8, val as i8) }
        }
        2 => {
            if val < i16::MIN as i64 || val > i16::MAX as i64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in i16 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 2 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut i16, val as i16) }
        }
        4 => {
            if val < i32::MIN as i64 || val > i32::MAX as i64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in i32 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 4 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut i32, val as i32) }
        }
        // SAFETY: dst points to at least 8 bytes of writable memory
        8 => unsafe { ptr::write_unaligned(dst as *mut i64, val) },
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
    debug_assert!(
        field.offset.checked_add(field.base_itemsize).is_some(),
        "field '{}': offset + base_itemsize overflows",
        field.name
    );
    if row_ptr.is_null() {
        return Err(PyValueError::new_err(
            "null buffer pointer in write_uint_to_buffer",
        ));
    }
    // SAFETY: caller guarantees row_ptr + field.offset is valid and within bounds
    let dst = unsafe { row_ptr.add(field.offset) };
    match field.base_itemsize {
        1 => {
            if val > u8::MAX as u64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in u8 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 1 byte of writable memory
            unsafe { ptr::write_unaligned(dst, val as u8) }
        }
        2 => {
            if val > u16::MAX as u64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in u16 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 2 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut u16, val as u16) }
        }
        4 => {
            if val > u32::MAX as u64 {
                return Err(PyOverflowError::new_err(format!(
                    "integer overflow: value {} does not fit in u32 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 4 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut u32, val as u32) }
        }
        // SAFETY: dst points to at least 8 bytes of writable memory
        8 => unsafe { ptr::write_unaligned(dst as *mut u64, val) },
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
    debug_assert!(
        field.offset.checked_add(field.base_itemsize).is_some(),
        "field '{}': offset + base_itemsize overflows",
        field.name
    );
    if row_ptr.is_null() {
        return Err(PyValueError::new_err(
            "null buffer pointer in write_float_to_buffer",
        ));
    }
    // SAFETY: caller guarantees row_ptr + field.offset is valid and within bounds
    let dst = unsafe { row_ptr.add(field.offset) };
    match field.base_itemsize {
        4 => {
            if val.is_finite() && (val > f32::MAX as f64 || val < f32::MIN as f64) {
                return Err(PyOverflowError::new_err(format!(
                    "float overflow: value {} does not fit in f32 for field '{}'",
                    val, field.name
                )));
            }
            // SAFETY: dst points to at least 4 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut f32, val as f32) }
        }
        // SAFETY: dst points to at least 8 bytes of writable memory
        8 => unsafe { ptr::write_unaligned(dst as *mut f64, val) },
        2 => {
            // float16: use `half` crate for IEEE 754 compliant conversion
            // Handles denormals, rounding, and special values correctly
            let h = f16::from_f64(val);
            // SAFETY: dst points to at least 2 bytes of writable memory
            unsafe { ptr::write_unaligned(dst as *mut u16, h.to_bits()) };
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
unsafe fn write_bytes_to_buffer(row_ptr: *mut u8, field: &FieldInfo, data: &[u8]) -> PyResult<()> {
    debug_assert!(!row_ptr.is_null());
    debug_assert!(
        field.offset.checked_add(field.itemsize).is_some(),
        "field '{}': offset + itemsize overflows",
        field.name
    );
    if row_ptr.is_null() {
        return Err(PyValueError::new_err(
            "null buffer pointer in write_bytes_to_buffer",
        ));
    }
    // SAFETY: caller guarantees row_ptr + field.offset is valid and within bounds
    let dst = unsafe { row_ptr.add(field.offset) };
    // Clamp copy length to field size to prevent buffer overrun
    let copy_len = data.len().min(field.itemsize);
    if copy_len > 0 {
        // SAFETY: dst points to at least field.itemsize bytes of writable memory
        let dst_slice = unsafe { std::slice::from_raw_parts_mut(dst, field.itemsize) };
        dst_slice[..copy_len].copy_from_slice(&data[..copy_len]);
    }
    // np.zeros already zero-initialized, no need to zero-pad
    Ok(())
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
    fn non_negative_u64(v: i64, field: &FieldInfo) -> PyResult<u64> {
        if v < 0 {
            return Err(PyValueError::new_err(format!(
                "cannot write negative integer {} to unsigned field '{}'",
                v, field.name
            )));
        }
        Ok(v as u64)
    }
    fn non_negative_f64_to_u64(v: f64, field: &FieldInfo) -> PyResult<u64> {
        if !v.is_finite() {
            return Err(PyValueError::new_err(format!(
                "cannot write non-finite float {} to unsigned field '{}'",
                v, field.name
            )));
        }
        if v < 0.0 {
            return Err(PyValueError::new_err(format!(
                "cannot write negative float {} to unsigned field '{}'",
                v, field.name
            )));
        }
        if v >= u64::MAX as f64 {
            return Err(PyValueError::new_err(format!(
                "cannot write out-of-range float {} to unsigned field '{}'",
                v, field.name
            )));
        }
        Ok(v as u64)
    }
    fn finite_f64_to_i64(v: f64, field: &FieldInfo) -> PyResult<i64> {
        if !v.is_finite() {
            return Err(PyValueError::new_err(format!(
                "cannot write non-finite float {} to integer field '{}'",
                v, field.name
            )));
        }
        if v < i64::MIN as f64 || v >= i64::MAX as f64 {
            return Err(PyValueError::new_err(format!(
                "cannot write out-of-range float {} to integer field '{}'",
                v, field.name
            )));
        }
        Ok(v as i64)
    }

    match value {
        Value::Int(v) => match field.kind {
            // SAFETY: forwarding caller's safety guarantees to write_*_to_buffer
            DtypeKind::Int => unsafe { write_int_to_buffer(row_ptr, field, *v) },
            DtypeKind::Uint => unsafe {
                write_uint_to_buffer(row_ptr, field, non_negative_u64(*v, field)?)
            },
            DtypeKind::Float => unsafe { write_float_to_buffer(row_ptr, field, *v as f64) },
            _ => Err(PyTypeError::new_err(format!(
                "cannot write integer to bytes field '{}'",
                field.name
            ))),
        },
        Value::Float(fv) => {
            let v = float_value_to_f64(fv);
            match field.kind {
                // SAFETY: forwarding caller's safety guarantees to write_*_to_buffer
                DtypeKind::Float => unsafe { write_float_to_buffer(row_ptr, field, v) },
                DtypeKind::Int => unsafe {
                    write_int_to_buffer(row_ptr, field, finite_f64_to_i64(v, field)?)
                },
                DtypeKind::Uint => unsafe {
                    write_uint_to_buffer(row_ptr, field, non_negative_f64_to_u64(v, field)?)
                },
                _ => Err(PyTypeError::new_err(format!(
                    "cannot write float to bytes field '{}'",
                    field.name
                ))),
            }
        }
        Value::Bool(b) => {
            let iv = if *b { 1i64 } else { 0i64 };
            match field.kind {
                // SAFETY: forwarding caller's safety guarantees to write_*_to_buffer
                DtypeKind::Int => unsafe { write_int_to_buffer(row_ptr, field, iv) },
                DtypeKind::Uint => unsafe { write_uint_to_buffer(row_ptr, field, iv as u64) },
                DtypeKind::Float => unsafe { write_float_to_buffer(row_ptr, field, iv as f64) },
                _ => Err(PyTypeError::new_err(format!(
                    "cannot write bool to bytes field '{}'",
                    field.name
                ))),
            }
        }
        Value::Blob(bytes) => match field.kind {
            DtypeKind::FixedBytes | DtypeKind::VoidBytes => {
                // SAFETY: forwarding caller's safety guarantees to write_bytes_to_buffer
                unsafe { write_bytes_to_buffer(row_ptr, field, bytes) }
            }
            // sub-array: bytes blob written directly to buffer
            DtypeKind::Float | DtypeKind::Int | DtypeKind::Uint
                if field.itemsize > field.base_itemsize =>
            {
                // SAFETY: forwarding caller's safety guarantees to write_bytes_to_buffer
                unsafe { write_bytes_to_buffer(row_ptr, field, bytes) }
            }
            _ => Err(PyTypeError::new_err(format!(
                "cannot write bytes to numeric field '{}'",
                field.name
            ))),
        },
        Value::String(s) => match field.kind {
            DtypeKind::FixedBytes | DtypeKind::VoidBytes => {
                // SAFETY: forwarding caller's safety guarantees to write_bytes_to_buffer
                unsafe { write_bytes_to_buffer(row_ptr, field, s.as_bytes()) }
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

/// NumPy buffer address stored as `usize` so that the `py.detach` closure
/// can capture it across the GIL-free boundary.
///
/// Why `usize` instead of `*mut u8`: under Rust 2021 disjoint captures,
/// reading the inner field of a `struct Wrapper(*mut u8)` causes the
/// closure to capture the raw pointer directly, which is not `Send`. A
/// `usize` field sidesteps that — `usize: Send` always — and we cast back
/// to `*mut u8` at use sites where we already need an `unsafe` block.
///
/// The `PhantomData<&'py mut u8>` ties the address to the lifetime of
/// the owning NumPy [`Bound`] so that the compiler statically forbids
/// returning a `BufferAddr` out of [`batch_to_numpy_py`] or storing it
/// past the array's drop — a guarantee the comment-only contract used
/// to rely on. The `Send` impl re-enables the cross-`py.detach`
/// capture that the marker would otherwise (correctly) forbid: we
/// transfer the address into a closure that completes synchronously on
/// the same thread before the borrow ends.
///
/// # Safety
///
/// `BufferAddr` is only constructed inside [`batch_to_numpy_py`] from the
/// data pointer of a locally-held NumPy array. That array outlives every
/// use of the address, and `py.detach` only releases the GIL on the
/// calling thread — no other thread can resize or replace the buffer
/// while the pointer is in use.
#[derive(Clone, Copy)]
struct BufferAddr<'py> {
    addr: usize,
    _phantom: PhantomData<&'py mut u8>,
}

// SAFETY: see the type docs — the address is captured into a
// `py.detach` closure that completes on the same thread within the
// originating NumPy array's borrow, so the `Send` cross-thread
// implication of `PhantomData<&'py mut u8>` does not materialise.
unsafe impl Send for BufferAddr<'_> {}

impl<'py> BufferAddr<'py> {
    /// # Safety
    ///
    /// `array` must own a writable buffer whose lifetime covers `'py`,
    /// and `ptr` must be its current data pointer (as returned by
    /// [`get_array_data_ptr`]).
    #[inline]
    unsafe fn from_ptr(_array: &Bound<'py, PyAny>, ptr: *mut u8) -> Self {
        Self {
            addr: ptr as usize,
            _phantom: PhantomData,
        }
    }

    /// # Safety
    ///
    /// Caller must uphold the lifetime invariants documented on the type:
    /// the originating NumPy array must still be alive and its buffer
    /// must not have been reallocated.
    #[inline]
    unsafe fn as_ptr(self) -> *mut u8 {
        self.addr as *mut u8
    }
}

/// Convert batch results into a `NumpyBatchRecords` Python object.
///
/// Allocates three NumPy arrays (data, meta, result_codes) and writes
/// Aerospike values directly into the data buffer via raw pointers,
/// avoiding per-element Python object allocation.
///
/// **GIL handling.** The per-record fill loop runs under
/// [`Python::detach`], so every `Value → buffer` write happens with the
/// GIL released. This matters most for CPU-inference workloads
/// (uvicorn/FastAPI + PyTorch), where another worker can hold the GIL for
/// its tensor work while this thread is doing nothing but raw
/// `ptr::write_unaligned`. Only the prep (numpy allocation, dtype parse,
/// key_map build) and the final wrapper construction touch the
/// interpreter.
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

    // Overflow check: ensure n * row_stride does not overflow usize
    if n.checked_mul(row_stride).is_none() {
        return Err(PyValueError::new_err(format!(
            "buffer size overflow: {} rows * {} bytes/row exceeds usize",
            n, row_stride,
        )));
    }

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

    // 3. Get raw data pointers, stored as `usize` so they can cross
    //    `py.detach` (Rust 2021 disjoint captures forbid capturing
    //    `*mut u8` directly; see [`BufferAddr`] docs). The `'py`
    //    lifetime on each address is tied to the owning `Bound`, so
    //    the compiler statically rejects any use that outlives the
    //    array.
    //
    // SAFETY: the `*mut u8` returned by `get_array_data_ptr` is the
    // data pointer of the just-allocated NumPy array; the local
    // `Bound` keeps that array alive for the whole `'py` borrow.
    let data_addr = unsafe { BufferAddr::from_ptr(&data_array, get_array_data_ptr(&data_array)?) };
    let meta_addr = unsafe { BufferAddr::from_ptr(&meta_array, get_array_data_ptr(&meta_array)?) };
    let rc_addr = unsafe {
        BufferAddr::from_ptr(
            &result_codes_array,
            get_array_data_ptr(&result_codes_array)?,
        )
    };

    // meta stride: gen(u4) + ttl(u4) = 8 bytes
    let meta_stride: usize = 8;

    // 4. Build field name → FieldInfo lookup
    let field_map: HashMap<&str, &FieldInfo> =
        fields.iter().map(|f| (f.name.as_str(), f)).collect();

    // 5. Fill data / meta / result_codes buffers WITHOUT the GIL.
    //
    // Every operation inside the loop is either pure Rust
    // (`result_code_to_int`, `record_ttl_seconds`, `Value` matching) or a
    // raw memory write (`ptr::write_unaligned`). Nothing touches the
    // Python interpreter, so another thread (e.g. a sibling FastAPI worker
    // running torch inference) can hold the GIL while this thread fills
    // the array.
    //
    // `write_value_to_buffer` may construct a `PyErr` on overflow / type
    // mismatch. pyo3's `PyErr::new_err` stores arguments lazily and only
    // realises the Python exception object when the error escapes back
    // through the FFI boundary, so it is safe to call without the GIL.
    //
    // The `entry_thread` snapshot exists to detect future refactors that
    // try to move the fill loop off the calling thread (e.g. wrapping
    // `tokio::spawn` or `rayon::par_iter` inside the closure). The
    // `BufferAddr::as_ptr` safety contract requires single-thread sync
    // execution; if that ever changes, the debug assert here will fire
    // before the raw pointers cause UB. In release builds the snapshot
    // compiles out.
    let entry_thread = std::thread::current().id();
    py.detach(move || -> PyResult<()> {
        debug_assert_eq!(
            std::thread::current().id(),
            entry_thread,
            "py.detach closure must run on the calling thread — BufferAddr is not Send across threads"
        );
        // SAFETY: the NumPy arrays (`data_array`, `meta_array`,
        // `result_codes_array`) outlive this closure — they are owned by
        // the outer scope which strictly outlives `py.detach`.
        let data_ptr = unsafe { data_addr.as_ptr() };
        let meta_ptr = unsafe { meta_addr.as_ptr() };
        let rc_ptr = unsafe { rc_addr.as_ptr() };

        for (i, br) in results.iter().enumerate() {
            let result_code = match &br.result_code {
                Some(rc) => result_code_to_int(rc),
                None => 0,
            };

            // SAFETY: rc_ptr points to an i32 array of length n; i < n.
            unsafe {
                ptr::write_unaligned(rc_ptr.add(i * 4) as *mut i32, result_code);
            }

            if result_code != 0 {
                continue;
            }
            let Some(record) = &br.record else {
                log::warn!(
                    "batch record at index {}: result_code is OK but record is None (data/meta will be zero-filled)",
                    i
                );
                continue;
            };

            let gen = record.generation;
            let ttl: u32 = record_ttl_seconds(record);

            // SAFETY: meta_ptr points to a (u4,u4) array of length n; i < n.
            unsafe {
                let meta_row = meta_ptr.add(i * meta_stride);
                ptr::write_unaligned(meta_row as *mut u32, gen);
                ptr::write_unaligned(meta_row.add(4) as *mut u32, ttl);
            }

            // SAFETY: data_ptr points to a structured array of length n
            // and row stride `row_stride`; bounds were checked via
            // `n.checked_mul(row_stride)` above.
            let row_ptr = unsafe { data_ptr.add(i * row_stride) };
            for (bin_name, value) in &record.bins {
                if let Some(field) = field_map.get(bin_name.as_str()) {
                    // SAFETY: parse_dtype_fields validated that
                    // offset + itemsize <= row_stride for every field.
                    unsafe {
                        write_value_to_buffer(row_ptr, field, value)?;
                    }
                }
                // bins not in dtype are silently ignored
            }
        }
        // Mirror the entry-side check so a future refactor that swaps
        // threads mid-closure (e.g. a worker steal) is also caught.
        debug_assert_eq!(
            std::thread::current().id(),
            entry_thread,
            "py.detach closure must exit on the same thread it entered — BufferAddr is not Send across threads"
        );
        Ok(())
    })?;

    // 6. Build key_map with the GIL reacquired. This is the only
    //    record-iterating step that genuinely needs Python objects.
    let key_map = PyDict::new(py);
    for (i, br) in results.iter().enumerate() {
        // Use a sentinel string for None keys to avoid collision with integer user_keys.
        let user_key = match &br.key.user_key {
            Some(v) => value_to_py(py, v)?,
            None => format!("__no_user_key_{i}__")
                .into_pyobject(py)?
                .into_any()
                .unbind(),
        };
        key_map.set_item(user_key, i)?;
    }

    // 7. Construct NumpyBatchRecords Python object
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
    fn uint_to_i64(v: u64, field: &FieldInfo) -> PyResult<i64> {
        i64::try_from(v).map_err(|_| {
            PyOverflowError::new_err(format!(
                "unsigned value {} in field '{}' exceeds signed 64-bit Aerospike integer range",
                v, field.name
            ))
        })
    }

    if row_ptr.is_null() {
        return Err(PyValueError::new_err(
            "null buffer pointer in read_value_from_buffer",
        ));
    }
    // SAFETY: caller guarantees row_ptr + field.offset is valid and within bounds
    let src = unsafe { row_ptr.add(field.offset) };

    // Sub-array numeric field (e.g. ('vec','(4,)f8')): the field spans
    // `itemsize` bytes across multiple base elements. A scalar read would
    // capture only `base_itemsize` bytes and silently drop the rest, so
    // read all `itemsize` bytes into a Blob — mirroring the write path,
    // which routes such fields through `write_bytes_to_buffer`.
    if matches!(
        field.kind,
        DtypeKind::Int | DtypeKind::Uint | DtypeKind::Float
    ) && field.itemsize > field.base_itemsize
    {
        let mut buf = vec![0u8; field.itemsize];
        // SAFETY: src points to at least field.itemsize bytes of readable memory
        unsafe { ptr::copy_nonoverlapping(src, buf.as_mut_ptr(), field.itemsize) };
        return Ok(Value::Blob(buf));
    }

    match field.kind {
        DtypeKind::Int => {
            let v = match field.base_itemsize {
                // SAFETY: src points to at least N bytes of readable memory
                1 => (unsafe { ptr::read_unaligned(src as *const i8) }) as i64,
                2 => (unsafe { ptr::read_unaligned(src as *const i16) }) as i64,
                4 => (unsafe { ptr::read_unaligned(src as *const i32) }) as i64,
                8 => unsafe { ptr::read_unaligned(src as *const i64) },
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
                // SAFETY: src points to at least N bytes of readable memory
                1 => (unsafe { ptr::read_unaligned(src) }) as i64,
                2 => (unsafe { ptr::read_unaligned(src as *const u16) }) as i64,
                4 => (unsafe { ptr::read_unaligned(src as *const u32) }) as i64,
                8 => uint_to_i64(unsafe { ptr::read_unaligned(src as *const u64) }, field)?,
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
                    // SAFETY: src points to at least 2 bytes of readable memory
                    let bits = unsafe { ptr::read_unaligned(src as *const u16) };
                    f16::from_bits(bits).to_f64()
                }
                // SAFETY: src points to at least N bytes of readable memory
                4 => (unsafe { ptr::read_unaligned(src as *const f32) }) as f64,
                8 => unsafe { ptr::read_unaligned(src as *const f64) },
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
            // SAFETY: src points to at least field.itemsize bytes of readable memory
            unsafe { ptr::copy_nonoverlapping(src, buf.as_mut_ptr(), field.itemsize) };
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
    if ptr_int == 0 {
        return Err(PyValueError::new_err("numpy array data pointer is null"));
    }
    Ok(ptr_int as *const u8)
}

/// Resolve the actual byte stride between logical rows in a 1-D numpy structured array.
///
/// NumPy views can expose row strides larger than `dtype.itemsize` (for sliced
/// arrays) or negative strides (for reversed views). The native batch-write path
/// must honor those strides instead of assuming packed contiguous rows.
fn get_array_row_stride(array: &Bound<'_, PyAny>, row_size: usize) -> PyResult<isize> {
    let iface = array.getattr("__array_interface__")?;
    let shape: Vec<usize> = iface.get_item("shape")?.extract()?;
    if shape.len() != 1 {
        return Err(PyValueError::new_err(format!(
            "numpy structured array must be 1-dimensional, got shape {:?}",
            shape
        )));
    }

    let row_size = isize::try_from(row_size).map_err(|_| {
        PyValueError::new_err(format!(
            "dtype itemsize {} exceeds supported pointer stride range",
            row_size
        ))
    })?;

    let strides_obj = iface.get_item("strides")?;
    if strides_obj.is_none() {
        return Ok(row_size);
    }

    let strides: Vec<isize> = strides_obj.extract()?;
    if strides.len() != 1 {
        return Err(PyValueError::new_err(format!(
            "numpy structured array must be 1-dimensional, got strides {:?}",
            strides
        )));
    }

    let stride = strides[0];
    if stride != 0 {
        let abs_stride = stride.checked_abs().ok_or_else(|| {
            PyValueError::new_err(format!(
                "numpy structured array row stride {} is not supported",
                stride
            ))
        })?;
        if abs_stride < row_size {
            return Err(PyValueError::new_err(format!(
                "numpy structured array row stride {} is smaller than dtype itemsize {}",
                stride, row_size
            )));
        }
    }

    Ok(stride)
}

fn checked_row_offset(index: usize, row_stride: isize) -> PyResult<isize> {
    let index = isize::try_from(index).map_err(|_| {
        PyValueError::new_err(format!(
            "array index {} exceeds supported pointer offset range",
            index
        ))
    })?;

    index.checked_mul(row_stride).ok_or_else(|| {
        PyValueError::new_err(format!(
            "buffer offset overflow: index {} * stride {} exceeds isize",
            index, row_stride
        ))
    })
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
    _py: Python<'_>,
    data_array: &Bound<'_, PyAny>,
    dtype_obj: &Bound<'_, PyAny>,
    namespace: &str,
    set_name: &str,
    key_field: &str,
) -> PyResult<Vec<(Key, Vec<Bin>)>> {
    let n: usize = data_array.len()?;
    debug!(
        "numpy_to_records: converting {} rows, key_field='{}'",
        n, key_field
    );

    let (fields, row_size) = parse_dtype_fields(dtype_obj)?;

    // Overflow check: ensure n * row_stride does not overflow usize
    if n.checked_mul(row_size).is_none() {
        return Err(PyValueError::new_err(format!(
            "buffer size overflow: {} rows * {} bytes/row exceeds usize",
            n, row_size,
        )));
    }

    let data_ptr = get_array_data_ptr_readonly(data_array)?;
    let row_stride = get_array_row_stride(data_array, row_size)?;

    // Partition fields into key-fields and bin-fields
    let key_field_info = fields.iter().find(|f| f.name == key_field);
    let bin_fields: Vec<&FieldInfo> = fields
        .iter()
        .filter(|f| f.name != key_field && !f.name.starts_with('_'))
        .collect();

    let key_fi = key_field_info.ok_or_else(|| {
        PyValueError::new_err(format!(
            "dtype must contain a '{}' field for the record key",
            key_field
        ))
    })?;

    // Check for optional _namespace and _set fields
    let ns_field = fields.iter().find(|f| f.name == "_namespace");
    let set_field = fields.iter().find(|f| f.name == "_set");

    let mut result = Vec::with_capacity(n);

    for i in 0..n {
        let row_offset = checked_row_offset(i, row_stride)?;
        let row_ptr = unsafe { data_ptr.offset(row_offset) };

        // Extract key value.
        // For bytes keys from fixed-length numpy fields (e.g. S10), trim
        // trailing null bytes so the digest matches lookups with unpadded keys.
        // This mirrors the trimming already applied to _namespace and _set fields.
        let key_value = unsafe { read_value_from_buffer(row_ptr, key_fi)? };
        let key_value = match key_value {
            Value::Blob(ref b) => {
                let end = b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1);
                if end < b.len() {
                    Value::Blob(b[..end].to_vec())
                } else {
                    key_value
                }
            }
            _ => key_value,
        };

        // Extract namespace (from field or default)
        let ns = if let Some(ns_fi) = ns_field {
            match unsafe { read_value_from_buffer(row_ptr, ns_fi)? } {
                Value::Blob(b) => {
                    // Trim trailing null bytes for fixed-length fields
                    let trimmed = &b[..b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1)];
                    String::from_utf8_lossy(trimmed).into_owned()
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
                    String::from_utf8_lossy(trimmed).into_owned()
                }
                Value::String(s) => s,
                _ => set_name.to_string(),
            }
        } else {
            set_name.to_string()
        };

        // Build the Key with a properly computed digest.
        // For Blob (bytes) keys, use STRING particle type (3) for cross-client
        // compatibility with the official C Python client.
        // For other key types, use Key::new() which computes the correct digest.
        let key = match &key_value {
            Value::Blob(bytes_data) => {
                let digest = compute_bytes_key_digest(&set, bytes_data);
                Key {
                    namespace: ns,
                    set_name: set,
                    user_key: Some(key_value),
                    digest,
                }
            }
            _ => Key::new(ns, set, key_value)
                .map_err(|e| PyValueError::new_err(format!("Invalid key at row {}: {}", i, e)))?,
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

    fn fake_numpy_stride_module<'py>(
        py: Python<'py>,
    ) -> PyResult<Bound<'py, pyo3::types::PyModule>> {
        pyo3::types::PyModule::from_code(
            py,
            c"
import ctypes
import struct

class FakeFieldDtype:
    def __init__(self, kind, itemsize, byteorder='='):
        self.kind = kind
        self.itemsize = itemsize
        self.byteorder = byteorder
        self.base = self

    def __str__(self):
        return f'{self.byteorder}{self.kind}{self.itemsize}'


class FakeSubArrayDtype:
    '''A sub-array field: numpy reports byteorder '|' here and the real
    byte order on `.base`, so `parse_dtype_fields` must inspect `.base`.'''

    def __init__(self, base, count):
        self.kind = 'V'
        self.itemsize = base.itemsize * count
        self.byteorder = '|'
        self.base = base


class FakeNestedStructDtype:
    '''A nested structured field: numpy reports kind='V', byteorder='|' and
    `base is self` here, so the inner member's byte order is invisible at this
    level. Handled as opaque fixed-width bytes.'''

    def __init__(self, inner):
        self.kind = 'V'
        self.itemsize = inner.itemsize
        self.byteorder = '|'
        self.base = self
        self.names = ('b',)
        self.fields = {'b': (inner, 0)}


class FakeSingleFieldDtype:
    def __init__(self, field_dtype):
        self.names = ('score',)
        self.fields = {'score': (field_dtype, 0)}
        self.itemsize = field_dtype.itemsize

class FakeDtype:
    def __init__(self):
        i4 = FakeFieldDtype('i', 4)
        self.names = ('_key', 'value')
        self.fields = {
            '_key': (i4, 0),
            'value': (i4, 4),
        }
        self.itemsize = 8

class FakeArray:
    def __init__(self, buf, ptr, shape, strides):
        self._buf = buf
        self._length = shape[0]
        self.__array_interface__ = {
            'data': (ptr, False),
            'shape': shape,
            'strides': strides,
        }

    def __len__(self):
        return self._length

def _build_buffer():
    buf = ctypes.create_string_buffer(24)
    struct.pack_into('<ii', buf, 0, 1, 10)
    struct.pack_into('<ii', buf, 8, 2, 20)
    struct.pack_into('<ii', buf, 16, 3, 30)
    return buf

def make_dtype():
    return FakeDtype()

def make_scalar_dtype(kind, itemsize, byteorder):
    return FakeSingleFieldDtype(FakeFieldDtype(kind, itemsize, byteorder))

def make_subarray_dtype(kind, itemsize, byteorder, count):
    base = FakeFieldDtype(kind, itemsize, byteorder)
    return FakeSingleFieldDtype(FakeSubArrayDtype(base, count))

def make_nested_struct_dtype(kind, itemsize, byteorder):
    inner = FakeFieldDtype(kind, itemsize, byteorder)
    return FakeSingleFieldDtype(FakeNestedStructDtype(inner))

def make_step_slice():
    buf = _build_buffer()
    return FakeArray(buf, ctypes.addressof(buf), (2,), (16,))

def make_reverse_slice():
    buf = _build_buffer()
    return FakeArray(buf, ctypes.addressof(buf) + 16, (3,), (-8,))
",
            c"fake_numpy_support.py",
            c"fake_numpy_support",
        )
    }

    // ── dtype byte-order validation ─────────────────────────────

    /// The numpy byte-order character that is *not* native on this host.
    fn non_native_byteorder_char() -> &'static str {
        if cfg!(target_endian = "little") {
            ">"
        } else {
            "<"
        }
    }

    /// Parse a single-field dtype built by the `fake_numpy_support` helper.
    ///
    /// `factory` is `make_scalar_dtype` or `make_subarray_dtype`; `args` matches
    /// that factory's signature.
    fn parse_helper_dtype<'py, A>(
        py: Python<'py>,
        factory: &str,
        args: A,
    ) -> PyResult<(Vec<FieldInfo>, usize)>
    where
        A: pyo3::call::PyCallArgs<'py>,
    {
        let module = fake_numpy_stride_module(py).expect("test helper module should compile");
        let dtype = module
            .getattr(factory)
            .expect("dtype factory should exist")
            .call1(args)
            .expect("dtype construction should succeed");
        parse_dtype_fields(&dtype)
    }

    #[test]
    fn parse_dtype_fields_accepts_native_byteorder() {
        Python::initialize();
        Python::attach(|py| {
            let (fields, row_stride) =
                parse_helper_dtype(py, "make_scalar_dtype", ("i", 4usize, "="))
                    .expect("native-endian dtype must be accepted");
            assert_eq!(fields.len(), 1);
            assert_eq!(fields[0].kind, DtypeKind::Int);
            assert_eq!(row_stride, 4);
        });
    }

    #[test]
    fn parse_dtype_fields_accepts_host_native_byteorder_char() {
        Python::initialize();
        Python::attach(|py| {
            // numpy normalises native dtypes to '=', but an explicitly spelled
            // '<i4' (on a little-endian host) must be accepted too.
            let (fields, _) = parse_helper_dtype(
                py,
                "make_scalar_dtype",
                ("i", 4usize, NATIVE_BYTEORDER_CHAR),
            )
            .expect("host-native byteorder char must be accepted");
            assert_eq!(fields.len(), 1);
        });
    }

    #[test]
    fn parse_dtype_fields_accepts_byteorder_agnostic() {
        Python::initialize();
        Python::attach(|py| {
            // '|' means "not applicable": S / V and single-byte i1 / u1.
            let (fields, _) = parse_helper_dtype(py, "make_scalar_dtype", ("S", 10usize, "|"))
                .expect("byte-order-agnostic dtype must be accepted");
            assert_eq!(fields[0].kind, DtypeKind::FixedBytes);
        });
    }

    /// Regression test for the silent corruption this check exists to stop.
    ///
    /// A `>i4` field used to parse as `kind='i', itemsize=4`; the buffer helpers
    /// then wrote native bytes and numpy read them back byte-swapped — native
    /// `1` surfaced as `16777216`, with no exception and no warning.
    #[test]
    fn parse_dtype_fields_rejects_non_native_int_byteorder() {
        Python::initialize();
        Python::attach(|py| {
            let err = parse_helper_dtype(
                py,
                "make_scalar_dtype",
                ("i", 4usize, non_native_byteorder_char()),
            )
            .expect_err("byte-swapped int dtype must be rejected");
            assert!(err.is_instance_of::<PyValueError>(py));
            let msg = err.to_string();
            assert!(msg.contains("score"), "error should name the field: {msg}");
            assert!(
                msg.contains("non-native byte order"),
                "error should state the cause: {msg}"
            );
            assert!(
                msg.contains("newbyteorder"),
                "error should tell the caller how to convert: {msg}"
            );
        });
    }

    #[test]
    fn parse_dtype_fields_rejects_non_native_float_byteorder() {
        Python::initialize();
        Python::attach(|py| {
            let err = parse_helper_dtype(
                py,
                "make_scalar_dtype",
                ("f", 8usize, non_native_byteorder_char()),
            )
            .expect_err("byte-swapped float dtype must be rejected");
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    /// numpy reports `byteorder == '|'` on a *sub-array* field dtype and the
    /// real byte order only on its `.base`, so the check must inspect `.base`.
    /// Reading the field dtype instead would let `>f4` sub-arrays through.
    #[test]
    fn parse_dtype_fields_rejects_non_native_subarray_base_byteorder() {
        Python::initialize();
        Python::attach(|py| {
            let err = parse_helper_dtype(
                py,
                "make_subarray_dtype",
                ("f", 4usize, non_native_byteorder_char(), 4usize),
            )
            .expect_err("byte-swapped sub-array base dtype must be rejected");
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    /// Documents the one-level boundary of the byte-order check.
    ///
    /// A nested structured field reports `kind='V'`, `byteorder='|'`, and
    /// `base is self`, so it is accepted and its inner `>i4` is never inspected.
    /// Benign: `V` is handled as opaque fixed-width bytes and round-trips
    /// byte-identically. Pinned so nobody later assumes recursive coverage.
    #[test]
    fn parse_dtype_fields_accepts_nested_struct_without_recursing() {
        Python::initialize();
        Python::attach(|py| {
            let (fields, row_stride) =
                parse_helper_dtype(py, "make_nested_struct_dtype", ("i", 4usize, ">"))
                    .expect("nested struct field is opaque V bytes and must be accepted");
            assert_eq!(fields.len(), 1);
            assert_eq!(fields[0].kind, DtypeKind::VoidBytes);
            assert_eq!(row_stride, 4);
        });
    }

    #[test]
    fn parse_dtype_fields_accepts_native_subarray_base_byteorder() {
        Python::initialize();
        Python::attach(|py| {
            let (fields, row_stride) =
                parse_helper_dtype(py, "make_subarray_dtype", ("f", 4usize, "=", 4usize))
                    .expect("native sub-array dtype must be accepted");
            assert_eq!(fields[0].kind, DtypeKind::Float);
            assert_eq!(fields[0].base_itemsize, 4);
            assert_eq!(fields[0].itemsize, 16);
            assert_eq!(row_stride, 16);
        });
    }

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
            write_int_to_buffer(buf.as_mut_ptr(), &field, 42)
                .expect("write i32 to valid buffer should succeed");
            let val = ptr::read_unaligned(buf.as_ptr().add(4) as *const i32);
            assert_eq!(val, 42);
        }
    }

    #[test]
    fn test_write_int_i8_overflow_returns_error() {
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 1,
            base_itemsize: 1,
            kind: DtypeKind::Int,
        };
        unsafe {
            let result = write_int_to_buffer(buf.as_mut_ptr(), &field, 300);
            assert!(result.is_err(), "overflow should return error");
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, std::f64::consts::PI)
                .expect("write f32 to valid buffer should succeed");
            let val = ptr::read_unaligned(buf.as_ptr() as *const f32);
            assert!((val - std::f32::consts::PI).abs() < 1e-5);
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, std::f64::consts::PI)
                .expect("write f64 to valid buffer should succeed");
            let val = ptr::read_unaligned(buf.as_ptr() as *const f64);
            assert!((val - std::f64::consts::PI).abs() < 1e-15);
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
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"abcdefgh")
                .expect("write truncated bytes should succeed");
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
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"ab")
                .expect("write short bytes with zero-padding should succeed");
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
            write_uint_to_buffer(buf.as_mut_ptr(), &field, 65535)
                .expect("write u16 to valid buffer should succeed");
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, 1.5)
                .expect("write f16 normal value should succeed");
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, denorm_val)
                .expect("write f16 denormal value should succeed");
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, f64::INFINITY)
                .expect("write f16 infinity should succeed");
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
            write_float_to_buffer(buf.as_mut_ptr(), &field, f64::NAN)
                .expect("write f16 NaN should succeed");
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
            write_bytes_to_buffer(buf.as_mut_ptr(), &field, b"")
                .expect("write empty bytes should succeed");
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
            write_value_to_buffer(buf.as_mut_ptr(), &field, &Value::Nil)
                .expect("write Nil value should be no-op and succeed");
            let val = ptr::read_unaligned(buf.as_ptr() as *const i32);
            assert_eq!(val, 0);
        }
    }

    #[test]
    fn test_write_value_negative_int_to_uint_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 2,
            base_itemsize: 2,
            kind: DtypeKind::Uint,
        };
        unsafe {
            let err = write_value_to_buffer(buf.as_mut_ptr(), &field, &Value::Int(-1))
                .expect_err("negative int to uint should fail");
            assert!(err
                .to_string()
                .contains("cannot write negative integer -1 to unsigned field 'x'"));
        }
    }

    #[test]
    fn test_write_value_negative_float_to_uint_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Uint,
        };
        unsafe {
            let err = write_value_to_buffer(
                buf.as_mut_ptr(),
                &field,
                &Value::Float(FloatValue::F64((-1.5f64).to_bits())),
            )
            .expect_err("negative float to uint should fail");
            assert!(err
                .to_string()
                .contains("cannot write negative float -1.5 to unsigned field 'x'"));
        }
    }

    #[test]
    fn test_write_value_large_float_to_uint_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Uint,
        };
        unsafe {
            let err = write_value_to_buffer(
                buf.as_mut_ptr(),
                &field,
                &Value::Float(FloatValue::F64((u64::MAX as f64).to_bits())),
            )
            .expect_err("large float to uint should fail");
            assert!(err.to_string().contains("cannot write out-of-range float"));
        }
    }

    #[test]
    fn test_write_value_nan_float_to_int_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Int,
        };
        unsafe {
            let err = write_value_to_buffer(
                buf.as_mut_ptr(),
                &field,
                &Value::Float(FloatValue::F64(f64::NAN.to_bits())),
            )
            .expect_err("NaN float to int should fail");
            assert!(err
                .to_string()
                .contains("cannot write non-finite float NaN to integer field 'x'"));
        }
    }

    #[test]
    fn test_write_value_large_float_to_int_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Int,
        };
        unsafe {
            let err = write_value_to_buffer(
                buf.as_mut_ptr(),
                &field,
                &Value::Float(FloatValue::F64((i64::MAX as f64).to_bits())),
            )
            .expect_err("large float to int should fail");
            assert!(err.to_string().contains("cannot write out-of-range float"));
        }
    }

    #[test]
    fn test_write_value_nan_float_to_uint_rejected() {
        Python::initialize();
        let mut buf = [0u8; 8];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 0,
            itemsize: 4,
            base_itemsize: 4,
            kind: DtypeKind::Uint,
        };
        unsafe {
            let err = write_value_to_buffer(
                buf.as_mut_ptr(),
                &field,
                &Value::Float(FloatValue::F64(f64::NAN.to_bits())),
            )
            .expect_err("NaN float to uint should fail");
            assert!(err
                .to_string()
                .contains("cannot write non-finite float NaN to unsigned field 'x'"));
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
            let val = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("read i32 from valid buffer should succeed");
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
            let val = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("read u16 from valid buffer should succeed");
            assert_eq!(val, Value::Int(65535));
        }
    }

    #[test]
    fn test_read_uint_u64_above_i64_max_rejected() {
        Python::initialize();
        let mut buf = [0u8; 16];
        let field = FieldInfo {
            name: "x".to_string(),
            offset: 4,
            itemsize: 8,
            base_itemsize: 8,
            kind: DtypeKind::Uint,
        };
        unsafe {
            ptr::write_unaligned(buf.as_mut_ptr().add(4) as *mut u64, i64::MAX as u64 + 1);
            let err =
                read_value_from_buffer(buf.as_ptr(), &field).expect_err("u64 overflow should fail");
            Python::attach(|py| {
                assert!(err.is_instance_of::<PyOverflowError>(py));
            });
            assert!(err
                .to_string()
                .contains("exceeds signed 64-bit Aerospike integer range"));
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
            ptr::write_unaligned(buf.as_mut_ptr() as *mut f64, std::f64::consts::PI);
            let val = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("read f64 from valid buffer should succeed");
            match val {
                Value::Float(FloatValue::F64(bits)) => {
                    assert!((f64::from_bits(bits) - std::f64::consts::PI).abs() < 1e-10);
                }
                _ => panic!("expected Float(F64) variant, got {:?}", val),
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
            let val = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("read bytes from valid buffer should succeed");
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
            write_int_to_buffer(buf.as_mut_ptr(), &field, -123)
                .expect("roundtrip: write i32 should succeed");
            let val = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("roundtrip: read i32 should succeed");
            assert_eq!(val, Value::Int(-123));
        }
    }

    #[test]
    fn test_numpy_to_records_reads_positive_stride_slice() {
        Python::initialize();
        Python::attach(|py| {
            let module = fake_numpy_stride_module(py).expect("test helper module should compile");
            let dtype = module
                .getattr("make_dtype")
                .expect("make_dtype should exist")
                .call0()
                .expect("dtype construction should succeed");
            let sliced = module
                .getattr("make_step_slice")
                .expect("make_step_slice should exist")
                .call0()
                .expect("step slice construction should succeed");

            let records = numpy_to_records(py, &sliced, &dtype, "test", "demo", "_key")
                .expect("positive-stride slice should convert");
            assert_eq!(records.len(), 2);
            assert_eq!(records[0].0.user_key, Some(Value::Int(1)));
            assert_eq!(
                records[0].1,
                vec![Bin::new("value".to_string(), Value::Int(10))]
            );
            assert_eq!(records[1].0.user_key, Some(Value::Int(3)));
            assert_eq!(
                records[1].1,
                vec![Bin::new("value".to_string(), Value::Int(30))]
            );
        });
    }

    #[test]
    fn test_numpy_to_records_reads_negative_stride_slice() {
        Python::initialize();
        Python::attach(|py| {
            let module = fake_numpy_stride_module(py).expect("test helper module should compile");
            let dtype = module
                .getattr("make_dtype")
                .expect("make_dtype should exist")
                .call0()
                .expect("dtype construction should succeed");
            let reversed = module
                .getattr("make_reverse_slice")
                .expect("make_reverse_slice should exist")
                .call0()
                .expect("reverse slice construction should succeed");

            let records = numpy_to_records(py, &reversed, &dtype, "test", "demo", "_key")
                .expect("negative-stride slice should convert");
            assert_eq!(records.len(), 3);
            assert_eq!(records[0].0.user_key, Some(Value::Int(3)));
            assert_eq!(
                records[0].1,
                vec![Bin::new("value".to_string(), Value::Int(30))]
            );
            assert_eq!(records[1].0.user_key, Some(Value::Int(2)));
            assert_eq!(
                records[1].1,
                vec![Bin::new("value".to_string(), Value::Int(20))]
            );
            assert_eq!(records[2].0.user_key, Some(Value::Int(1)));
            assert_eq!(
                records[2].1,
                vec![Bin::new("value".to_string(), Value::Int(10))]
            );
        });
    }

    #[test]
    fn test_bytes_key_trailing_null_trim() {
        let padded = Value::Blob(b"alice\x00\x00\x00\x00\x00".to_vec());
        let trimmed = match padded {
            Value::Blob(ref b) => {
                let end = b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1);
                Value::Blob(b[..end].to_vec())
            }
            other => other,
        };
        assert_eq!(trimmed, Value::Blob(b"alice".to_vec()));
    }

    #[test]
    fn test_bytes_key_all_nulls_trim_to_empty() {
        let padded = Value::Blob(b"\x00\x00\x00".to_vec());
        let trimmed = match padded {
            Value::Blob(ref b) => {
                let end = b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1);
                Value::Blob(b[..end].to_vec())
            }
            other => other,
        };
        assert_eq!(trimmed, Value::Blob(b"".to_vec()));
    }

    #[test]
    fn test_bytes_key_no_trailing_nulls_unchanged() {
        let original = Value::Blob(b"exact".to_vec());
        let result = match &original {
            Value::Blob(ref b) => {
                let end = b.iter().rposition(|&x| x != 0).map_or(0, |p| p + 1);
                if end < b.len() {
                    Value::Blob(b[..end].to_vec())
                } else {
                    original.clone()
                }
            }
            _ => original.clone(),
        };
        assert_eq!(result, Value::Blob(b"exact".to_vec()));
    }

    /// Regression test for the sub-array data-loss bug: a structured-dtype
    /// field that is a numeric sub-array (e.g. ('vec','(4,)f8') →
    /// kind=Float, base_itemsize=8, itemsize=32) must round-trip ALL
    /// `itemsize` bytes through write → read. Before the fix, the read path
    /// matched only on `base_itemsize` and returned a single scalar,
    /// silently dropping all but the first base element.
    #[test]
    fn test_subarray_float_write_read_roundtrip() {
        // 4-element f64 sub-array: base_itemsize=8, itemsize=32.
        let field = FieldInfo {
            name: "vec".to_string(),
            offset: 0,
            itemsize: 32,
            base_itemsize: 8,
            kind: DtypeKind::Float,
        };
        let mut buf = [0u8; 32];

        // Source payload: 4 distinct f64 values laid out contiguously.
        let values = [1.5_f64, -2.25, 3.125, 4.0e10];
        let mut payload = Vec::with_capacity(32);
        for v in values {
            payload.extend_from_slice(&v.to_le_bytes());
        }

        unsafe {
            // WRITE path: a Blob whose len equals itemsize routes through
            // write_bytes_to_buffer for sub-array numeric fields.
            write_value_to_buffer(buf.as_mut_ptr(), &field, &Value::Blob(payload.clone()))
                .expect("sub-array blob write should succeed");

            // READ path: must return all 32 bytes, not a single 8-byte scalar.
            let read = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("sub-array read should succeed");

            match read {
                Value::Blob(bytes) => {
                    assert_eq!(
                        bytes.len(),
                        32,
                        "sub-array read must preserve all {} bytes, not just base_itemsize",
                        field.itemsize
                    );
                    assert_eq!(bytes, payload, "sub-array bytes must round-trip exactly");
                }
                other => panic!("expected Value::Blob for sub-array field, got {other:?}"),
            }
        }
    }

    /// Same round-trip guarantee for an integer sub-array.
    #[test]
    fn test_subarray_int_write_read_roundtrip() {
        // 3-element i32 sub-array: base_itemsize=4, itemsize=12.
        let field = FieldInfo {
            name: "ids".to_string(),
            offset: 0,
            itemsize: 12,
            base_itemsize: 4,
            kind: DtypeKind::Int,
        };
        let mut buf = [0u8; 12];

        let values = [10_i32, -20, 30];
        let mut payload = Vec::with_capacity(12);
        for v in values {
            payload.extend_from_slice(&v.to_le_bytes());
        }

        unsafe {
            write_value_to_buffer(buf.as_mut_ptr(), &field, &Value::Blob(payload.clone()))
                .expect("sub-array int blob write should succeed");

            let read = read_value_from_buffer(buf.as_ptr(), &field)
                .expect("sub-array int read should succeed");

            match read {
                Value::Blob(bytes) => {
                    assert_eq!(
                        bytes.len(),
                        12,
                        "int sub-array read must preserve all bytes"
                    );
                    assert_eq!(bytes, payload);
                }
                other => panic!("expected Value::Blob for int sub-array field, got {other:?}"),
            }
        }
    }
}
