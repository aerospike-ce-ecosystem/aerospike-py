"""Cross-client batch operation compatibility tests."""


class TestBatchGet:
    def test_rust_put_many_official_get_many(
        self, rust_client, official_client, cleanup
    ):
        keys = [("test", "compat", f"batch_r2o_{i}") for i in range(10)]
        for k in keys:
            cleanup.append(k)

        for i, key in enumerate(keys):
            rust_client.put(key, {"idx": i, "val": f"item_{i}"})

        results = official_client.get_many(keys)
        assert len(results) == 10
        for i, (_, meta, bins) in enumerate(results):
            assert meta is not None
            assert bins["idx"] == i
            assert bins["val"] == f"item_{i}"

    def test_official_put_many_rust_get_many(
        self, rust_client, official_client, cleanup
    ):
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
    def test_cross_exists_many(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"bexist_{i}") for i in range(5)]
        for k in keys:
            cleanup.append(k)

        for key in keys:
            rust_client.put(key, {"val": 1})

        results = official_client.exists_many(keys)
        assert len(results) == 5
        for _, meta in results:
            assert meta is not None
            assert meta["gen"] >= 1


class TestBatchSelect:
    def test_cross_select_many(self, rust_client, official_client, cleanup):
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
    def test_cross_batch_remove(self, rust_client, official_client, cleanup):
        keys = [("test", "compat", f"brm_{i}") for i in range(5)]

        for key in keys:
            rust_client.put(key, {"val": 1})

        official_client.batch_remove(keys)

        results = rust_client.exists_many(keys)
        for _, meta in results:
            assert meta is None
