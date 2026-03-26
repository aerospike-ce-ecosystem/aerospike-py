"""Integration tests for AsyncClient (requires Aerospike server).

Note: CRUD, batch_read, exists, touch, increment, and operate tests are
covered by ``test_scenarios.py`` via the ``any_client`` fixture (sync+async).
This file only contains async-specific tests (connection management) and
batch_operate scenarios not yet covered by any_client tests.
"""

import aerospike_py


class TestAsyncConnection:
    async def test_is_connected(self, async_client):
        assert async_client.is_connected()

    async def test_close(self, async_client):
        assert async_client.is_connected()
        await async_client.close()
        assert not async_client.is_connected()

    async def test_get_node_names(self, async_client):
        """get_node_names() is sync on AsyncClient since alpha.10 — no await."""
        names = async_client.get_node_names()
        assert isinstance(names, list)
        assert len(names) > 0
        assert all(isinstance(n, str) for n in names)


class TestAsyncBatchWrite:
    """Test async batch_operate used as batch write (OPERATOR_WRITE)."""

    async def test_async_batch_write_new_records(self, async_client):
        keys = [
            ("test", "demo", "async_bw_1"),
            ("test", "demo", "async_bw_2"),
            ("test", "demo", "async_bw_3"),
        ]
        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "name", "val": "async_test"},
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "score", "val": 200},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 3
        for br in results.batch_records:
            assert br.result == 0

        # Verify records were written
        for k in keys:
            _, meta, bins = await async_client.get(k)
            assert meta is not None
            assert bins["name"] == "async_test"
            assert bins["score"] == 200
        await async_client.batch_remove(keys)

    async def test_async_batch_write_partial_failure(self, async_client):
        """OPERATOR_INCR on string bin causes per-record failure."""
        keys = [
            ("test", "demo", "async_bwf_ok"),
            ("test", "demo", "async_bwf_fail"),
        ]
        await async_client.put(keys[0], {"counter": 10})
        await async_client.put(keys[1], {"counter": "not_a_number"})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2

        # First record succeeds
        br0 = results.batch_records[0]
        assert br0.result == 0
        assert br0.record is not None
        assert br0.record.meta is not None

        # Second record fails (type mismatch)
        br1 = results.batch_records[1]
        assert br1.result != 0
        assert br1.record is None

        await async_client.batch_remove(keys)

    async def test_async_batch_write_with_read_back(self, async_client):
        keys = [
            ("test", "demo", "async_bwr_1"),
            ("test", "demo", "async_bwr_2"),
        ]
        ops = [
            {"op": aerospike_py.OPERATOR_WRITE, "bin": "val", "val": 77},
            {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
        ]
        results = await async_client.batch_operate(keys, ops)
        assert len(results.batch_records) == 2
        for br in results.batch_records:
            assert br.result == 0
            assert br.record is not None
            val = br.record.bins["val"]
            if isinstance(val, list):
                assert val[-1] == 77
            else:
                assert val == 77
        await async_client.batch_remove(keys)
