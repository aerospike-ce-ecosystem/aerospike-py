"""Integration tests for `batch_read()` returning a `LazyBatchRecords`.

The async path completes with near-zero GIL hold (Arc::new + Py::new);
materialisation is via ``lazy_records.to_dict()`` /
``lazy_records.to_numpy(dtype)`` in the calling coroutine, so concurrent
``batch_read`` futures release their ``spawn_blocking`` threads almost
immediately.
"""

import asyncio

import pytest

NS = "test"
SET = "lazy_batch_records"


@pytest.fixture(autouse=True)
async def _seed_records(async_client, async_cleanup):
    """Seed 5 records and clean up after each test."""
    keys = [(NS, SET, f"h_{i}") for i in range(5)]
    for i, k in enumerate(keys):
        async_cleanup.append(k)
        await async_client.put(k, {"name": f"user_{i}", "score": i * 10})
    yield keys


class TestLazyBatchRecordsDict:
    """Tests for ``batch_read().to_dict()`` returning dict[UserKey, AerospikeRecord]."""

    async def test_returns_lazy_records(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)
        # batch_read no longer eagerly materialises; .to_dict() does.
        assert not isinstance(lazy_records, dict)
        result = lazy_records.to_dict()
        assert isinstance(result, dict)
        assert len(result) == 5

    async def test_dict_values(self, async_client, _seed_records):
        """Dict maps user_key to bins dict."""
        keys = _seed_records
        result = (await async_client.batch_read(keys)).to_dict()

        for i in range(5):
            key_val = f"h_{i}"
            assert key_val in result
            assert result[key_val]["name"] == f"user_{i}"
            assert result[key_val]["score"] == i * 10

    async def test_specific_bins(self, async_client, _seed_records):
        """bins parameter filters returned bins."""
        keys = _seed_records
        result = (await async_client.batch_read(keys, bins=["name"])).to_dict()

        for i in range(5):
            bins = result[f"h_{i}"]
            assert "name" in bins
            assert "score" not in bins

    async def test_missing_records_excluded(self, async_client, _seed_records):
        """Missing records are excluded from the dict."""
        keys = _seed_records
        missing = [(NS, SET, "missing_1"), (NS, SET, "missing_2")]
        result = (await async_client.batch_read(keys + missing)).to_dict()

        assert len(result) == 5  # Only found records
        assert "missing_1" not in result
        assert "missing_2" not in result

    async def test_empty_keys(self, async_client):
        """Empty keys list yields an empty dict via .to_dict()."""
        result = (await async_client.batch_read([])).to_dict()
        assert result == {}

    async def test_dict_iteration(self, async_client, _seed_records):
        """Standard dict iteration patterns work on .to_dict()."""
        keys = _seed_records
        result = (await async_client.batch_read(keys)).to_dict()

        # items()
        for user_key, bins_dict in result.items():
            assert isinstance(user_key, str)
            assert isinstance(bins_dict, dict)
            assert "name" in bins_dict

        # keys()
        assert set(result.keys()) == {f"h_{i}" for i in range(5)}

    async def test_integer_keys(self, async_client, async_cleanup):
        """Integer user keys work correctly."""
        keys = [(NS, SET, i) for i in range(3)]
        for k in keys:
            async_cleanup.append(k)
            await async_client.put(k, {"val": k[2] * 10})

        result = (await async_client.batch_read(keys)).to_dict()
        assert len(result) == 3
        for i in range(3):
            assert result[i]["val"] == i * 10


class TestBatchReadConcurrency:
    """Test GIL contention elimination with concurrent batch_read."""

    async def test_concurrent_gather(self, async_client, _seed_records):
        """Multiple concurrent batch_read calls via asyncio.gather."""
        keys = _seed_records

        async def read_task():
            lazy_records = await async_client.batch_read(keys)
            result = lazy_records.to_dict()
            assert len(result) == 5
            return result

        results = await asyncio.gather(*(read_task() for _ in range(8)))
        assert len(results) == 8
        for d in results:
            assert isinstance(d, dict)
            assert len(d) == 5


