"""Verify that both clients raise equivalent errors in the same situations."""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")


class TestRecordNotFound:
    def test_get_nonexistent_rust(self, rust_client):
        key = ("test", "compat", "err_notfound_rust_xyz")
        with pytest.raises(aerospike_py.RecordNotFound):
            rust_client.get(key)

    def test_get_nonexistent_official(self, official_client):
        key = ("test", "compat", "err_notfound_off_xyz")
        with pytest.raises(aerospike.exception.RecordNotFound):
            official_client.get(key)


class TestCreateOnlyDuplicate:
    def test_create_only_duplicate_rust(self, rust_client, cleanup):
        key = ("test", "compat", "err_dup_rust")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})
        with pytest.raises(aerospike_py.RecordExistsError):
            rust_client.put(
                key,
                {"val": 2},
                policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )

    def test_create_only_duplicate_official(
        self, rust_client, official_client, cleanup
    ):
        key = ("test", "compat", "err_dup_off")
        cleanup.append(key)

        official_client.put(key, {"val": 1})
        with pytest.raises(aerospike.exception.RecordExistsError):
            official_client.put(
                key,
                {"val": 2},
                policy={"exists": aerospike.POLICY_EXISTS_CREATE},
            )


class TestGenerationMismatch:
    def test_gen_eq_mismatch_rust(self, rust_client, cleanup):
        key = ("test", "compat", "err_gen_rust")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})
        with pytest.raises(aerospike_py.RecordGenerationError):
            rust_client.put(
                key,
                {"val": 2},
                meta={"gen": 999},
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )

    def test_gen_eq_mismatch_official(self, rust_client, official_client, cleanup):
        key = ("test", "compat", "err_gen_off")
        cleanup.append(key)

        official_client.put(key, {"val": 1})
        with pytest.raises(aerospike.exception.RecordGenerationError):
            official_client.put(
                key,
                {"val": 2},
                meta={"gen": 999},
                policy={"gen": aerospike.POLICY_GEN_EQ},
            )


class TestInvalidNamespace:
    def test_invalid_namespace_rust(self, rust_client):
        key = ("nonexistent_namespace_xyz", "demo", "key1")
        with pytest.raises(aerospike_py.AerospikeError):
            rust_client.put(key, {"val": 1})

    def test_invalid_namespace_official(self, official_client):
        key = ("nonexistent_namespace_xyz", "demo", "key1")
        with pytest.raises(aerospike.exception.AerospikeError):
            official_client.put(key, {"val": 1})
