"""Cross-client query compatibility tests."""

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
