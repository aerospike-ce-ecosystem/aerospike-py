//! Float fields: the production writer and reader on arbitrary fields and values.
//!
//! A value the writer accepts for an `f2`, `f4` or `f8` field must come back as
//! the nearest value that width can hold. In particular a finite value never
//! comes back infinite: one that does not fit is refused, and a refused value
//! writes nothing.

#![no_main]
use _aerospike::fuzzing::{field, write_then_read, DtypeKind, Input, Output};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // 1 (width) + 2 (offset) + 1 (kind of value) + 8 (value)
    if data.len() < 12 {
        return;
    }
    let width = [2usize, 4, 8][usize::from(data[0] % 3)];
    let offset = usize::from(u16::from_le_bytes([data[1], data[2]]));
    let raw = u64::from_le_bytes(data[4..12].try_into().expect("eight bytes"));
    let input = match data[3] % 3 {
        0 => Input::Float(f64::from_bits(raw)),
        1 => Input::Int(raw as i64),
        _ => Input::Bool(raw & 1 == 1),
    };
    let Some(field) = field(DtypeKind::Float, width, 1, offset, false) else {
        return;
    };

    let outcome = write_then_read(&field, &input);

    assert_eq!(outcome.row.len(), field.offset + field.itemsize);
    assert!(
        outcome.row[..field.offset].iter().all(|byte| *byte == 0),
        "the write reached below the field"
    );
    if !outcome.written {
        assert!(
            outcome.row.iter().all(|byte| *byte == 0),
            "a refused value left bytes behind"
        );
        return;
    }

    let asked = match input {
        Input::Float(v) => v,
        Input::Int(v) => v as f64,
        Input::Bool(v) => f64::from(u8::from(v)),
        _ => unreachable!("only numbers are generated"),
    };
    let Some(Output::Float(got)) = outcome.read else {
        panic!("a float field was read as {:?}", outcome.read);
    };

    if asked.is_nan() {
        assert!(got.is_nan());
        return;
    }
    assert_eq!(
        got.is_finite(),
        asked.is_finite(),
        "{asked} was stored as {got}"
    );
    match width {
        8 => assert_eq!(got.to_bits(), asked.to_bits()),
        4 => assert_eq!(got, f64::from(asked as f32)),
        // Half precision keeps about three decimal digits.
        _ if asked.is_finite() => {
            let tolerance = asked.abs() * 1e-3 + 1e-7;
            assert!(
                (got - asked).abs() <= tolerance,
                "{asked} came back as {got}"
            );
        }
        _ => assert_eq!(got, asked),
    }
});
