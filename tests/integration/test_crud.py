"""Integration tests for CRUD operations (requires Aerospike server)."""

import aerospike_py


class TestPutGet:
    def test_put_and_get(self, client, cleanup):
        key = ("test", "demo", "test_put_get")
        cleanup.append(key)

        client.put(key, {"name": "John", "age": 30})
        _, meta, bins = client.get(key)

        assert bins["name"] == "John"
        assert bins["age"] == 30
        assert meta.gen >= 1

    def test_put_with_policy_key_send(self, client, cleanup):
        key = ("test", "demo", "test_key_send")
        cleanup.append(key)

        client.put(key, {"val": 1}, policy={"key": aerospike_py.POLICY_KEY_SEND})
        key_tuple, meta, bins = client.get(key)

        assert bins["val"] == 1
        assert meta.gen >= 1

    def test_put_with_meta_ttl(self, client, cleanup):
        key = ("test", "demo", "test_ttl")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"ttl": 300})
        _, meta, _ = client.get(key)

        assert meta.ttl > 0
        assert meta.ttl <= 300

    def test_put_various_types(self, client, cleanup):
        key = ("test", "demo", "test_types")
        cleanup.append(key)

        bins = {
            "int_val": 42,
            "str_val": "hello",
            "float_val": 3.14,
            "bytes_val": b"\x00\x01\x02",
            "list_val": [1, "two", 3.0],
            "map_val": {"nested": "dict"},
            "bool_val": True,
            "none_val": None,
        }
        client.put(key, bins)
        _, _, result = client.get(key)

        assert result["int_val"] == 42
        assert result["str_val"] == "hello"
        assert abs(result["float_val"] - 3.14) < 0.001
        assert result["bytes_val"] == b"\x00\x01\x02"
        assert result["list_val"] == [1, "two", 3.0]
        assert result["map_val"] == {"nested": "dict"}
        assert result["bool_val"] is True


class TestSelect:
    def test_select_bins(self, client, cleanup):
        key = ("test", "demo", "test_select")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3})
        _, _, bins = client.select(key, ["a", "c"])

        assert "a" in bins
        assert "c" in bins
        assert bins["a"] == 1
        assert bins["c"] == 3


class TestExists:
    def test_exists_found(self, client, cleanup):
        key = ("test", "demo", "test_exists_found")
        cleanup.append(key)

        client.put(key, {"val": 1})
        key_tuple, meta = client.exists(key)

        assert meta is not None
        assert meta.gen >= 1

    def test_exists_not_found(self, client, cleanup):
        key = ("test", "demo", "test_exists_notfound")
        key_tuple, meta = client.exists(key)
        assert meta is None


class TestRemove:
    def test_remove(self, client, cleanup):
        key = ("test", "demo", "test_remove")

        client.put(key, {"val": 1})
        client.remove(key)

        _, meta = client.exists(key)
        assert meta is None


class TestTouch:
    def test_touch(self, client, cleanup):
        key = ("test", "demo", "test_touch")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"ttl": 100})
        client.touch(key, 300)

        _, meta, _ = client.get(key)
        assert meta.ttl > 100


class TestIncrement:
    def test_increment(self, client, cleanup):
        key = ("test", "demo", "test_incr")
        cleanup.append(key)

        client.put(key, {"counter": 10})
        client.increment(key, "counter", 5)

        _, _, bins = client.get(key)
        assert bins["counter"] == 15


class TestAppendPrepend:
    def test_append(self, client, cleanup):
        key = ("test", "demo", "test_append")
        cleanup.append(key)

        client.put(key, {"name": "Hello"})
        client.append(key, "name", " World")

        _, _, bins = client.get(key)
        assert bins["name"] == "Hello World"

    def test_prepend(self, client, cleanup):
        key = ("test", "demo", "test_prepend")
        cleanup.append(key)

        client.put(key, {"name": "World"})
        client.prepend(key, "name", "Hello ")

        _, _, bins = client.get(key)
        assert bins["name"] == "Hello World"


class TestRemoveBin:
    def test_remove_bin(self, client, cleanup):
        key = ("test", "demo", "test_remove_bin")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3})
        client.remove_bin(key, ["b"])

        _, _, bins = client.get(key)
        assert "a" in bins
        assert "b" not in bins
        assert "c" in bins


class TestOperate:
    def test_operate(self, client, cleanup):
        key = ("test", "demo", "test_operate")
        cleanup.append(key)

        client.put(key, {"counter": 10, "name": "test"})

        ops = [
            {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        _, _, bins = client.operate(key, ops)
        assert bins["counter"] == 15

    def test_operate_ordered(self, client, cleanup):
        key = ("test", "demo", "test_operate_ordered")
        cleanup.append(key)

        client.put(key, {"val": 1})
        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
        ]
        _, meta, ordered = client.operate_ordered(key, ops)
        assert isinstance(ordered, list)
        assert meta.gen >= 1


class TestConnection:
    def test_is_connected(self, client):
        assert client.is_connected()

    def test_get_node_names(self, client):
        nodes = client.get_node_names()
        assert isinstance(nodes, list)
        assert len(nodes) > 0


class TestTruncate:
    def test_truncate(self, client):
        """Test that truncate completes without error.

        Note: truncate is asynchronous on the server side; records
        may not be physically removed immediately.
        """
        keys = [("test", "trunc_test", f"trunc_{i}") for i in range(3)]
        for key in keys:
            client.put(key, {"v": 1})

        # Should not raise
        client.truncate("test", "trunc_test")
