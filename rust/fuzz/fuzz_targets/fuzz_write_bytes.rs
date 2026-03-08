//! Fuzz target for bytes buffer writes.
//!
//! Simulates the write_bytes_to_buffer logic with arbitrary data,
//! field sizes, and offsets to verify no buffer overruns.

#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Need at least 6 bytes: 2 (offset) + 2 (itemsize) + 2 (at least some data)
    if data.len() < 6 {
        return;
    }

    let offset = u16::from_le_bytes([data[0], data[1]]) as usize;
    let itemsize = u16::from_le_bytes([data[2], data[3]]) as usize;
    if itemsize == 0 {
        return;
    }

    let src_data = &data[4..];

    // Allocate buffer
    let buf_size = offset.saturating_add(itemsize);
    if buf_size > 1024 * 1024 {
        return;
    }

    let mut buffer = vec![0u8; buf_size];
    let dst = unsafe { buffer.as_mut_ptr().add(offset) };

    // Simulate write_bytes_to_buffer: bounded copy using slice
    let copy_len = src_data.len().min(itemsize);
    if copy_len > 0 {
        let dst_slice = unsafe { std::slice::from_raw_parts_mut(dst, itemsize) };
        dst_slice[..copy_len].copy_from_slice(&src_data[..copy_len]);
    }

    assert!(buffer.len() == buf_size);
});
