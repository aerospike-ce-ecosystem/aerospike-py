"""Integration tests for batch operations (requires Aerospike server)."""

import pytest

import aerospike_py


@pytest.fixture(scope="module")
def client():
    """Create and connect a client for the test module."""
    try:
        c = aerospike_py.client(
            {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
        ).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def cleanup(client):
    """Clean up test keys after each test."""
    keys = []
    yield keys
    for key in keys:
        try:
            client.remove(key)
        except Exception:
            pass


class TestBatchRead:
    def test_batch_read_all_bins(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_get_1"),
            ("test", "demo", "batch_get_2"),
            ("test", "demo", "batch_get_3"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"a": 1})
        client.put(keys[1], {"a": 2})
        client.put(keys[2], {"a": 3})

        result = client.batch_read(keys)
        assert len(result.batch_records) == 3
        for br in result.batch_records:
            assert br.result == 0
            assert br.record is not None
            _, meta, bins = br.record
            assert meta is not None
            assert meta["gen"] >= 1
            assert "a" in bins

    def test_batch_read_specific_bins(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_select_1"),
            ("test", "demo", "batch_select_2"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"a": 1, "b": 2, "c": 3})
        client.put(keys[1], {"a": 10, "b": 20, "c": 30})

        result = client.batch_read(keys, bins=["a", "c"])
        assert len(result.batch_records) == 2
        for br in result.batch_records:
            assert br.result == 0
            _, meta, bins = br.record
            assert meta is not None
            assert "a" in bins
            assert "c" in bins

    def test_batch_read_exists(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_exists_1"),
            ("test", "demo", "batch_exists_2"),
            ("test", "demo", "batch_exists_missing"),
        ]
        cleanup.append(keys[0])
        cleanup.append(keys[1])

        client.put(keys[0], {"val": 1})
        client.put(keys[1], {"val": 2})

        result = client.batch_read(keys, bins=[])
        assert len(result.batch_records) == 3
        assert result.batch_records[0].result == 0
        assert result.batch_records[1].result == 0
        assert result.batch_records[2].result == 2  # KEY_NOT_FOUND

    def test_batch_read_with_missing(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_get_exists"),
            ("test", "demo", "batch_get_missing"),
        ]
        cleanup.append(keys[0])

        client.put(keys[0], {"val": 1})

        result = client.batch_read(keys)
        assert len(result.batch_records) == 2
        # First key exists
        br0 = result.batch_records[0]
        assert br0.result == 0
        assert br0.record is not None
        _, meta0, bins0 = br0.record
        assert meta0 is not None
        assert bins0["val"] == 1
        # Second key missing
        br1 = result.batch_records[1]
        assert br1.result == 2  # KEY_NOT_FOUND
        assert br1.record is None


class TestBatchOperate:
    def test_batch_operate(self, client, cleanup):
        keys = [
            ("test", "demo", "batch_op_1"),
            ("test", "demo", "batch_op_2"),
        ]
        for k in keys:
            cleanup.append(k)

        client.put(keys[0], {"counter": 10})
        client.put(keys[1], {"counter": 20})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        results = client.batch_operate(keys, ops)
        assert len(results) == 2
        _, _, bins0 = results[0]
        _, _, bins1 = results[1]
        # Batch operate returns multi-op results as list per bin
        counter0 = bins0["counter"]
        counter1 = bins1["counter"]
        if isinstance(counter0, list):
            assert counter0[-1] == 15
            assert counter1[-1] == 25
        else:
            assert counter0 == 15
            assert counter1 == 25


class TestBatchRemove:
    def test_batch_remove(self, client):
        keys = [
            ("test", "demo", "batch_rm_1"),
            ("test", "demo", "batch_rm_2"),
        ]

        client.put(keys[0], {"val": 1})
        client.put(keys[1], {"val": 2})

        client.batch_remove(keys)

        for k in keys:
            _, meta = client.exists(k)
            assert meta is None
