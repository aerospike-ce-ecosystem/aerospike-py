"""The ``operate_ordered()`` contract, pinned against the official client.

Each case names a request, the record it runs against, and the ordered bins the
official client returns for it. Three things are checked per case:

1. the official client still returns the recorded value, so the table in
   ``docs/rust-v3-numpy-handoff.md`` cannot drift from reality unnoticed;
2. the sync client returns exactly what the official client returns;
3. the async client does too.

Every client runs the request against its own freshly written record, because
most cases contain writes.

The rule the cases encode: the official client asks the server to answer every
operation only when the request contains a map, bit, HLL or expression
operation. In that mode an operation that names a bin appears even when it has
no value (``(name, None)``), and an operation that names no bin (``touch``)
produces no entry. Otherwise only operations that return a value appear. List
operations do not switch the mode on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

import aerospike_py
from aerospike_py import bit_operations as rust_bit
from aerospike_py import hll_operations as rust_hll
from aerospike_py import list_operations as rust_lop
from aerospike_py import map_operations as rust_mop
from tests import AEROSPIKE_CONFIG
from tests.server import skip_or_raise

aerospike = pytest.importorskip("aerospike")
from aerospike_helpers import expressions as off_exp  # noqa: E402
from aerospike_helpers.operations import bitwise_operations as off_bit  # noqa: E402
from aerospike_helpers.operations import expression_operations as off_expop  # noqa: E402
from aerospike_helpers.operations import hll_operations as off_hll  # noqa: E402
from aerospike_helpers.operations import list_operations as off_lop  # noqa: E402
from aerospike_helpers.operations import map_operations as off_mop  # noqa: E402
from aerospike_helpers.operations import operations as off_ops  # noqa: E402

NS = "test"
SET = "compat_oo_contract"


def _read(bin_name: str) -> dict[str, Any]:
    return {"op": aerospike_py.OPERATOR_READ, "bin": bin_name}


def _write(bin_name: str, value: Any) -> dict[str, Any]:
    return {"op": aerospike_py.OPERATOR_WRITE, "bin": bin_name, "val": value}


def _incr(bin_name: str, value: int) -> dict[str, Any]:
    return {"op": aerospike_py.OPERATOR_INCR, "bin": bin_name, "val": value}


def _append(bin_name: str, value: str) -> dict[str, Any]:
    return {"op": aerospike_py.OPERATOR_APPEND, "bin": bin_name, "val": value}


def _touch() -> dict[str, Any]:
    return {"op": aerospike_py.OPERATOR_TOUCH}


@dataclass(frozen=True)
class Case:
    """One request and the ordered bins the official client returns for it."""

    id: str
    initial: dict[str, Any]
    official_ops: Callable[[], list[Any]]
    expected: list[tuple[str, Any]]
    # ``None`` when the binding has no equivalent operation to compare.
    rust_ops: Callable[[], list[Any]] | None = None


CASES: list[Case] = [
    # ── only operations that return a value appear ────────────────────
    Case(
        id="reads_keep_request_order_and_duplicates",
        initial={"a": 1, "b": 2, "c": 3},
        official_ops=lambda: [off_ops.read("c"), off_ops.read("a"), off_ops.read("c"), off_ops.read("b")],
        rust_ops=lambda: [_read("c"), _read("a"), _read("c"), _read("b")],
        expected=[("c", 3), ("a", 1), ("c", 3), ("b", 2)],
    ),
    Case(
        id="increment_then_read_returns_only_the_read",
        initial={"x": 2},
        official_ops=lambda: [off_ops.increment("x", 1), off_ops.read("x")],
        rust_ops=lambda: [_incr("x", 1), _read("x")],
        expected=[("x", 3)],
    ),
    Case(
        id="write_only_returns_nothing",
        initial={"b": 2},
        official_ops=lambda: [off_ops.write("x", 7)],
        rust_ops=lambda: [_write("x", 7)],
        expected=[],
    ),
    Case(
        id="touch_then_read",
        initial={"b": 2},
        official_ops=lambda: [off_ops.touch(), off_ops.read("b")],
        rust_ops=lambda: [_touch(), _read("b")],
        expected=[("b", 2)],
    ),
    Case(
        id="missing_bin_read_is_omitted",
        initial={"b": 2},
        official_ops=lambda: [off_ops.read("nope"), off_ops.read("b")],
        rust_ops=lambda: [_read("nope"), _read("b")],
        expected=[("b", 2)],
    ),
    Case(
        id="write_then_missing_and_present_reads",
        initial={"n": 5},
        official_ops=lambda: [off_ops.write("y", 1), off_ops.read("nope"), off_ops.read("n")],
        rust_ops=lambda: [_write("y", 1), _read("nope"), _read("n")],
        expected=[("n", 5)],
    ),
    Case(
        id="append_then_read",
        initial={"s": "a"},
        official_ops=lambda: [off_ops.append("s", "x"), off_ops.read("s")],
        rust_ops=lambda: [_append("s", "x"), _read("s")],
        expected=[("s", "ax")],
    ),
    Case(
        id="list_append_then_read_keeps_both_results",
        initial={"l": [1]},
        official_ops=lambda: [off_lop.list_append("l", 3), off_ops.read("l")],
        rust_ops=lambda: [rust_lop.list_append("l", 3), _read("l")],
        expected=[("l", 2), ("l", [1, 3])],
    ),
    Case(
        id="list_append_then_list_size",
        initial={"items": [10, 20, 30]},
        official_ops=lambda: [off_lop.list_append("items", 40), off_lop.list_size("items")],
        rust_ops=lambda: [rust_lop.list_append("items", 40), rust_lop.list_size("items")],
        expected=[("items", 4), ("items", 4)],
    ),
    Case(
        id="list_clear_returns_nothing_of_its_own",
        initial={"l": [1]},
        official_ops=lambda: [off_lop.list_clear("l"), off_ops.read("l")],
        rust_ops=lambda: [rust_lop.list_clear("l"), _read("l")],
        expected=[("l", [])],
    ),
    Case(
        id="list_read_does_not_force_write_results",
        initial={"l": [1]},
        official_ops=lambda: [off_ops.write("x", 7), off_lop.list_size("l")],
        rust_ops=lambda: [_write("x", 7), rust_lop.list_size("l")],
        expected=[("l", 1)],
    ),
    Case(
        id="list_remove_with_no_return_type",
        initial={"l": [1]},
        official_ops=lambda: [
            off_ops.write("x", 7),
            off_lop.list_remove_by_index("l", 0, aerospike.LIST_RETURN_NONE),
        ],
        rust_ops=lambda: [
            _write("x", 7),
            rust_lop.list_remove_by_index("l", 0, aerospike_py.LIST_RETURN_NONE),
        ],
        expected=[],
    ),
    # ── a map / bit / HLL / expression op makes every named op appear ──
    Case(
        id="map_read_makes_write_appear_as_none",
        initial={"m": {"k": 1}},
        official_ops=lambda: [off_ops.write("x", 7), off_mop.map_size("m")],
        rust_ops=lambda: [_write("x", 7), rust_mop.map_size("m")],
        expected=[("x", None), ("m", 1)],
    ),
    Case(
        id="map_write_makes_write_appear_as_none",
        initial={"m": {"k": 1}},
        official_ops=lambda: [off_ops.write("x", 7), off_mop.map_put("m", "j", 2)],
        rust_ops=lambda: [_write("x", 7), rust_mop.map_put("m", "j", 2)],
        expected=[("x", None), ("m", 2)],
    ),
    Case(
        id="map_put_then_map_size",
        initial={"mymap": {"a": 1, "b": 2}},
        official_ops=lambda: [off_mop.map_put("mymap", "c", 3), off_mop.map_size("mymap")],
        rust_ops=lambda: [rust_mop.map_put("mymap", "c", 3), rust_mop.map_size("mymap")],
        expected=[("mymap", 3), ("mymap", 3)],
    ),
    Case(
        id="missing_bin_read_appears_as_none_with_map_op",
        initial={"m": {"k": 1}},
        official_ops=lambda: [off_ops.read("nope"), off_mop.map_size("m")],
        rust_ops=lambda: [_read("nope"), rust_mop.map_size("m")],
        expected=[("nope", None), ("m", 1)],
    ),
    Case(
        id="increment_read_and_map_op",
        initial={"x": 2, "m": {"k": 1}},
        official_ops=lambda: [off_ops.increment("x", 1), off_ops.read("x"), off_mop.map_size("m")],
        rust_ops=lambda: [_incr("x", 1), _read("x"), rust_mop.map_size("m")],
        expected=[("x", None), ("x", 3), ("m", 1)],
    ),
    Case(
        id="touch_never_appears_even_with_map_op",
        initial={"m": {"k": 1}},
        official_ops=lambda: [off_ops.touch(), off_mop.map_size("m")],
        rust_ops=lambda: [_touch(), rust_mop.map_size("m")],
        expected=[("m", 1)],
    ),
    Case(
        id="bit_read_makes_write_appear_as_none",
        initial={"b": bytearray(b"\x0f")},
        official_ops=lambda: [off_ops.write("x", 7), off_bit.bit_count("b", 0, 8)],
        rust_ops=lambda: [_write("x", 7), rust_bit.bit_count("b", 0, 8)],
        expected=[("x", None), ("b", 4)],
    ),
    Case(
        id="hll_ops_make_write_appear_as_none",
        initial={"n": 5},
        official_ops=lambda: [
            off_ops.write("x", 7),
            off_hll.hll_add("h", ["a"], 8),
            off_hll.hll_get_count("h"),
        ],
        rust_ops=lambda: [_write("x", 7), rust_hll.hll_add("h", ["a"], 8), rust_hll.hll_get_count("h")],
        expected=[("x", None), ("h", 1), ("h", 1)],
    ),
    Case(
        id="expression_read_makes_write_appear_as_none",
        initial={"n": 5},
        official_ops=lambda: [
            off_ops.write("x", 7),
            off_expop.expression_read("r", off_exp.Add(off_exp.IntBin("n"), 1).compile()),
        ],
        # The binding exposes no expression operation, so only the official
        # value is pinned.
        rust_ops=None,
        expected=[("x", None), ("r", 6)],
    ),
]

BINDING_CASES = [case for case in CASES if case.rust_ops is not None]

# Rust client 2.2 returns the bins of an ``operate`` as a ``HashMap``: repeated
# bins collapse into one entry, request order is lost, and an operation without
# a value leaves no trace. The binding cannot pass these cases until it is built
# on Rust client 3.0, which reports one result per operation in request order.
# ``strict=True`` turns an unexpected pass into a failure so the mark cannot
# outlive the port.
_NEEDS_RUST_CLIENT_3 = frozenset(
    {
        "reads_keep_request_order_and_duplicates",
        "list_append_then_read_keeps_both_results",
        "list_append_then_list_size",
        "map_read_makes_write_appear_as_none",
        "map_write_makes_write_appear_as_none",
        "map_put_then_map_size",
        "missing_bin_read_appears_as_none_with_map_op",
        "increment_read_and_map_op",
        "bit_read_makes_write_appear_as_none",
        "hll_ops_make_write_appear_as_none",
    }
)


def _param(case: Case) -> Any:
    marks = []
    if case.id in _NEEDS_RUST_CLIENT_3:
        marks.append(
            pytest.mark.xfail(
                strict=True,
                reason="Rust client 2.2 returns operate bins as a HashMap (aerospike-client-rust#183)",
            )
        )
    return pytest.param(case, id=case.id, marks=marks)


def _fresh_key(case: Case, who: str) -> tuple[str, str, str]:
    return (NS, SET, f"{case.id}:{who}")


def _official_result(official_client, case: Case, key) -> tuple[list[tuple[str, Any]], int]:
    """Run the case with the official client on a freshly written record."""
    try:
        official_client.remove(key)
    except aerospike.exception.RecordNotFound:
        pass
    official_client.put(key, case.initial)
    _, meta, ordered = official_client.operate_ordered(key, case.official_ops())
    return ordered, meta["gen"]


@pytest.fixture
async def async_rust_client():
    try:
        c = aerospike_py.AsyncClient(AEROSPIKE_CONFIG)
        await c.connect()
    except Exception as e:
        skip_or_raise(e)
    yield c
    await c.close()


@pytest.mark.parametrize("case", [pytest.param(case, id=case.id) for case in CASES])
def test_official_client_returns_the_recorded_value(case: Case, official_client, cleanup):
    """The recorded expectation is what the official client actually returns."""
    key = _fresh_key(case, "official-pin")
    cleanup.append(key)

    ordered, _ = _official_result(official_client, case, key)

    assert ordered == case.expected


@pytest.mark.parametrize("case", [_param(case) for case in BINDING_CASES])
def test_sync_client_matches_official(case: Case, rust_client, official_client, cleanup):
    official_key = _fresh_key(case, "official")
    rust_key = _fresh_key(case, "sync")
    cleanup.extend([official_key, rust_key])

    expected, expected_gen = _official_result(official_client, case, official_key)

    try:
        rust_client.remove(rust_key)
    except aerospike_py.RecordNotFound:
        pass
    rust_client.put(rust_key, case.initial)
    result = rust_client.operate_ordered(rust_key, case.rust_ops())

    assert [tuple(item) for item in result.ordered_bins] == expected
    assert result.meta.gen == expected_gen


@pytest.mark.parametrize("case", [_param(case) for case in BINDING_CASES])
async def test_async_client_matches_official(case: Case, async_rust_client, official_client, cleanup):
    official_key = _fresh_key(case, "official")
    rust_key = _fresh_key(case, "async")
    cleanup.extend([official_key, rust_key])

    expected, expected_gen = _official_result(official_client, case, official_key)

    try:
        await async_rust_client.remove(rust_key)
    except aerospike_py.RecordNotFound:
        pass
    await async_rust_client.put(rust_key, case.initial)
    result = await async_rust_client.operate_ordered(rust_key, case.rust_ops())

    assert [tuple(item) for item in result.ordered_bins] == expected
    assert result.meta.gen == expected_gen
