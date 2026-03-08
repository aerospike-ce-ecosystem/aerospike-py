# Fuzz Testing for numpy_support

Fuzz testing targets for the unsafe buffer write/read functions in `numpy_support.rs`.

## Prerequisites

```bash
cargo install cargo-fuzz
```

## Running

```bash
cd rust/
cargo +nightly fuzz run fuzz_write_int -- -max_total_time=60
cargo +nightly fuzz run fuzz_write_bytes -- -max_total_time=60
cargo +nightly fuzz run fuzz_write_float -- -max_total_time=60
```

## Targets

| Target | Description |
|--------|-------------|
| `fuzz_write_int` | Fuzz `write_int_to_buffer` with random field offsets, sizes, and values |
| `fuzz_write_bytes` | Fuzz `write_bytes_to_buffer` with random byte data and field sizes |
| `fuzz_write_float` | Fuzz `write_float_to_buffer` with random float values and field sizes |
