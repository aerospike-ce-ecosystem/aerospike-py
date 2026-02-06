"""Cross-client scan and query compatibility tests."""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

NS = "test"
SET_NAME = "compat_sq"


@pytest.fixture(autouse=True)
def seed_data(rust_client, official_client):
    """Seed test data and clean up after."""
    keys = []
    for i in range(10):
        key = (NS, SET_NAME, f"sq_{i}")
        rust_client.put(
            key,
            {"id": i, "category": "even" if i % 2 == 0 else "odd", "value": i * 100},
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )
        keys.append(key)
    yield
    for key in keys:
        try:
            rust_client.remove(key)
        except Exception:
            pass


class TestScan:
    def test_rust_put_official_scan(self, official_client):
        scan = official_client.scan(NS, SET_NAME)
        results = scan.results()
        assert len(results) >= 10

    def test_official_scan_has_bins(self, official_client):
        scan = official_client.scan(NS, SET_NAME)
        scan.select("id", "value")
        results = scan.results()
        for _, _, bins in results:
            assert "id" in bins
            assert "value" in bins

    def test_rust_scan_has_bins(self, rust_client):
        scan = rust_client.scan(NS, SET_NAME)
        scan.select("id", "value")
        results = scan.results()
        for _, _, bins in results:
            assert "id" in bins
            assert "value" in bins

    def test_cross_scan_results_match(self, rust_client, official_client):
        """Both clients should see the same data when scanning."""
        rust_scan = rust_client.scan(NS, SET_NAME)
        rust_scan.select("id", "value")
        rust_results = rust_scan.results()

        off_scan = official_client.scan(NS, SET_NAME)
        off_scan.select("id", "value")
        off_results = off_scan.results()

        # Extract and sort bins by id for comparison
        rust_bins = sorted([bins for _, _, bins in rust_results], key=lambda b: b["id"])
        off_bins = sorted([bins for _, _, bins in off_results], key=lambda b: b["id"])

        assert len(rust_bins) == len(off_bins)
        for rb, ob in zip(rust_bins, off_bins):
            assert rb["id"] == ob["id"]
            assert rb["value"] == ob["value"]


class TestQuery:
    def test_cross_query_with_index(self, rust_client, official_client):
        idx_name = "compat_id_idx"
        try:
            rust_client.index_integer_create(NS, SET_NAME, "id", idx_name)
        except aerospike_py.IndexFoundError:
            pass

        try:
            # Query via official client on data written by rust client
            query = official_client.query(NS, SET_NAME)
            query.where(aerospike.predicates.between("id", 3, 7))
            results = query.results()

            ids = [bins["id"] for _, _, bins in results]
            assert len(ids) >= 5
            for id_val in ids:
                assert 3 <= id_val <= 7
        finally:
            try:
                rust_client.index_remove(NS, idx_name)
            except Exception:
                pass
