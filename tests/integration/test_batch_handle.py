"""Integration tests for BatchReadHandle (async batch_read zero-conversion handle).

Tests the BatchReadHandle returned by AsyncClient.batch_read(), including:
- as_dict() fast path
- batch_records compatibility path (NamedTuple conversion)
- found_count() / keys() / len()
- Concurrent gather with multiple batch_read calls
"""

import asyncio

import pytest


NS = "test"
SET = "batch_handle"


@pytest.fixture(autouse=True)
async def _seed_records(async_client, async_cleanup):
    """Seed 5 records and clean up after each test."""
    keys = [(NS, SET, f"h_{i}") for i in range(5)]
    for i, k in enumerate(keys):
        async_cleanup.append(k)
        await async_client.put(k, {"name": f"user_{i}", "score": i * 10})
    yield keys


class TestBatchReadHandle:
    """Tests for BatchReadHandle API."""

    async def test_len(self, async_client, _seed_records):
        keys = _seed_records
        handle = await async_client.batch_read(keys)
        assert len(handle) == 5

    async def test_as_dict(self, async_client, _seed_records):
        """as_dict() returns dict[key, bins_dict] for found records."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)
        d = handle.as_dict()

        assert isinstance(d, dict)
        assert len(d) == 5
        for i in range(5):
            key_val = f"h_{i}"
            assert key_val in d
            assert d[key_val]["name"] == f"user_{i}"
            assert d[key_val]["score"] == i * 10

    async def test_as_dict_specific_bins(self, async_client, _seed_records):
        """as_dict() with bins filter only returns requested bins."""
        keys = _seed_records
        handle = await async_client.batch_read(keys, bins=["name"])
        d = handle.as_dict()

        for i in range(5):
            bins = d[f"h_{i}"]
            assert "name" in bins
            assert "score" not in bins

    async def test_batch_records_compat(self, async_client, _seed_records):
        """batch_records property returns list[BatchRecord] NamedTuples."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)

        records = handle.batch_records
        assert len(records) == 5

        for i, br in enumerate(records):
            assert br.result == 0
            assert br.record is not None
            # NamedTuple attribute access
            assert br.record.bins is not None
            assert br.record.meta is not None
            assert br.record.meta.gen >= 1
            # Key NamedTuple
            assert br.key is not None

    async def test_batch_records_tuple_unpacking(self, async_client, _seed_records):
        """batch_records support tuple unpacking pattern."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)

        for br in handle.batch_records:
            if br.result == 0 and br.record is not None:
                _, meta, bins = br.record
                assert meta is not None
                assert isinstance(bins, dict)

    async def test_batch_records_cached(self, async_client, _seed_records):
        """batch_records property is cached (same list on repeated access)."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)

        first = handle.batch_records
        second = handle.batch_records
        assert first is second

    async def test_found_count(self, async_client, _seed_records):
        """found_count() counts successful records without conversion."""
        keys = _seed_records
        # Add a non-existent key
        all_keys = keys + [(NS, SET, "nonexistent_key")]
        handle = await async_client.batch_read(all_keys)

        assert handle.found_count() == 5
        assert len(handle) == 6

    async def test_keys(self, async_client, _seed_records):
        """keys() extracts user keys without record conversion."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)
        result_keys = handle.keys()

        assert len(result_keys) == 5
        assert set(result_keys) == {f"h_{i}" for i in range(5)}

    async def test_iter(self, async_client, _seed_records):
        """Iteration over handle yields BatchRecord NamedTuples."""
        keys = _seed_records
        handle = await async_client.batch_read(keys)

        count = 0
        for br in handle:
            assert br.result == 0
            count += 1
        assert count == 5

    async def test_missing_records(self, async_client, _seed_records):
        """Handle correctly represents missing records."""
        keys = _seed_records
        missing = [(NS, SET, "missing_1"), (NS, SET, "missing_2")]
        handle = await async_client.batch_read(keys + missing)

        assert len(handle) == 7
        assert handle.found_count() == 5

        d = handle.as_dict()
        assert len(d) == 5  # Only found records in dict
        assert "missing_1" not in d

    async def test_empty_keys(self, async_client):
        """Handle works with empty keys list."""
        handle = await async_client.batch_read([])
        assert len(handle) == 0
        assert handle.as_dict() == {}
        assert handle.batch_records == []
        assert handle.found_count() == 0
        assert handle.keys() == []


class TestBatchReadHandleConcurrency:
    """Test GIL contention elimination with concurrent batch_read."""

    async def test_concurrent_gather(self, async_client, _seed_records):
        """Multiple concurrent batch_read calls via asyncio.gather."""
        keys = _seed_records

        async def read_task():
            handle = await async_client.batch_read(keys)
            assert len(handle) == 5
            d = handle.as_dict()
            assert len(d) == 5
            return d

        results = await asyncio.gather(*(read_task() for _ in range(8)))
        assert len(results) == 8
        for d in results:
            assert len(d) == 5

    async def test_concurrent_mixed_access(self, async_client, _seed_records):
        """Concurrent tasks using different access paths on handles."""
        keys = _seed_records

        async def dict_task():
            handle = await async_client.batch_read(keys)
            return handle.as_dict()

        async def records_task():
            handle = await async_client.batch_read(keys)
            return handle.batch_records

        dict_results = await asyncio.gather(*(dict_task() for _ in range(4)))
        record_results = await asyncio.gather(*(records_task() for _ in range(4)))

        for d in dict_results:
            assert len(d) == 5
        for records in record_results:
            assert len(records) == 5
