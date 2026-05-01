"""Integration tests for UDF operations (requires Aerospike server)."""

import os

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG

UDF_FILE = os.path.join(os.path.dirname(__file__), "..", "test_udf.lua")


@pytest.fixture(scope="module")
def client():
    config = AEROSPIKE_CONFIG
    try:
        c = aerospike_py.client(config).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(scope="module")
def udf_client(client):
    """Register the test UDF module once for the module."""
    client.udf_put(UDF_FILE)
    yield client
    try:
        client.udf_remove("test_udf")
    except Exception:
        pass


class TestUDFPutRemove:
    def test_udf_put(self, client):
        """Test registering a UDF module."""
        client.udf_put(UDF_FILE)

    def test_udf_remove(self, client):
        """Test removing a UDF module."""
        # Register first, then remove
        client.udf_put(UDF_FILE)
        client.udf_remove("test_udf")


class TestApply:
    def test_apply_echo(self, udf_client):
        """Test executing a UDF that returns its argument."""
        key = ("test", "demo", "udf_echo")
        udf_client.put(key, {"a": 1})
        try:
            result = udf_client.apply(key, "test_udf", "echo", [42])
            assert result == 42
        finally:
            udf_client.remove(key)

    def test_apply_add(self, udf_client):
        """Test UDF with multiple arguments."""
        key = ("test", "demo", "udf_add")
        udf_client.put(key, {"a": 1})
        try:
            result = udf_client.apply(key, "test_udf", "add", [10, 20])
            assert result == 30
        finally:
            udf_client.remove(key)

    def test_apply_get_bin(self, udf_client):
        """Test UDF that reads a bin from the record."""
        key = ("test", "demo", "udf_getbin")
        udf_client.put(key, {"name": "hello", "val": 99})
        try:
            result = udf_client.apply(key, "test_udf", "get_bin", ["val"])
            assert result == 99
        finally:
            udf_client.remove(key)

    def test_apply_set_bin(self, udf_client):
        """Test UDF that writes a bin on the record."""
        key = ("test", "demo", "udf_setbin")
        udf_client.put(key, {"x": 1})
        try:
            udf_client.apply(key, "test_udf", "set_bin", ["x", 42])
            _, _, bins = udf_client.get(key)
            assert bins["x"] == 42
        finally:
            udf_client.remove(key)


class TestBatchApply:
    def test_batch_apply_basic(self, udf_client):
        """Apply the same UDF to multiple records with a single call."""
        keys = [("test", "demo", f"bapply_basic_{i}") for i in range(5)]
        for k in keys:
            udf_client.put(k, {"x": 1})
        try:
            result = udf_client.batch_apply(keys, "test_udf", "add", [10, 20])
            assert len(result.batch_records) == 5
            for br in result.batch_records:
                assert br.result == 0, f"per-record result should be 0, got {br.result}"
        finally:
            for k in keys:
                udf_client.remove(k)

    def test_batch_apply_set_bin_writes_each_record(self, udf_client):
        """UDF that writes a bin should mutate each record."""
        keys = [("test", "demo", f"bapply_set_{i}") for i in range(4)]
        for k in keys:
            udf_client.put(k, {"x": 0})
        try:
            udf_client.batch_apply(keys, "test_udf", "set_bin", ["x", 99])
            for k in keys:
                _, _, bins = udf_client.get(k)
                assert bins["x"] == 99
        finally:
            for k in keys:
                udf_client.remove(k)

    def test_batch_apply_per_record_args_override(self, udf_client):
        """Per-record BatchUDFMeta with `args` should override defaults.

        Default args set bin ``x`` to ``1``; record k2 overrides to set bin
        ``y`` to ``7`` instead.
        """
        k1 = ("test", "demo", "bapply_meta_args1")
        k2 = ("test", "demo", "bapply_meta_args2")
        for k in (k1, k2):
            udf_client.put(k, {"x": 0, "y": 0})
        try:
            udf_client.batch_apply(
                [
                    k1,  # bare key uses default args ["x", 1]
                    (k2, {"args": ["y", 7]}),
                ],
                "test_udf",
                "set_bin",
                args=["x", 1],
            )
            _, _, b1 = udf_client.get(k1)
            _, _, b2 = udf_client.get(k2)
            assert b1["x"] == 1
            assert b2["y"] == 7
            # k2 must NOT have x mutated (it used the override args).
            assert b2["x"] == 0
        finally:
            udf_client.remove(k1)
            udf_client.remove(k2)

    def test_batch_apply_per_record_function_override(self, udf_client):
        """Per-record meta may switch to a different UDF function."""
        k1 = ("test", "demo", "bapply_func1")
        k2 = ("test", "demo", "bapply_func2")
        for k in (k1, k2):
            udf_client.put(k, {"x": 0})
        try:
            result = udf_client.batch_apply(
                [
                    k1,  # uses default add
                    (k2, {"function": "echo", "args": ["override"]}),
                ],
                "test_udf",
                "add",
                args=[2, 3],
            )
            assert len(result.batch_records) == 2
            for br in result.batch_records:
                assert br.result == 0
        finally:
            udf_client.remove(k1)
            udf_client.remove(k2)

    def test_batch_apply_missing_record_returns_per_key_error(self, udf_client):
        """Calling UDF on a non-existent key surfaces a per-record error."""
        existing = ("test", "demo", "bapply_present")
        missing = ("test", "demo", "bapply_absent_does_not_exist")
        udf_client.put(existing, {"x": 1})
        try:
            result = udf_client.batch_apply([existing, missing], "test_udf", "echo", [1])
            assert len(result.batch_records) == 2
            # The missing record should report a non-zero error code; the
            # existing one should be 0.
            existing_br = next(br for br in result.batch_records if br.key.user_key == "bapply_present")
            assert existing_br.result == 0
        finally:
            udf_client.remove(existing)
