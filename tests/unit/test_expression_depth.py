"""Filter-expression nesting depth cap (no server required).

`py_to_expression` walks the Python expression dict tree recursively. Without a
depth cap, a deeply nested tree (trivial to build in a loop, and trivial to
build from untrusted request input by a query-builder service) overflows the
*native* stack and kills the whole interpreter with SIGSEGV. A native stack
overflow is not a Rust panic, so `panic_safety.rs` cannot intercept it.

These tests assert the conversion rejects over-deep trees with `ValueError`
instead, and that the process survives. Expression parsing happens during
policy extraction, before the "client is not connected" check, so no server is
needed: a shallow expression reaches `ClientError`, a deep one raises
`ValueError` first.
"""

import pytest

from aerospike_py import AsyncClient, Client, exp
from aerospike_py.exception import ClientError

# Deeper than any plausible real expression, and far deeper than the cap, but
# still well below the native stack overflow threshold once the cap is in place.
OVERFLOW_DEPTH = 10_000
# Comfortably under the cap — must still parse and reach the connect check.
SHALLOW_DEPTH = 40

_CONFIG = {"hosts": [("127.0.0.1", 1)]}
_KEY = ("test", "demo", "depth-cap")
_BINS = {"b": 1}


def _nested_not(depth: int) -> dict:
    """Build a `not(not(...(int_bin)))` chain `depth` levels deep."""
    expr = exp.int_bin("a")
    for _ in range(depth):
        expr = exp.not_(expr)
    return expr


def _nested_and(depth: int) -> dict:
    """Build an `and(..., bool_val(True))` chain `depth` levels deep."""
    expr = exp.int_bin("a")
    for _ in range(depth):
        expr = exp.and_(expr, exp.bool_val(True))
    return expr


@pytest.mark.parametrize("build", [_nested_not, _nested_and], ids=["not", "and"])
def test_overdeep_expression_raises_value_error(build):
    """An over-deep filter expression raises ValueError instead of segfaulting."""
    client = Client(_CONFIG)
    with pytest.raises(ValueError) as excinfo:
        client.put(_KEY, _BINS, policy={"filter_expression": build(OVERFLOW_DEPTH)})
    assert "depth" in str(excinfo.value).lower()


@pytest.mark.parametrize("build", [_nested_not, _nested_and], ids=["not", "and"])
def test_shallow_expression_still_parses(build):
    """A shallow expression parses fine and reaches the normal connect check."""
    client = Client(_CONFIG)
    with pytest.raises(ClientError):
        client.put(_KEY, _BINS, policy={"filter_expression": build(SHALLOW_DEPTH)})


async def test_overdeep_expression_raises_value_error_async():
    """The async client rejects an over-deep expression the same way."""
    client = AsyncClient(_CONFIG)
    with pytest.raises(ValueError) as excinfo:
        await client.put(_KEY, _BINS, policy={"filter_expression": _nested_not(OVERFLOW_DEPTH)})
    assert "depth" in str(excinfo.value).lower()


async def test_shallow_expression_still_parses_async():
    """The async client still parses a shallow expression."""
    client = AsyncClient(_CONFIG)
    with pytest.raises(ClientError):
        await client.put(_KEY, _BINS, policy={"filter_expression": _nested_not(SHALLOW_DEPTH)})
