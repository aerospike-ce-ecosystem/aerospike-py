"""Integration tests for async batch_read dict return type.

Tests that AsyncClient.batch_read() returns dict[UserKey, AerospikeRecord]
with zero-GIL-contention async pattern preserved internally.
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


class TestBatchReadDict:
    """Tests for batch_read() returning dict[UserKey, AerospikeRecord]."""

    async def test_returns_dict(self, async_client, _seed_records):
        keys = _seed_records
        result = await async_client.batch_read(keys)
        assert isinstance(result, dict)
        assert len(result) == 5

    async def test_dict_values(self, async_client, _seed_records):
        """Dict maps user_key to bins dict."""
        keys = _seed_records
        result = await async_client.batch_read(keys)

        for i in range(5):
            key_val = f"h_{i}"
            assert key_val in result
            assert result[key_val]["name"] == f"user_{i}"
            assert result[key_val]["score"] == i * 10

    async def test_specific_bins(self, async_client, _seed_records):
        """bins parameter filters returned bins."""
        keys = _seed_records
        result = await async_client.batch_read(keys, bins=["name"])

        for i in range(5):
            bins = result[f"h_{i}"]
            assert "name" in bins
            assert "score" not in bins

    async def test_missing_records_excluded(self, async_client, _seed_records):
        """Missing records are excluded from the dict."""
        keys = _seed_records
        missing = [(NS, SET, "missing_1"), (NS, SET, "missing_2")]
        result = await async_client.batch_read(keys + missing)

        assert len(result) == 5  # Only found records
        assert "missing_1" not in result
        assert "missing_2" not in result

    async def test_empty_keys(self, async_client):
        """Empty keys list returns empty dict."""
        result = await async_client.batch_read([])
        assert result == {}

    async def test_dict_iteration(self, async_client, _seed_records):
        """Standard dict iteration patterns work."""
        keys = _seed_records
        result = await async_client.batch_read(keys)

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

        result = await async_client.batch_read(keys)
        assert len(result) == 3
        for i in range(3):
            assert result[i]["val"] == i * 10


class TestBatchReadConcurrency:
    """Test GIL contention elimination with concurrent batch_read."""

    async def test_concurrent_gather(self, async_client, _seed_records):
        """Multiple concurrent batch_read calls via asyncio.gather."""
        keys = _seed_records

        async def read_task():
            result = await async_client.batch_read(keys)
            assert len(result) == 5
            return result

        results = await asyncio.gather(*(read_task() for _ in range(8)))
        assert len(results) == 8
        for d in results:
            assert isinstance(d, dict)
            assert len(d) == 5
