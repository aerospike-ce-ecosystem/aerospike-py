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
no value (``(name, None)``); delete has an empty name and touch is omitted.
Outside that mode, a read of a nil list element appears in a request that
writes, and is omitted in a read-only request.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable

import pytest

import aerospike_py
import aerospike_py.bit_operations as rust_bit
import aerospike_py.hll_operations as rust_hll
import aerospike_py.list_operations as rust_lop
import aerospike_py.map_operations as rust_mop
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
    Case(
        id="empty_name_reads_every_bin",
        initial={"a": 1, "b": 2},
        official_ops=lambda: [off_ops.read("")],
        rust_ops=lambda: [_read("")],
        expected=[("a", 1), ("b", 2)],
    ),
    Case(
        id="whole_record_read_with_named_read",
        initial={"a": 1, "b": 2},
        official_ops=lambda: [off_ops.read(""), off_ops.read("a")],
        rust_ops=lambda: [_read(""), _read("a")],
        expected=[("a", 1), ("b", 2)],
    ),
    Case(
        id="nil_list_read_and_missing_list_in_a_write",
        initial={"l": [None, 5], "b": 2},
        official_ops=lambda: [
            off_ops.touch(),
            off_lop.list_get("l", 0),
            off_lop.list_get("no_list", 0),
            off_ops.read("b"),
            off_lop.list_get("l", 1),
        ],
        rust_ops=lambda: [
            _touch(),
            rust_lop.list_get("l", 0),
            rust_lop.list_get("no_list", 0),
            _read("b"),
            rust_lop.list_get("l", 1),
        ],
        expected=[("l", None), ("b", 2), ("l", 5)],
    ),
    Case(
        id="check_list_presence_at_the_operation",
        initial={"l": [None]},
        official_ops=lambda: [off_lop.list_get("l", 0), off_ops.write("l", None), off_lop.list_get("l", 0)],
        rust_ops=lambda: [rust_lop.list_get("l", 0), _write("l", None), rust_lop.list_get("l", 0)],
        expected=[("l", None)],
    ),
    Case(
        id="delete_has_an_empty_name_in_respond_all_mode",
        initial={"m": {"k": 1}},
        official_ops=lambda: [off_mop.map_size("m"), off_ops.delete()],
        rust_ops=lambda: [rust_mop.map_size("m"), {"op": aerospike_py.OPERATOR_DELETE}],
        expected=[("m", 1), ("", None)],
    ),
    Case(
        id="touch_ignores_an_extraneous_bin_name",
        initial={"m": {"k": 1}},
        official_ops=lambda: [dict(off_ops.touch(), bin="ignored"), off_mop.map_size("m")],
        rust_ops=lambda: [dict(_touch(), bin="ignored"), rust_mop.map_size("m")],
        expected=[("m", 1)],
    ),
    Case(
        id="key_value_result_is_a_flat_list",
        initial={"m": {"j": 2, "k": 1}},
        official_ops=lambda: [off_mop.map_get_by_key_list("m", ["j", "k"], aerospike.MAP_RETURN_KEY_VALUE)],
        rust_ops=lambda: [rust_mop.map_get_by_key_list("m", ["j", "k"], aerospike_py.MAP_RETURN_KEY_VALUE)],
        expected=[("m", ["j", 2, "k", 1])],
    ),
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
    # ── a list read that finds nil, in a request that only reads ──────
    # The server leaves such a read out. The binding once gave the bin's one
    # answer to every operation that named the bin, which reported l[0] as 5.
    Case(
        id="list_read_of_a_nil_element_is_omitted",
        initial={"l": [None, 5]},
        official_ops=lambda: [off_lop.list_get("l", 0), off_lop.list_get("l", 1)],
        rust_ops=lambda: [rust_lop.list_get("l", 0), rust_lop.list_get("l", 1)],
        expected=[("l", 5)],
    ),
    Case(
        id="nil_element_between_two_values",
        initial={"l": [7, None, 9]},
        official_ops=lambda: [off_lop.list_get("l", 0), off_lop.list_get("l", 1), off_lop.list_get("l", 2)],
        rust_ops=lambda: [rust_lop.list_get("l", 0), rust_lop.list_get("l", 1), rust_lop.list_get("l", 2)],
        expected=[("l", 7), ("l", 9)],
    ),
    Case(
        id="nil_elements_of_two_bins_keep_the_order_of_the_answers",
        initial={"l": [None, 5], "k": [5, None]},
        official_ops=lambda: [
            off_lop.list_get("l", 0),
            off_lop.list_get("k", 0),
            off_lop.list_get("l", 1),
            off_lop.list_get("k", 1),
        ],
        rust_ops=lambda: [
            rust_lop.list_get("l", 0),
            rust_lop.list_get("k", 0),
            rust_lop.list_get("l", 1),
            rust_lop.list_get("k", 1),
        ],
        expected=[("k", 5), ("l", 5)],
    ),
    Case(
        id="list_read_that_returns_nothing_then_list_size",
        initial={"l": [1, 2, 3]},
        official_ops=lambda: [
            off_lop.list_get_by_index("l", 0, aerospike.LIST_RETURN_NONE),
            off_lop.list_size("l"),
        ],
        rust_ops=lambda: [
            rust_lop.list_get_by_index("l", 0, aerospike_py.LIST_RETURN_NONE),
            rust_lop.list_size("l"),
        ],
        expected=[("l", 3)],
    ),
]

BINDING_CASES = [case for case in CASES if case.rust_ops is not None]


def _fresh_key(case: Case, who: str) -> tuple[str, str, str]:
    return (NS, SET, f"{case.id}:{who}")


def _official_result(official_client, case: Case, key) -> tuple[list[tuple[str, Any]], int]:
    """Run the case with the official client on a freshly written record."""
    with suppress(aerospike.exception.RecordNotFound):
        official_client.remove(key)
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


@pytest.mark.parametrize("case", [pytest.param(case, id=case.id) for case in BINDING_CASES])
def test_sync_client_matches_official(case: Case, rust_client, official_client, cleanup):
    official_key = _fresh_key(case, "official")
    rust_key = _fresh_key(case, "sync")
    cleanup.extend([official_key, rust_key])

    expected, expected_gen = _official_result(official_client, case, official_key)

    with suppress(aerospike_py.RecordNotFound):
        rust_client.remove(rust_key)
    rust_client.put(rust_key, case.initial)
    result = rust_client.operate_ordered(rust_key, case.rust_ops())

    assert [tuple(item) for item in result.ordered_bins] == expected
    assert result.meta.gen == expected_gen


@pytest.mark.parametrize("case", [pytest.param(case, id=case.id) for case in BINDING_CASES])
async def test_async_client_matches_official(case: Case, async_rust_client, official_client, cleanup):
    official_key = _fresh_key(case, "official")
    rust_key = _fresh_key(case, "async")
    cleanup.extend([official_key, rust_key])

    expected, expected_gen = _official_result(official_client, case, official_key)

    with suppress(aerospike_py.RecordNotFound):
        await async_rust_client.remove(rust_key)
    await async_rust_client.put(rust_key, case.initial)
    result = await async_rust_client.operate_ordered(rust_key, case.rust_ops())

    assert [tuple(item) for item in result.ordered_bins] == expected
    assert result.meta.gen == expected_gen
