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

    def test_get_cluster_name_requires_connection(self):
        """get_cluster_name() on unconnected client raises ClientError."""
        c = aerospike_py.client(DUMMY_CONFIG)
        try:
            c.get_cluster_name()
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass

    async def test_async_get_cluster_name_requires_connection(self):
        """AsyncClient.get_cluster_name() on unconnected client raises ClientError."""
        c = aerospike_py.AsyncClient(DUMMY_CONFIG)
        try:
            await c.get_cluster_name()
            assert False, "Should have raised ClientError"
        except aerospike_py.ClientError:
            pass
