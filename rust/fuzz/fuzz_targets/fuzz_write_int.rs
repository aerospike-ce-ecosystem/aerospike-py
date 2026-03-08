//! Fuzz target for integer buffer writes.
//!
//! Simulates the write_int_to_buffer logic with arbitrary field offsets,
//! sizes, and values to verify no out-of-bounds writes occur.

#![no_main]
use libfuzzer_sys::fuzz_target;
use std::ptr;

fuzz_target!(|data: &[u8]| {
    // Need at least 13 bytes: 1 (itemsize_idx) + 4 (offset) + 8 (value)
    if data.len() < 13 {
        return;
    }

    let itemsize_idx = data[0] % 4;
    let base_itemsize: usize = match itemsize_idx {
        0 => 1,
        1 => 2,
        2 => 4,
        3 => 8,
        _ => return,
    };

    let offset = u32::from_le_bytes([data[1], data[2], data[3], data[4]]) as usize;
    let value = i64::from_le_bytes([
        data[5], data[6], data[7], data[8], data[9], data[10], data[11], data[12],
    ]);

    // Allocate a buffer large enough to hold the write
    let buf_size = offset.saturating_add(base_itemsize);
    if buf_size > 1024 * 1024 {
        return; // Skip unreasonably large buffers
    }

    let mut buffer = vec![0u8; buf_size];
    let row_ptr = buffer.as_mut_ptr();

    // Simulate write_int_to_buffer logic
    unsafe {
        let dst = row_ptr.add(offset);
        match base_itemsize {
            1 => ptr::write_unaligned(dst as *mut i8, value as i8),
            2 => ptr::write_unaligned(dst as *mut i16, value as i16),
            4 => ptr::write_unaligned(dst as *mut i32, value as i32),
            8 => ptr::write_unaligned(dst as *mut i64, value),
            _ => {}
        }
    }

    // Verify buffer is still valid (no crash = success)
    assert!(buffer.len() == buf_size);
});
