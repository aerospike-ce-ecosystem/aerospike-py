"""Integration tests for info operations (requires Aerospike server)."""

import pytest

import aerospike_py


class TestInfoAll:
    def test_info_all_build(self, client):
        """info_all('build') returns build version from all nodes."""
        results = client.info_all("build")
        assert isinstance(results, list)
        assert len(results) >= 1

        for node_name, error_code, response in results:
            assert isinstance(node_name, str)
            assert len(node_name) > 0
            assert error_code == 0
            assert isinstance(response, str)
            assert len(response) > 0  # build version string

    def test_info_all_namespaces(self, client):
        """info_all('namespaces') returns namespace list from all nodes."""
        results = client.info_all("namespaces")
        assert len(results) >= 1

        for node_name, error_code, response in results:
            assert error_code == 0
            assert "test" in response  # default test namespace

    def test_info_all_with_policy(self, client):
        """info_all with timeout policy works."""
        results = client.info_all("build", policy={"timeout": 5000})
        assert len(results) >= 1
        for _, error_code, _ in results:
            assert error_code == 0

    def test_info_all_not_connected(self):
        """info_all on unconnected client raises ClientError."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        with pytest.raises(aerospike_py.ClientError):
            c.info_all("build")


class TestInfoRandomNode:
    def test_info_random_node_build(self, client):
        """info_random_node('build') returns a build version string."""
        result = client.info_random_node("build")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_info_random_node_namespaces(self, client):
        """info_random_node('namespaces') returns namespace list."""
        result = client.info_random_node("namespaces")
        assert "test" in result

    def test_info_random_node_with_policy(self, client):
        """info_random_node with timeout policy works."""
        result = client.info_random_node("build", policy={"timeout": 5000})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_info_random_node_not_connected(self):
        """info_random_node on unconnected client raises ClientError."""
        c = aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})
        with pytest.raises(aerospike_py.ClientError):
            c.info_random_node("build")


class TestAsyncInfoAll:
    @pytest.mark.asyncio
    async def test_async_info_all_build(self, async_client):
        """Async info_all('build') returns build version from all nodes."""
        results = await async_client.info_all("build")
        assert isinstance(results, list)
        assert len(results) >= 1

        for node_name, error_code, response in results:
            assert isinstance(node_name, str)
            assert error_code == 0
            assert len(response) > 0


class TestAsyncInfoRandomNode:
    @pytest.mark.asyncio
    async def test_async_info_random_node_build(self, async_client):
        """Async info_random_node('build') returns a build version string."""
        result = await async_client.info_random_node("build")
        assert isinstance(result, str)
        assert len(result) > 0
