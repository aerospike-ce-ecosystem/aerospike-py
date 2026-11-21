# Fuzz Testing for numpy_support

Fuzz testing targets for the unsafe buffer write/read functions in `numpy_support.rs`.

The targets call the production functions — `write_value_to_buffer` and
`read_value_from_buffer` — through the safe shims in `_aerospike::fuzzing`
(`numpy_support.rs`, compiled only with the `fuzzing` feature). A shim builds a
field the way dtype parsing does and allocates a row of exactly
`offset + itemsize` bytes, so an access past the field is an access past the
allocation and the address sanitizer reports it. On top of "does not crash",
each target asserts what the writer and reader promise: an accepted value reads
back unchanged, a refused value writes nothing, nothing is written outside the
field.

The fuzz crate links libpython, as `cargo test` does. PyO3 takes the interpreter
from `PYO3_PYTHON`, or the `python3` on `PATH`.

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
| `fuzz_write_int` | `i1`…`i8` / `u1`…`u8` fields with integer, float and bool values: no wrap-around, no sign flip |
| `fuzz_write_float` | `f2` / `f4` / `f8` fields: a finite value never comes back infinite |
| `fuzz_write_bytes` | `S<N>` / `V<N>` fields (truncation, zero padding) and numeric sub-arrays (exact BLOB length only) |