class TestLazyBatchRecordsMapping:
    """Direct tests for the dict-style Mapping protocol on the `LazyBatchRecords`.

    The other dict tests go through ``.to_dict()`` and assert on the
    resulting plain ``dict``. This class exercises the `LazyBatchRecords`'s
    own ``__getitem__`` / ``__contains__`` / ``__iter__`` / ``__len__`` /
    ``keys`` / ``values`` / ``items`` / ``get`` so a regression dropping
    any single dunder from ``#[pymethods]`` is caught.
    """

    async def test_len_is_dict_view_cardinality(self, async_client, _seed_records):
        """``len(lazy_records)`` matches ``len(lazy_records.to_dict())`` —
        missing reads and per-record failures are excluded. The raw record
        count is available via ``len(lazy_records.batch_records)``."""
        keys = _seed_records
        missing = [(NS, SET, "missing_X"), (NS, SET, "missing_Y")]
        lazy_records = await async_client.batch_read(keys + missing)

        # Dict-view cardinality: only the 5 found records
        assert len(lazy_records) == len(keys)
        assert len(lazy_records) == len(lazy_records.to_dict())
        # Raw record count (includes missing reads) lives on `batch_records`
        assert len(lazy_records.batch_records) == len(keys) + len(missing)

    async def test_contains_iter_keys_values_items(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        assert "h_0" in lazy_records
        assert "not_a_key" not in lazy_records
        assert sorted(iter(lazy_records)) == sorted(f"h_{i}" for i in range(5))
        assert set(lazy_records.keys()) == {f"h_{i}" for i in range(5)}
        assert all(isinstance(v, dict) and "name" in v for v in lazy_records.values())
        assert {k: v["name"] for k, v in lazy_records.items()} == {f"h_{i}": f"user_{i}" for i in range(5)}

    async def test_getitem_raises_keyerror_for_missing(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        with pytest.raises(KeyError):
            _ = lazy_records["missing_record"]

    async def test_get_returns_default_for_missing(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        # default=None
        assert lazy_records.get("missing_record") is None
        # explicit default
        sentinel = {"_": "_"}
        assert lazy_records.get("missing_record", sentinel) is sentinel
        # present key
        assert lazy_records.get("h_2")["name"] == "user_2"

    async def test_dict_view_matches_keys_view(self, async_client, _seed_records):
        """``set(lazy_records.keys()) == set(lazy_records.to_dict().keys())`` invariant."""
        keys = _seed_records
        missing = [(NS, SET, "missing_Z")]
        lazy_records = await async_client.batch_read(keys + missing)
        assert set(lazy_records.keys()) == set(lazy_records.to_dict().keys())


class TestLazyBatchRecordsConversionCache:
    """``to_dict()`` returns a fresh shallow copy so mutation cannot poison
    the cached dict view used by the Mapping-protocol dunders."""

    async def test_to_dict_fresh_copy_does_not_poison_cache(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        d1 = lazy_records.to_dict()
        d1["mutated_after_to_dict"] = {"name": "ghost"}
        # The Mapping-protocol view is independent of the caller's mutation
        assert "mutated_after_to_dict" not in lazy_records
        # A second `to_dict()` is also unaffected
        assert "mutated_after_to_dict" not in lazy_records.to_dict()


class TestLazyBatchRecordsAllRecordsViews:
    """``iter_records`` / ``all_user_keys`` expose every batch record,
    including digest-only and per-record-failed entries that the dict
    view filters out."""

    async def test_iter_records_includes_missing(self, async_client, _seed_records):
        keys = _seed_records
        missing = [(NS, SET, "missing_iter")]
        lazy_records = await async_client.batch_read(keys + missing)

        all_records = list(lazy_records.iter_records())
        # Every batch entry is present, including the missing one
        assert len(all_records) == len(keys) + len(missing)
        # Dict view filters the missing entry out
        assert len(lazy_records.to_dict()) == len(keys)

    async def test_all_user_keys_includes_missing(self, async_client, _seed_records):
        keys = _seed_records
        missing_key = (NS, SET, "missing_raw")
        lazy_records = await async_client.batch_read([*keys, missing_key])

        raw = list(lazy_records.all_user_keys())
        assert "missing_raw" in raw
        # Order matches the request order
        assert raw == [f"h_{i}" for i in range(5)] + ["missing_raw"]


class TestLazyBatchRecordsMerge:
    """``merge_to_dict`` (single-GIL merge of multiple `LazyBatchRecords`)."""

    async def test_merge_to_dict_combines_lazy_records(self, async_client, async_cleanup):
        from aerospike_py import LazyBatchRecords

        keys_a = [(NS, SET, f"merge_a_{i}") for i in range(3)]
        keys_b = [(NS, SET, f"merge_b_{i}") for i in range(2)]
        for k in keys_a + keys_b:
            async_cleanup.append(k)
            await async_client.put(k, {"v": k[2]})

        ra = await async_client.batch_read(keys_a)
        rb = await async_client.batch_read(keys_b)

        merged = LazyBatchRecords.merge_to_dict([ra, rb])
        assert len(merged) == 2
        assert set(merged[0].keys()) == {f"merge_a_{i}" for i in range(3)}
        assert set(merged[1].keys()) == {f"merge_b_{i}" for i in range(2)}

    async def test_merge_to_dict_empty_list(self):
        from aerospike_py import LazyBatchRecords

        assert LazyBatchRecords.merge_to_dict([]) == []
