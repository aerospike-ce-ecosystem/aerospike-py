//! Bytes fields and numeric vectors: the production writer and reader.
//!
//! - An `S<N>` / `V<N>` field takes bytes and text, cut to `N` bytes and
//!   zero-padded, and takes nothing else.
//! - A numeric sub-array (`('vec', 'f4', (8,))`) takes a BLOB of exactly its own
//!   size and refuses any other length. A scalar is taken only by a one-element
//!   sub-array.
//!
//! In every case nothing is written outside the field, and a refused value
//! writes nothing. That includes a field of no bytes (`S0`, `V0`, a `(0,)`
//! sub-array), which NumPy allows and dtype parsing lets through.

#![no_main]
use _aerospike::fuzzing::{field, write_then_read, DtypeKind, Input, Output};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // 1 (field kind) + 2 (offset) + 2 (size) + 1 (kind of value), then the payload
    if data.len() < 6 {
        return;
    }
    let offset = usize::from(u16::from_le_bytes([data[1], data[2]]));
    let size = usize::from(u16::from_le_bytes([data[3], data[4]]));
    let payload = &data[6..];

    let (kind, base_itemsize, elements, is_vector) = match data[0] % 5 {
        0 => (DtypeKind::FixedBytes, size, 1, false),
        1 => (DtypeKind::VoidBytes, size, 1, false),
        2 => (DtypeKind::Int, 1 << (size & 3), (size >> 2) % 65, true),
        3 => (DtypeKind::Uint, 1 << (size & 3), (size >> 2) % 65, true),
        _ => (
            DtypeKind::Float,
            [2, 4, 8][size % 3],
            (size >> 2) % 65,
            true,
        ),
    };
    let Some(field) = field(kind, base_itemsize, elements, offset, is_vector) else {
        return;
    };
    let input = match data[5] % 5 {
        0 | 1 => Input::Bytes(payload.to_vec()),
        2 => Input::Text(String::from_utf8_lossy(payload).into_owned()),
        3 => Input::Int(i64::from(payload.first().copied().unwrap_or(0))),
        _ => Input::Nil,
    };

    let outcome = write_then_read(&field, &input);

    assert_eq!(outcome.row.len(), field.offset + field.itemsize);
    assert!(
        outcome.row[..field.offset].iter().all(|byte| *byte == 0),
        "the write reached below the field"
    );
    let Some(Output::Bytes(stored)) = &outcome.read else {
        // A one-element vector is read as a BLOB too; only scalars are not.
        panic!("a bytes or vector field was read as {:?}", outcome.read);
    };
    assert_eq!(stored.len(), field.itemsize);
    if !outcome.written {
        assert!(
            outcome.row.iter().all(|byte| *byte == 0),
            "a refused value left bytes behind"
        );
        return;
    }

    let given: &[u8] = match &input {
        Input::Bytes(bytes) => bytes,
        Input::Text(text) => text.as_bytes(),
        Input::Nil => &[],
        Input::Int(_) => {
            assert!(
                is_vector && elements == 1,
                "a scalar was accepted by a field that is not a one-element vector"
            );
            return;
        }
        _ => unreachable!("not generated"),
    };
    if is_vector {
        assert!(
            matches!(input, Input::Nil) || given.len() == field.itemsize,
            "a vector of {} bytes accepted a BLOB of {}",
            field.itemsize,
            given.len()
        );
        assert!(
            !matches!(input, Input::Text(_)),
            "text was accepted as a numeric vector"
        );
    }
    let kept = given.len().min(field.itemsize);
    assert_eq!(&stored[..kept], &given[..kept]);
    assert!(
        stored[kept..].iter().all(|byte| *byte == 0),
        "the padding is not zero"
    );
});
