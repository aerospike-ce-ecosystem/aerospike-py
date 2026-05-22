"""Unit tests for put() input validation (no server required).

Covers:
- #118: put(key, None) should raise TypeError, not RecordNotFound
- put(key, non_dict) should raise TypeError
- key tuple shape validation (explicit digest length, tuple arity)
"""

import pytest

import aerospike_py
from tests import DUMMY_CONFIG


def _make_client():
    return aerospike_py.client(DUMMY_CONFIG)


@pytest.mark.parametrize(
    "invalid_bins,desc",
    [
        (None, "None"),
        ("not_a_dict", "string"),
        (123, "int"),
        ([1, 2, 3], "list"),
        ((1, 2), "tuple"),
        (True, "bool"),
        (b"bytes", "bytes"),
        (42.0, "float"),
        ({1, 2, 3}, "set"),
    ],
    ids=["None", "string", "int", "list", "tuple", "bool", "bytes", "float", "set"],
)
def test_put_non_dict_bins_raises_type_error(invalid_bins, desc):
    """put(key, non_dict) raises TypeError for type: {desc}."""
    c = _make_client()
    with pytest.raises(TypeError):
        c.put(("test", "demo", "k1"), invalid_bins)


@pytest.mark.parametrize("bad_len", [0, 1, 19, 21, 40], ids=lambda n: f"{n}bytes")
def test_put_malformed_digest_length_raises(bad_len):
    """A 4-element key with an explicit digest that is not exactly 20 bytes
    must raise ValueError instead of being silently ignored.

    Previously a wrong-length digest was discarded and the client recomputed
    the digest from the user key, so a caller passing a malformed digest
    addressed a different record than intended with no error.
    """
    c = _make_client()
    key = ("test", "demo", "k1", b"\x00" * bad_len)
    with pytest.raises(ValueError, match="20 bytes"):
        c.put(key, {"v": 1})


def test_put_valid_20_byte_digest_passes_key_validation():
    """A 4-element key with a valid 20-byte digest passes key parsing.

    No server is connected, so the call fails later with a client/cluster
    error — but never with a ValueError about the digest shape.
    """
    c = _make_client()
    key = ("test", "demo", "k1", b"\x07" * 20)
    with pytest.raises(aerospike_py.AerospikeError) as exc_info:
        c.put(key, {"v": 1})
    assert not isinstance(exc_info.value, aerospike_py.InvalidArgError)


def test_put_oversized_key_tuple_raises():
    """A key tuple longer than 4 elements is a caller mistake and must be
    rejected rather than silently ignoring the extra elements."""
    c = _make_client()
    key = ("test", "demo", "k1", b"\x00" * 20, "extra")
    with pytest.raises(ValueError, match="3 or 4 elements"):
        c.put(key, {"v": 1})
