"""Unit tests for info operations (no server required)."""

import aerospike_py


class TestInfoNotConnected:
    def test_info_all_requires_connection(self):
        """info_all() on unconnected client raises ClientError."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        try:
            c.info_all("build")
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass

    def test_info_random_node_requires_connection(self):
        """info_random_node() on unconnected client raises ClientError."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        try:
            c.info_random_node("build")
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass
