"""Verify that both clients return the same structure for API responses."""


class TestGetReturnFormat:
    """Both clients should return (key, meta, bins) 3-tuple from get()."""

    def test_get_returns_3_tuple(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "ret_3tuple")
        cleanup.append(key)
        rust_client.put(key, {"val": 42})

        rust_result = rust_client.get(key)
        off_result = official_client.get(key)

        assert len(rust_result) == 3
        assert len(off_result) == 3

    def test_meta_has_gen_and_ttl(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "ret_meta")
        cleanup.append(key)
        rust_client.put(key, {"val": 1}, meta={"ttl": 300})

        _, rust_meta, _ = rust_client.get(key)
        _, off_meta, _ = official_client.get(key)

        assert "gen" in rust_meta
        assert "ttl" in rust_meta
        assert "gen" in off_meta
        assert "ttl" in off_meta


class TestExistsReturnFormat:
    """Both clients should return (key, meta) 2-tuple from exists()."""

    def test_exists_returns_2_tuple(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "ret_exists")
        cleanup.append(key)
        rust_client.put(key, {"val": 1})

        rust_result = rust_client.exists(key)
        off_result = official_client.exists(key)

        assert len(rust_result) == 2
        assert len(off_result) == 2

    def test_exists_not_found_meta_none(self, rust_client, official_client):
        key = ("test", "compat", "ret_exists_missing_xyz")

        _, rust_meta = rust_client.exists(key)
        _, off_meta = official_client.exists(key)

        assert rust_meta is None
        assert off_meta is None


class TestGenerationBehavior:
    """Both clients should report the same generation semantics."""

    def test_gen_starts_at_1(self, rust_client, official_client, cleanup):
        key_r = ("test", "compat", "gen_start_rust")
        key_o = ("test", "compat", "gen_start_off")
        cleanup.append(key_r)
        cleanup.append(key_o)

        rust_client.put(key_r, {"val": 1})
        official_client.put(key_o, {"val": 1})

        _, rust_meta, _ = rust_client.get(key_r)
        _, off_meta, _ = official_client.get(key_o)

        assert rust_meta["gen"] == 1
        assert off_meta["gen"] == 1

    def test_gen_increments(self, rust_client, official_client, cleanup):
        key_r = ("test", "compat", "gen_incr_rust")
        key_o = ("test", "compat", "gen_incr_off")
        cleanup.append(key_r)
        cleanup.append(key_o)

        # Write 3 times each
        for i in range(3):
            rust_client.put(key_r, {"val": i})
            official_client.put(key_o, {"val": i})

        _, rust_meta, _ = rust_client.get(key_r)
        _, off_meta, _ = official_client.get(key_o)

        assert rust_meta["gen"] == 3
        assert off_meta["gen"] == 3
