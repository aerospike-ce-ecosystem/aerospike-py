"""Unit tests for put() input validation (no server required).

Covers:
- #118: put(key, None) should raise TypeError, not RecordNotFound
- put(key, non_dict) should raise TypeError
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
