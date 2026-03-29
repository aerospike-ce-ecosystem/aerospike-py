"""Unit tests for info operations (no server required)."""

import aerospike_py
from tests import DUMMY_CONFIG


class TestInfoNotConnected:
    def test_info_all_requires_connection(self):
        """info_all() on unconnected client raises ClientError."""
        c = aerospike_py.client(DUMMY_CONFIG)
        try:
            c.info_all("build")
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass

    def test_info_random_node_requires_connection(self):
        """info_random_node() on unconnected client raises ClientError."""
        c = aerospike_py.client(DUMMY_CONFIG)
        try:
            c.info_random_node("build")
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass

    def test_ping_returns_false_when_not_connected(self):
        """ping() on unconnected client returns False (no exception)."""
        c = aerospike_py.client(DUMMY_CONFIG)
        assert c.ping() is False
