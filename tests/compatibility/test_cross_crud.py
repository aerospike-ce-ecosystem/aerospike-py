"""Cross-client CRUD tests: one client writes, the other reads."""

import pytest

aerospike = pytest.importorskip("aerospike")


class TestCrossWrite:
    """Test that data written by one client can be read by the other."""

    def test_rust_put_official_get(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "rust_put_off_get")
        cleanup.append(key)

        rust_client.put(key, {"name": "Alice", "age": 30})
        _, meta, bins = official_client.get(key)

        assert bins["name"] == "Alice"
        assert bins["age"] == 30
        assert meta["gen"] >= 1

    def test_official_put_rust_get(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "off_put_rust_get")
        cleanup.append(key)

        official_client.put(key, {"name": "Bob", "age": 25})
        _, meta, bins = rust_client.get(key)

        assert bins["name"] == "Bob"
        assert bins["age"] == 25
        assert meta.gen >= 1


class TestCrossExists:
    """Test exists() across clients."""

    def test_rust_put_official_exists(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "rust_put_off_exists")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})
        _, meta = official_client.exists(key)

        assert meta is not None
        assert meta["gen"] >= 1

    def test_official_put_rust_exists(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "off_put_rust_exists")
        cleanup.append(key)

        official_client.put(key, {"val": 1})
        _, meta = rust_client.exists(key)

        assert meta is not None
        assert meta.gen >= 1


class TestCrossRemove:
    """Test remove across clients."""

    def test_rust_put_official_remove(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "rust_put_off_rm")

        rust_client.put(key, {"val": 1})
        official_client.remove(key)
        _, meta = rust_client.exists(key)

        assert meta is None

    def test_official_put_rust_remove(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "off_put_rust_rm")

        official_client.put(key, {"val": 1})
        rust_client.remove(key)
        _, meta = official_client.exists(key)

        assert meta is None


class TestCrossModify:
    """Test cross-client modification operations."""

    def test_cross_increment(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "cross_incr")
        cleanup.append(key)

        rust_client.put(key, {"counter": 0})
        official_client.increment(key, "counter", 5)
        _, _, bins = rust_client.get(key)

        assert bins["counter"] == 5

    def test_cross_append(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "cross_append")
        cleanup.append(key)

        official_client.put(key, {"msg": "Hello"})
        rust_client.append(key, "msg", " World")
        _, _, bins = official_client.get(key)

        assert bins["msg"] == "Hello World"

    def test_cross_touch(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "cross_touch")
        cleanup.append(key)

        rust_client.put(key, {"val": 1}, meta={"ttl": 100})
        official_client.touch(key, 500)
        _, meta, _ = rust_client.get(key)

        assert meta.ttl > 100

    def test_cross_select(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "cross_select")
        cleanup.append(key)

        official_client.put(key, {"a": 1, "b": 2, "c": 3})
        _, _, bins = rust_client.select(key, ["a", "c"])

        assert bins == {"a": 1, "c": 3}

    def test_cross_operate(self, rust_client, official_client, cleanup):
        """Rust puts data, official client operates (using official constants)."""
        key = ("test", "compat", "cross_operate")
        cleanup.append(key)

        rust_client.put(key, {"counter": 10, "name": "test"})

        ops = [
            {"op": aerospike.OPERATOR_INCR, "bin": "counter", "val": 5},
            {"op": aerospike.OPERATOR_READ, "bin": "counter", "val": ""},
        ]
        _, _, bins = official_client.operate(key, ops)

        assert bins["counter"] == 15
