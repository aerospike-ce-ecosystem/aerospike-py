"""Cross-client batch operation compatibility tests.

The official aerospike client deprecated get_many/exists_many/select_many
in favour of batch_read.  These tests use the rust client's get_many for
reading and the official client's individual get/exists for verification,
ensuring cross-client data compatibility without relying on deprecated APIs.
"""


class TestBatchGet:
    def test_rust_put_many_official_get(self, rust_client, official_client, cleanup):
        """Rust client puts N records, official client reads them individually."""
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

    def test_official_put_many_rust_get_many(
        self, rust_client, official_client, cleanup
    ):
        """Official client puts N records, rust client batch-reads via get_many."""
        keys = [("test", "compat", f"batch_o2r_{i}") for i in range(10)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            official_client.put(key, {"idx": i, "val": f"item_{i}"})

        results = rust_client.get_many(keys)
        assert len(results) == 10
        for i, (_, meta, bins) in enumerate(results):
            assert meta is not None
            assert bins["idx"] == i
            assert bins["val"] == f"item_{i}"


class TestBatchExists:
    def test_rust_put_official_exists(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"bexist_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)

        for key in keys:
            rust_client.put(key, {"val": 1})

        for key in keys:
            _, meta = official_client.exists(key)
            assert meta is not None
            assert meta["gen"] >= 1


class TestBatchSelect:
    def test_cross_select(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"bsel_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            official_client.put(key, {"a": i, "b": i * 10, "c": i * 100})

        results = rust_client.select_many(keys, ["a", "c"])
        assert len(results) == 5
        for i, (_, meta, bins) in enumerate(results):
            assert meta is not None
            assert bins["a"] == i
            assert bins["c"] == i * 100
            assert "b" not in bins


class TestBatchRemove:
    def test_official_batch_remove_rust_verify(
        self, rust_client, official_client, cleanup
    ):
        keys = [("test", "compat", f"brm_{i}") for i in range(5)]

        for key in keys:
            rust_client.put(key, {"val": 1})

        official_client.batch_remove(keys)

        results = rust_client.exists_many(keys)
        for _, meta in results:
            assert meta is None

    def test_rust_batch_remove_official_verify(
        self, rust_client, official_client, cleanup
    ):
        keys = [("test", "compat", f"brm2_{i}") for i in range(5)]

        for key in keys:
            official_client.put(key, {"val": 1})

        rust_client.batch_remove(keys)

        for key in keys:
            _, meta = official_client.exists(key)
            assert meta is None
