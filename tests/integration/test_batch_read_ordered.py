"""Integration tests for batch_read_ordered on both Client and AsyncClient.

Verifies position-preserved list return: each input key maps to its bins
dict at the same index, or ``None`` if not found.
"""

import pytest

NS = "test"
SET = "bro"


@pytest.fixture(autouse=True)
async def _seed_records(async_client, async_cleanup):
    """Seed even-indexed records (0, 2, 4, 6, 8). Odd indices are missing."""
    keys = []
    for i in range(10):
        k = (NS, SET, f"o_{i}")
        if i % 2 == 0:
            async_cleanup.append(k)
            await async_client.put(k, {"i": i, "name": f"name_{i}"})
        keys.append(k)
    yield keys


class TestBatchReadOrderedAsync:
    async def test_preserves_order(self, async_client, _seed_records):
        keys = _seed_records
        result = await async_client.batch_read_ordered(keys)
        assert len(result) == len(keys)
        for i, bins in enumerate(result):
            if i % 2 == 0:
                assert bins is not None
                assert bins["i"] == i
            else:
                assert bins is None

    async def test_missing_keys_are_none(self, async_client, _seed_records):
        # All missing
        keys = [(NS, SET, f"o_{i}") for i in (1, 3, 5)]
        result = await async_client.batch_read_ordered(keys)
        assert result == [None, None, None]

    async def test_duplicate_keys_each_get_a_slot(self, async_client, _seed_records):
        """Duplicate input keys must each receive their own slot in the
        output (server-side dedup must not propagate to the slot count)."""
        k0 = (NS, SET, "o_0")
        result = await async_client.batch_read_ordered([k0, k0, k0])
        assert len(result) == 3
        assert all(r is not None and r["i"] == 0 for r in result)

    async def test_bins_filter(self, async_client, _seed_records):
        keys = [(NS, SET, "o_0"), (NS, SET, "o_2")]
        result = await async_client.batch_read_ordered(keys, bins=["i"])
        assert len(result) == 2
        for bins in result:
            assert bins is not None
            assert "i" in bins
            assert "name" not in bins

    async def test_empty_keys_returns_empty_list(self, async_client, _seed_records):
        result = await async_client.batch_read_ordered([])
        assert result == []


class TestBatchReadOrderedSync:
    def test_preserves_order(self, client, cleanup):
        keys = [(NS, "bro_sync", f"o_{i}") for i in range(6)]
        for i, k in enumerate(keys):
            if i % 2 == 0:
                cleanup.append(k)
                client.put(k, {"i": i})

        result = client.batch_read_ordered(keys)
        assert len(result) == 6
        for i, bins in enumerate(result):
            if i % 2 == 0:
                assert bins is not None and bins["i"] == i
            else:
                assert bins is None

    def test_equivalent_to_dict_lookup(self, client, cleanup):
        """Reordered result must equal the same lookup done via the
        regular batch_read dict — anything else means the reorder
        introduced a bug."""
        keys = [(NS, "bro_sync_eq", f"o_{i}") for i in range(5)]
        for i, k in enumerate(keys):
            cleanup.append(k)
            client.put(k, {"i": i})

        ordered = client.batch_read_ordered(keys)
        dict_form = client.batch_read(keys)
        manual = [dict_form.get(f"o_{i}") for i in range(5)]
        assert ordered == manual
