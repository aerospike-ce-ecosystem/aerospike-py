"""Integration tests for batch_read_many on both Client and AsyncClient.

Verifies that grouping N batch_reads into a single merged call produces
the same per-group dicts as N separate calls (correctness), and that the
input order is preserved on the way back out.
"""

import asyncio

import pytest

NS = "test"


class TestBatchReadManySync:
    def test_returns_list_of_dicts_in_order(self, client, cleanup):
        groups: list[list[tuple[str, str, str]]] = []
        for fv in range(3):
            group = [(NS, f"brm_sync_fv_{fv}", f"u{i}") for i in range(4)]
            for i, k in enumerate(group):
                cleanup.append(k)
                client.put(k, {"fv": fv, "user_idx": i})
            groups.append(group)

        results = client.batch_read_many(groups)
        assert isinstance(results, list)
        assert len(results) == 3
        for fv, group_result in enumerate(results):
            assert isinstance(group_result, dict)
            assert len(group_result) == 4
            for user_idx in range(4):
                rec = group_result[f"u{user_idx}"]
                assert rec["fv"] == fv

    def test_equivalent_to_loop_of_batch_read(self, client, cleanup):
        groups: list[list[tuple[str, str, str]]] = []
        for fv in range(2):
            group = [(NS, f"brm_sync_eq_{fv}", f"u{i}") for i in range(3)]
            for i, k in enumerate(group):
                cleanup.append(k)
                client.put(k, {"fv": fv})
            groups.append(group)

        many = client.batch_read_many(groups)
        loop = [client.batch_read(g) for g in groups]
        assert many == loop


@pytest.fixture(autouse=True)
async def _seed_groups(async_client, async_cleanup):
    """Seed 3 sets × 4 records each. Each set models a feature view."""
    seeds: list[list[tuple[str, str, str]]] = []
    for fv in range(3):
        group = [(NS, f"brm_fv_{fv}", f"u{i}") for i in range(4)]
        for i, k in enumerate(group):
            async_cleanup.append(k)
            await async_client.put(k, {"fv": fv, "user_idx": i})
        seeds.append(group)
    yield seeds


class TestBatchReadMany:
    async def test_returns_list_of_dicts_in_order(self, async_client, _seed_groups):
        groups = _seed_groups
        results = await async_client.batch_read_many(groups)

        assert isinstance(results, list)
        assert len(results) == len(groups)
        for fv, group_result in enumerate(results):
            assert isinstance(group_result, dict)
            assert len(group_result) == 4
            for user_idx in range(4):
                rec = group_result[f"u{user_idx}"]
                assert rec["fv"] == fv
                assert rec["user_idx"] == user_idx

    async def test_empty_group_returns_empty_dict(self, async_client, _seed_groups):
        """An empty key list inside the multi-batch must still produce a
        slot (an empty dict) in the output — preserves positional alignment."""
        groups = [
            _seed_groups[0],
            [],
            _seed_groups[2],
        ]
        results = await async_client.batch_read_many(groups)
        assert len(results) == 3
        assert len(results[0]) == 4
        assert results[1] == {}
        assert len(results[2]) == 4

    async def test_bins_filter_applies_to_all_groups(self, async_client, _seed_groups):
        groups = _seed_groups
        results = await async_client.batch_read_many(groups, bins=["fv"])
        for group_result in results:
            for rec in group_result.values():
                assert "fv" in rec
                assert "user_idx" not in rec

    async def test_equivalent_to_gather_of_batch_read(
        self, async_client, _seed_groups
    ):
        """The fundamental contract: batch_read_many is observationally
        identical to gather(batch_read for each group). Anything else means
        the merge/split logic introduced a bug."""
        groups = _seed_groups

        many_result = await async_client.batch_read_many(groups)
        gather_result = await asyncio.gather(
            *[async_client.batch_read(g) for g in groups]
        )

        assert len(many_result) == len(gather_result)
        for many_dict, gather_dict in zip(many_result, gather_result):
            assert many_dict == gather_dict

    async def test_missing_keys_excluded_from_each_group(
        self, async_client, _seed_groups
    ):
        """Missing keys in a group produce no entry in that group's dict —
        same semantic as batch_read."""
        groups = [
            _seed_groups[0] + [(NS, "brm_fv_0", "no_such_user")],
            _seed_groups[1],
        ]
        results = await async_client.batch_read_many(groups)
        assert len(results[0]) == 4  # missing key omitted
        assert "no_such_user" not in results[0]
        assert len(results[1]) == 4
