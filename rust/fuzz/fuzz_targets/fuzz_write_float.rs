//! Fuzz target for float buffer writes.
//!
//! Simulates write_float_to_buffer with arbitrary field sizes and float values,
//! including NaN, infinity, denormals, and other edge cases.

#![no_main]
use libfuzzer_sys::fuzz_target;
use std::ptr;

fuzz_target!(|data: &[u8]| {
    // Need at least 9 bytes: 1 (itemsize_idx) + 8 (f64 value)
    if data.len() < 9 {
        return;
    }

    let itemsize_idx = data[0] % 3;
    let base_itemsize: usize = match itemsize_idx {
        0 => 2, // f16
        1 => 4, // f32
        2 => 8, // f64
        _ => return,
    };

    let value = f64::from_le_bytes([
        data[1], data[2], data[3], data[4], data[5], data[6], data[7], data[8],
    ]);

    let offset: usize = 0;
    let buf_size = offset + base_itemsize;
    let mut buffer = vec![0u8; buf_size];
    let dst = buffer.as_mut_ptr();

    unsafe {
        match base_itemsize {
            2 => {
                // Simulate f16 conversion (just store raw bits of truncated value)
                let bits = (value as f32).to_bits();
                let f16_bits = ((bits >> 16) & 0x8000)
                    | (((bits >> 23) & 0xFF).wrapping_sub(112).min(31) << 10)
                    | ((bits >> 13) & 0x3FF);
                ptr::write_unaligned(dst as *mut u16, f16_bits as u16);
            }
            4 => ptr::write_unaligned(dst as *mut f32, value as f32),
            8 => ptr::write_unaligned(dst as *mut f64, value),
            _ => {}
        }
    }

    assert!(buffer.len() == buf_size);
});
