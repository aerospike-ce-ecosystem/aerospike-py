"""Policy combination and TTL edge case compatibility tests.

Tests write policies (REPLACE, REPLACE_ONLY, UPDATE_ONLY, CREATE_ONLY),
TTL special values (NEVER_EXPIRE, DONT_UPDATE), and POLICY_KEY_SEND behavior.

Key concern: TTL 0xFFFFFFFF handling in record.rs:38 - verify it matches
the official client for never-expiring records.
"""

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

NS = "test"
SET = "compat_pol"


# ── Write Policy: REPLACE ──────────────────────────────────────────


class TestPolicyReplace:
    """REPLACE policy should replace ALL bins, not merge."""

    def test_rust_replace_removes_old_bins(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_replace_r")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": 2, "c": 3})
        rust_client.put(
            key,
            {"x": 10},
            policy={"exists": aerospike_py.POLICY_EXISTS_REPLACE},
        )

        _, _, bins = official_client.get(key)
        assert "a" not in bins
        assert "b" not in bins
        assert "c" not in bins
        assert bins["x"] == 10

    def test_official_replace_removes_old_bins(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_replace_o")
        cleanup.append(key)

        official_client.put(key, {"a": 1, "b": 2, "c": 3})
        official_client.put(
            key,
            {"x": 10},
            policy={"exists": aerospike.POLICY_EXISTS_REPLACE},
        )

        _, _, bins = rust_client.get(key)
        assert "a" not in bins
        assert bins["x"] == 10

    def test_replace_cross_client(self, rust_client, official_client, cleanup):
        """Rust writes initial, official replaces, rust verifies."""
        key = (NS, SET, "pol_replace_cross")
        cleanup.append(key)

        rust_client.put(key, {"old1": 1, "old2": 2})
        official_client.put(
            key,
            {"new1": 100},
            policy={"exists": aerospike.POLICY_EXISTS_REPLACE},
        )

        _, _, bins = rust_client.get(key)
        assert "old1" not in bins
        assert "old2" not in bins
        assert bins["new1"] == 100


# ── Write Policy: REPLACE_ONLY ─────────────────────────────────────


class TestPolicyReplaceOnly:
    """REPLACE_ONLY should fail on non-existent records."""

    def test_rust_replace_only_nonexistent(self, rust_client, cleanup):
        key = (NS, SET, "pol_reponly_ne")

        with pytest.raises(aerospike_py.RecordNotFound):
            rust_client.put(
                key,
                {"val": 1},
                policy={"exists": aerospike_py.POLICY_EXISTS_REPLACE_ONLY},
            )

    def test_replace_only_existing_works(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_reponly_ex")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": 2})
        rust_client.put(
            key,
            {"c": 3},
            policy={"exists": aerospike_py.POLICY_EXISTS_REPLACE_ONLY},
        )

        _, _, bins = official_client.get(key)
        assert "a" not in bins
        assert bins["c"] == 3


# ── Write Policy: UPDATE_ONLY ──────────────────────────────────────


class TestPolicyUpdateOnly:
    """UPDATE_ONLY should fail on non-existent records."""

    def test_rust_update_only_nonexistent(self, rust_client, cleanup):
        key = (NS, SET, "pol_updonly_ne")

        with pytest.raises(aerospike_py.RecordNotFound):
            rust_client.put(
                key,
                {"val": 1},
                policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY},
            )

    def test_update_only_merges_bins(self, rust_client, official_client, cleanup):
        """UPDATE_ONLY should merge bins (unlike REPLACE)."""
        key = (NS, SET, "pol_updonly_merge")
        cleanup.append(key)

        rust_client.put(key, {"a": 1, "b": 2})
        rust_client.put(
            key,
            {"c": 3},
            policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY},
        )

        _, _, bins = official_client.get(key)
        assert bins["a"] == 1
        assert bins["b"] == 2
        assert bins["c"] == 3


# ── TTL Special Values ─────────────────────────────────────────────


class TestTTLSpecialValues:
    """Test TTL special constants: NEVER_EXPIRE, DONT_UPDATE."""

    def test_ttl_never_expire_rust(self, rust_client, official_client, cleanup):
        key = (NS, SET, "ttl_never_r")
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            meta={"ttl": aerospike_py.TTL_NEVER_EXPIRE},
        )

        _, r_meta, _ = rust_client.get(key)
        _, o_meta, _ = official_client.get(key)

        # Both should report the same TTL for never-expire
        assert r_meta.ttl == o_meta["ttl"]

    def test_ttl_never_expire_official(self, rust_client, official_client, cleanup):
        key = (NS, SET, "ttl_never_o")
        cleanup.append(key)

        official_client.put(
            key,
            {"val": 1},
            meta={"ttl": aerospike.TTL_NEVER_EXPIRE},
        )

        _, r_meta, _ = rust_client.get(key)
        _, o_meta, _ = official_client.get(key)

        assert r_meta.ttl == o_meta["ttl"]

    def test_ttl_dont_update(self, rust_client, official_client, cleanup):
        """TTL_DONT_UPDATE should preserve the original TTL.

        Both clients should read the same TTL after a DONT_UPDATE write.
        """
        key = (NS, SET, "ttl_dont_upd")
        cleanup.append(key)

        rust_client.put(key, {"val": 1}, meta={"ttl": 3600})

        # Update with DONT_UPDATE TTL
        rust_client.put(
            key,
            {"val": 2},
            meta={"ttl": aerospike_py.TTL_DONT_UPDATE},
        )

        _, r_meta, _ = rust_client.get(key)
        _, o_meta, _ = official_client.get(key)

        # Both clients should read approximately the same TTL (within 2 sec)
        assert abs(r_meta.ttl - o_meta["ttl"]) <= 2, f"TTL mismatch: rust={r_meta.ttl}, official={o_meta['ttl']}"
        # Value should be updated
        _, _, bins = rust_client.get(key)
        assert bins["val"] == 2


