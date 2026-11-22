"""Size and copy contract of the ``LazyBatchRecords`` handle returned by ``batch_read``.

- ``len(handle)`` is the number of distinct Mapping keys, so it always equals
  ``len(handle.to_dict())``. It used to count successful user-keyed rows, which
  overcounted whenever a user key was requested twice (or in two sets): those
  rows share one Mapping entry.
- ``found_count()`` counts successful rows, so it differs from ``len(handle)``
  when keys repeat and when rows were requested by digest only.
- ``to_list()`` has one slot per request, in request order, ``None`` for a miss.
- ``to_dict()`` is a shallow copy of the cached dict view: the outer dict is
  new, the bins dicts inside it are shared with the handle.
"""

import pytest

from tests.helpers import invoke

NS = "test"
SET = "lazy_batch_len_contract"
SET_B = "lazy_batch_len_contract_b"

# Stored records, by request name. ``a_in_b`` has the same user key as ``a``
# but lives in another set.
STORED = {
    "a": ((NS, SET, "a"), {"v": 1, "src": "a"}),
    "b": ((NS, SET, "b"), {"v": 2}),
    "int": ((NS, SET, 7), {"v": 3}),
    "bytes": ((NS, SET, b"raw"), {"v": 4}),
    "a_in_b": ((NS, SET_B, "a"), {"v": 10, "src": "b"}),
}
MISSING = {
    "missing": (NS, SET, "missing"),
    "missing2": (NS, SET, 404),
}

# Bins each request name is expected to return, ``None`` for a miss.
# ``digest_b`` reads record ``b`` by digest; ``digest_missing`` reads a key
# that was never written, by digest.
EXPECTED_BINS = {
    **{name: bins for name, (_, bins) in STORED.items()},
    "missing": None,
    "missing2": None,
    "digest_b": STORED["b"][1],
    "digest_missing": None,
}

# (requests, len(handle), set of Mapping keys, found_count())
SCENARIOS = [
    pytest.param(["a", "b", "int", "bytes"], 4, {"a", "b", 7, b"raw"}, 4, id="distinct"),
    pytest.param(["a", "a", "b"], 2, {"a", "b"}, 3, id="same_key_twice"),
    pytest.param(["a", "a_in_b"], 1, {"a"}, 2, id="same_key_two_sets"),
    pytest.param(["a", "missing", "b", "missing2"], 2, {"a", "b"}, 2, id="some_missing"),
    pytest.param(["missing", "missing2"], 0, set(), 0, id="all_missing"),
    pytest.param(["a", "digest_b", "digest_missing"], 1, {"a"}, 2, id="digest_only"),
    pytest.param(["int", "int", "bytes", "bytes"], 2, {7, b"raw"}, 4, id="int_and_bytes_twice"),
    pytest.param(
        ["a", "a", "digest_b", "missing", "int", "a_in_b", "bytes", "bytes"],
        3,
        {"a", 7, b"raw"},
        7,
        id="everything",
    ),
    pytest.param([], 0, set(), 0, id="empty"),
]


@pytest.fixture
async def request_keys(any_client, any_cleanup):
    """Write the stored records and return ``name -> request key``."""
    keys = {}
    for name, (key, bins) in STORED.items():
        any_cleanup.append(key)
        await invoke(any_client, "put", key, dict(bins))
        keys[name] = key
    keys.update(MISSING)

    # batch_records[i].key is (ns, set, user_key, digest), also for a miss.
    handle = await invoke(any_client, "batch_read", [keys["b"], keys["missing"]])
    digest_b, digest_missing = (br.key[3] for br in handle.batch_records)
    keys["digest_b"] = (NS, SET, None, digest_b)
    keys["digest_missing"] = (NS, SET, None, digest_missing)
    return keys


