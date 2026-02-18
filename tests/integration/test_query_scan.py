"""Integration tests for query operations (requires Aerospike server)."""

import pytest

import aerospike_py
from aerospike_py import predicates as p
from tests.helpers import wait_for_index


@pytest.fixture(scope="module")
def seed_data(client):
    """Seed test data and create index for queries."""
    keys = []
    for i in range(10):
        key = ("test", "query_test", f"qkey_{i}")
        client.put(key, {"name": f"user_{i}", "age": 20 + i, "group": "A" if i < 5 else "B"})
        keys.append(key)

    # Create secondary index on 'age'
    try:
        client.index_integer_create("test", "query_test", "age", "idx_query_age")
    except aerospike_py.ServerError:
        pass  # Index may already exist

    wait_for_index(client, "test", "query_test", "age")
    yield keys

    # Cleanup
    for key in keys:
        try:
            client.remove(key)
        except Exception:
            pass
    try:
        client.index_remove("test", "idx_query_age")
    except Exception:
        pass


class TestQuery:
    def test_query_equals(self, client, seed_data):
        q = client.query("test", "query_test")
        q.where(p.equals("age", 25))
        results = q.results()
        assert len(results) >= 1
        for _, _, bins in results:
            assert bins["age"] == 25

    def test_query_between(self, client, seed_data):
        q = client.query("test", "query_test")
        q.where(p.between("age", 22, 26))
        results = q.results()
        assert len(results) >= 4  # ages 22, 23, 24, 25, 26
        for _, _, bins in results:
            assert 22 <= bins["age"] <= 26

    def test_query_select(self, client, seed_data):
        q = client.query("test", "query_test")
        q.select("age")
        q.where(p.equals("age", 23))
        results = q.results()
        assert len(results) >= 1
        for _, _, bins in results:
            assert "age" in bins

    def test_query_foreach(self, client, seed_data):
        q = client.query("test", "query_test")
        q.where(p.between("age", 20, 29))
        collected = []

        def callback(record):
            collected.append(record)

        q.foreach(callback)
        assert len(collected) >= 10


class TestIndex:
    def test_index_string_create_remove(self, client, seed_data):
        try:
            client.index_string_create("test", "query_test", "name", "idx_query_name")
            wait_for_index(client, "test", "query_test", "name")
        except aerospike_py.ServerError:
            pass  # May already exist

        # Cleanup
        client.index_remove("test", "idx_query_name")
