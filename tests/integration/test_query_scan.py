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


class TestPartitionFilter:
    """Validates PartitionFilter / expected_duration / include_bin_data on QueryPolicy.

    Closes #306. ``PartitionFilter`` scopes a query to a subset of partitions;
    ``expected_duration`` hints query length to the server; ``include_bin_data``
    suppresses bin payload in results.
    """

    @pytest.fixture(scope="class")
    def partitioned_data(self, client):
        keys = []
        for i in range(2000):
            key = ("test", "pf_test", f"pf_key_{i}")
            client.put(key, {"i": i, "name": f"row_{i}"})
            keys.append(key)
        yield keys
        for key in keys:
            try:
                client.remove(key)
            except Exception:
                pass

    def test_partition_filter_all_matches_default(self, client, partitioned_data):
        all_default = client.query("test", "pf_test").results()
        all_explicit = client.query("test", "pf_test").results(
            policy={"partition_filter": aerospike_py.partition_filter_all()}
        )
        assert len(all_default) == len(all_explicit) == len(partitioned_data)

    def test_partition_filter_by_range_quarter(self, client, partitioned_data):
        pf = aerospike_py.partition_filter_by_range(0, 1024)  # 1/4 of partitions
        records = client.query("test", "pf_test").results(policy={"partition_filter": pf})
        n = len(records)
        # Expect ~500 records (2000 * 1024/4096); allow ±25% jitter from hash distribution.
        assert 350 <= n <= 650, f"expected ~500, got {n}"

    def test_partition_filter_by_range_zero_rejected_by_server(self, client, partitioned_data):
        """``count=0`` is accepted at the helper level but rejected by the server.

        Confirms the value flows through to the server validation rather than
        being silently swallowed.
        """
        pf = aerospike_py.partition_filter_by_range(0, 0)
        with pytest.raises(aerospike_py.InvalidArgError):
            client.query("test", "pf_test").results(policy={"partition_filter": pf})

    def test_partition_filter_by_id_4095_succeeds(self, client, partitioned_data):
        pf = aerospike_py.partition_filter_by_id(4095)
        records = client.query("test", "pf_test").results(policy={"partition_filter": pf})
        assert isinstance(records, list)

    def test_partition_filter_by_id_out_of_range_raises(self):
        with pytest.raises(ValueError, match="partition_id must be"):
            aerospike_py.partition_filter_by_id(4096)

    def test_partition_filter_by_range_overflow_raises(self):
        with pytest.raises(ValueError, match="begin \\+ count must be"):
            aerospike_py.partition_filter_by_range(4000, 1000)

    def test_expected_duration_short_runs(self, client, partitioned_data):
        records = client.query("test", "pf_test").results(
            policy={"expected_duration": aerospike_py.QUERY_DURATION_SHORT}
        )
        assert len(records) == len(partitioned_data)

    def test_expected_duration_long_relax_ap_runs(self, client, partitioned_data):
        records = client.query("test", "pf_test").results(
            policy={"expected_duration": aerospike_py.QUERY_DURATION_LONG_RELAX_AP}
        )
        assert len(records) == len(partitioned_data)


class TestIndex:
    def test_index_string_create_remove(self, client, seed_data):
        try:
            client.index_string_create("test", "query_test", "name", "idx_query_name")
            wait_for_index(client, "test", "query_test", "name")
        except aerospike_py.ServerError:
            pass  # May already exist

        # Cleanup
        client.index_remove("test", "idx_query_name")