class TestLenMatchesTheDictView:
    @pytest.mark.parametrize(("names", "expected_len", "expected_keys", "expected_found"), SCENARIOS)
    async def test_len_to_dict_found_count_and_to_list(
        self, any_client, request_keys, names, expected_len, expected_keys, expected_found
    ):
        handle = await invoke(any_client, "batch_read", [request_keys[n] for n in names])

        # len() on a fresh handle, before any dict view exists.
        assert len(handle) == expected_len
        as_dict = handle.to_dict()
        assert len(as_dict) == expected_len
        assert set(as_dict) == expected_keys
        # len() again, now that the dict view is cached: same answer.
        assert len(handle) == expected_len

        # Rows, not keys.
        assert handle.found_count() == expected_found
        assert [br.result for br in handle.batch_records].count(0) == expected_found

        # One slot per request, in request order.
        assert handle.to_list() == [EXPECTED_BINS[n] for n in names]

    @pytest.mark.parametrize(("names", "expected_len", "expected_keys", "expected_found"), SCENARIOS)
    async def test_len_is_stable_across_cache_states(
        self, any_client, request_keys, names, expected_len, expected_keys, expected_found
    ):
        """``len()`` agrees whether the dict view was built by a Mapping access or dropped again."""
        handle = await invoke(any_client, "batch_read", [request_keys[n] for n in names])

        assert ("no such key" in handle) is False  # builds the cached view
        assert len(handle) == expected_len
        assert len(list(handle)) == expected_len
        assert len(handle.keys()) == expected_len

        handle.release_cache()
        assert len(handle) == expected_len
        assert set(handle.to_dict()) == expected_keys

    async def test_same_user_key_in_two_sets_keeps_the_later_row(self, any_client, request_keys):
        """Both rows are found and both stay in ``to_list()``; the Mapping holds one of them.

        The later request wins, as it does in the NumPy key index.
        """
        handle = await invoke(any_client, "batch_read", [request_keys["a"], request_keys["a_in_b"]])

        assert handle["a"] == STORED["a_in_b"][1]
        assert handle.to_list() == [STORED["a"][1], STORED["a_in_b"][1]]
        assert (len(handle), handle.found_count()) == (1, 2)


class TestToDictIsAShallowCopy:
    async def test_adding_or_removing_keys_affects_only_the_copy(self, any_client, request_keys):
        handle = await invoke(any_client, "batch_read", [request_keys["a"], request_keys["b"]])
        copy = handle.to_dict()

        copy["ghost"] = {"v": -1}
        del copy["a"]

        assert "ghost" not in handle
        assert "a" in handle
        assert handle["a"] == STORED["a"][1]
        assert len(handle) == 2
        fresh = handle.to_dict()
        assert fresh is not copy
        assert fresh == {"a": STORED["a"][1], "b": STORED["b"][1]}

    async def test_bins_dicts_are_shared_with_the_handle(self, any_client, request_keys):
        """Mutating a bins dict in place is visible through ``handle[key]`` and later ``to_dict()``."""
        handle = await invoke(any_client, "batch_read", [request_keys["a"], request_keys["b"]])
        bins = handle.to_dict()["a"]

        bins["v"] = 1000
        bins["added"] = True

        expected = {"v": 1000, "src": "a", "added": True}
        assert handle["a"] == expected
        assert handle.get("a") == expected
        assert handle.to_dict()["a"] == expected
        assert handle.to_dict()["a"] is bins
        assert handle["a"] is bins
        # The other entry is untouched.
        assert handle["b"] == STORED["b"][1]

    async def test_to_list_returns_fresh_dicts_every_call(self, any_client, request_keys):
        handle = await invoke(any_client, "batch_read", [request_keys["a"], request_keys["missing"]])
        first = handle.to_list()
        second = handle.to_list()

        assert first == second == [STORED["a"][1], None]
        assert first is not second
        assert first[0] is not second[0]

        first[0]["v"] = -5
        assert handle.to_list()[0] == STORED["a"][1]
        assert second[0] == STORED["a"][1]

    async def test_to_list_does_not_see_edits_to_the_shared_dict_view(self, any_client, request_keys):
        """``to_list()`` converts from the stored rows, not from the cached dict view."""
        handle = await invoke(any_client, "batch_read", [request_keys["a"]])
        handle["a"]["v"] = 1000

        listed = handle.to_list()

        assert listed == [STORED["a"][1]]
        assert listed[0] is not handle["a"]
