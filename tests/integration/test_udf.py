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