# ── TTL 0xFFFFFFFF ─────────────────────────────────────────────────


class TestTTLNoExpiration:
    """Verify 0xFFFFFFFF TTL handling for never-expiring records.

    Bug hypothesis: record.rs:38 sets TTL to 0xFFFFFFFF when
    time_to_live() returns None. Verify this matches the official client.
    """

    def test_ttl_value_matches_for_never_expire(self, rust_client, official_client, cleanup):
        key = (NS, SET, "ttl_ff")
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            meta={"ttl": aerospike_py.TTL_NEVER_EXPIRE},
        )

        _, r_meta, _ = rust_client.get(key)
        _, o_meta, _ = official_client.get(key)

        # The actual TTL values should match between clients
        assert r_meta.ttl == o_meta["ttl"], (
            f"TTL mismatch for never-expire: rust={r_meta.ttl}, "
            f"official={o_meta['ttl']}. "
            "Check record.rs:38 0xFFFFFFFF handling."
        )

    def test_ttl_with_explicit_high_value(self, rust_client, official_client, cleanup):
        """Write with high TTL and compare both clients' readings."""
        key = (NS, SET, "ttl_high")
        cleanup.append(key)

        # Write with a normal high TTL
        rust_client.put(key, {"val": 1}, meta={"ttl": 86400})

        _, r_meta, _ = rust_client.get(key)
        _, o_meta, _ = official_client.get(key)

        # TTL values should be approximately equal (within 2 seconds)
        assert abs(r_meta.ttl - o_meta["ttl"]) <= 2


# ── POLICY_KEY_SEND ────────────────────────────────────────────────


class TestPolicySendKey:
    """POLICY_KEY_SEND stores the key with the record."""

    def test_send_key_rust_write_official_read(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_sendkey_r")
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )

        r_key, _, _ = rust_client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})
        o_key, _, _ = official_client.get(key, policy={"key": aerospike.POLICY_KEY_SEND})

        # Both should return the stored primary key
        assert r_key[2] == "pol_sendkey_r"
        assert o_key[2] == "pol_sendkey_r"

    def test_send_key_official_write_rust_read(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_sendkey_o")
        cleanup.append(key)

        official_client.put(
            key,
            {"val": 1},
            policy={"key": aerospike.POLICY_KEY_SEND},
        )

        r_key, _, _ = rust_client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})
        assert r_key[2] == "pol_sendkey_o"

    def test_send_key_integer(self, rust_client, official_client, cleanup):
        """Integer primary key with POLICY_KEY_SEND."""
        key = (NS, SET, 12345)
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )

        r_key, _, _ = rust_client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})
        o_key, _, _ = official_client.get(key, policy={"key": aerospike.POLICY_KEY_SEND})

        assert r_key[2] == o_key[2] == 12345


# ── CREATE_ONLY Policy ─────────────────────────────────────────────


class TestPolicyCreateOnly:
    """CREATE_ONLY should fail when record already exists."""

    def test_create_only_new_record(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_create_new")
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
        )

        _, _, bins = official_client.get(key)
        assert bins["val"] == 1

    def test_create_only_existing_fails(self, rust_client, cleanup):
        key = (NS, SET, "pol_create_dup")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordExistsError):
            rust_client.put(
                key,
                {"val": 2},
                policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )


# ── Generation Policy ──────────────────────────────────────────────


class TestGenerationPolicy:
    """Generation-based conditional writes."""

    def test_gen_eq_success(self, rust_client, official_client, cleanup):
        key = (NS, SET, "pol_gen_eq")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})
        _, meta, _ = rust_client.get(key)

        # Write with matching generation
        rust_client.put(
            key,
            {"val": 2},
            meta={"gen": meta.gen},
            policy={"gen": aerospike_py.POLICY_GEN_EQ},
        )

        _, _, bins = official_client.get(key)
        assert bins["val"] == 2

    def test_gen_eq_mismatch_fails(self, rust_client, cleanup):
        key = (NS, SET, "pol_gen_eq_fail")
        cleanup.append(key)

        rust_client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordGenerationError):
            rust_client.put(
                key,
                {"val": 2},
                meta={"gen": 999},
                policy={"gen": aerospike_py.POLICY_GEN_EQ},
            )
