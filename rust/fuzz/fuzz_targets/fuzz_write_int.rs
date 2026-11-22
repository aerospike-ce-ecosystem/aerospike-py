//! Integer fields: the production writer and reader on arbitrary fields and values.
//!
//! Whatever integer, float or bool the writer accepts for an `i1`…`i8` or
//! `u1`…`u8` field must be what the reader hands back: no wrap-around, no sign
//! flip, nothing written outside the field, and nothing written at all when the
//! value is refused.

#![no_main]
use _aerospike::fuzzing::{field, write_then_read, DtypeKind, Input, Output};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // 1 (signedness and width) + 2 (offset) + 1 (kind of value) + 8 (value)
    if data.len() < 12 {
        return;
    }
    let signed = data[0] & 1 == 0;
    let width = 1usize << ((data[0] >> 1) & 3);
    let offset = usize::from(u16::from_le_bytes([data[1], data[2]]));
    let raw = i64::from_le_bytes(data[4..12].try_into().expect("eight bytes"));
    let input = match data[3] % 3 {
        0 => Input::Int(raw),
        1 => Input::Float(f64::from_bits(raw as u64)),
        _ => Input::Bool(raw & 1 == 1),
    };
    let kind = if signed {
        DtypeKind::Int
    } else {
        DtypeKind::Uint
    };
    let Some(field) = field(kind, width, 1, offset, false) else {
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

    let expected: i128 = match input {
        Input::Int(v) => i128::from(v),
        Input::Bool(v) => i128::from(v),
        Input::Float(v) => {
            assert!(
                v.is_finite(),
                "a non-finite float was written as an integer"
            );
            v.trunc() as i128
        }
        _ => unreachable!("only numbers are generated"),
    };
    let bits = 8 * width as u32;
    let (lowest, highest) = if signed {
        (-(1i128 << (bits - 1)), (1i128 << (bits - 1)) - 1)
    } else {
        (0, (1i128 << bits) - 1)
    };
    assert!(
        (lowest..=highest).contains(&expected),
        "{expected} was accepted for a field that holds {lowest}..={highest}"
    );

    match outcome.read {
        Some(Output::Int(got)) => assert_eq!(i128::from(got), expected),
        // An unsigned 64-bit value above the signed range is stored faithfully
        // but has no Aerospike integer to be read into.
        None => assert!(!signed && width == 8 && expected > i128::from(i64::MAX)),
        other => panic!("an integer field was read as {other:?}"),
    }
});
