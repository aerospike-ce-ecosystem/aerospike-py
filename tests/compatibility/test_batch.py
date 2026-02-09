"""Cross-client batch operation compatibility tests.

Only uses non-deprecated batch APIs: batch_operate, batch_remove.
Verification is done via individual get/exists calls.
"""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")


class TestBatchCrossRead:
    """Bulk put with one client, individual read with the other."""

    def test_rust_put_many_official_get(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"batch_r2o_{i}") for i in range(10)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            rust_client.put(key, {"idx": i, "val": f"item_{i}"})

        for i, key in enumerate(keys):
            _, meta, bins = official_client.get(key)
            assert meta is not None
            assert bins["idx"] == i
            assert bins["val"] == f"item_{i}"

    def test_official_put_many_rust_get(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"batch_o2r_{i}") for i in range(10)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            official_client.put(key, {"idx": i, "val": f"item_{i}"})

        for i, key in enumerate(keys):
            _, meta, bins = rust_client.get(key)
            assert meta is not None
            assert bins["idx"] == i
            assert bins["val"] == f"item_{i}"


class TestBatchRemove:
    def test_official_batch_remove_rust_verify(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"brm_{i}") for i in range(5)]

        for key in keys:
            rust_client.put(key, {"val": 1})

        official_client.batch_remove(keys)

        for key in keys:
            _, meta = rust_client.exists(key)
            assert meta is None

    def test_rust_batch_remove_official_verify(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"brm2_{i}") for i in range(5)]

        for key in keys:
            official_client.put(key, {"val": 1})

        rust_client.batch_remove(keys)

        for key in keys:
            _, meta = official_client.exists(key)
            assert meta is None


class TestBatchOperate:
    def test_rust_put_official_batch_operate(self, rust_client, official_client, cleanup):
        """Rust puts records, official batch_operate increments them."""
        keys = [("test", "compat", f"bop_r2o_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)
            rust_client.put(k, {"counter": 10})

        from aerospike_helpers.operations import operations as op_helpers

        ops = [op_helpers.increment("counter", 5)]
        official_client.batch_operate(keys, ops)

        for key in keys:
            _, _, bins = rust_client.get(key)
            assert bins["counter"] == 15

    def test_official_put_rust_batch_operate(self, rust_client, official_client, cleanup):
        """Official puts records, rust batch_operate increments them."""
        keys = [("test", "compat", f"bop_o2r_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)
            official_client.put(k, {"counter": 10})

        ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5}]
        rust_client.batch_operate(keys, ops)

        for key in keys:
            _, _, bins = official_client.get(key)
            assert bins["counter"] == 15
