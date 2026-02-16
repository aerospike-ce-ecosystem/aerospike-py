"""Edge case data type compatibility tests.

Tests boundary values, special types, and unusual data patterns
that may expose type conversion differences between aerospike-py
(Rust/PyO3) and the official aerospike Python client.
"""

import math

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

NS = "test"
SET = "compat_edge"


# ── Large Integers ─────────────────────────────────────────────────


class TestLargeIntegers:
    """Test integer boundary values: 2^63-1, -(2^63)."""

    def test_max_int64(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_max_int")
        cleanup.append(key)
        val = (2**63) - 1  # 9223372036854775807

        rust_client.put(key, {"big": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["big"] == val
        assert o_bins["big"] == val

    def test_min_int64(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_min_int")
        cleanup.append(key)
        val = -(2**63)  # -9223372036854775808

        rust_client.put(key, {"small": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["small"] == val
        assert o_bins["small"] == val

    def test_zero(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_zero")
        cleanup.append(key)

        rust_client.put(key, {"zero": 0})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["zero"] == 0
        assert o_bins["zero"] == 0

    def test_negative_one(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_neg1")
        cleanup.append(key)

        rust_client.put(key, {"neg": -1})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["neg"] == -1
        assert o_bins["neg"] == -1

    def test_cross_client_large_int(self, rust_client, official_client, cleanup):
        """Official writes large int, rust reads it."""
        key = (NS, SET, "edge_cross_int")
        cleanup.append(key)
        val = (2**63) - 1

        official_client.put(key, {"big": val})
        _, _, r_bins = rust_client.get(key)
        assert r_bins["big"] == val


# ── Special Floats ─────────────────────────────────────────────────


class TestSpecialFloats:
    """Test float edge cases: inf, -inf, nan, very small values."""

    def test_positive_infinity(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_pinf")
        cleanup.append(key)

        rust_client.put(key, {"val": float("inf")})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert math.isinf(r_bins["val"]) and r_bins["val"] > 0
        assert math.isinf(o_bins["val"]) and o_bins["val"] > 0

    def test_negative_infinity(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_ninf")
        cleanup.append(key)

        rust_client.put(key, {"val": float("-inf")})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert math.isinf(r_bins["val"]) and r_bins["val"] < 0
        assert math.isinf(o_bins["val"]) and o_bins["val"] < 0

    def test_nan(self, rust_client, official_client, cleanup):
        """NaN should round-trip correctly (NaN != NaN)."""
        key = (NS, SET, "edge_nan")
        cleanup.append(key)

        rust_client.put(key, {"val": float("nan")})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert math.isnan(r_bins["val"])
        assert math.isnan(o_bins["val"])

    def test_very_small_float(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_small_f")
        cleanup.append(key)

        val = 1e-308
        rust_client.put(key, {"val": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == val
        assert o_bins["val"] == val

    def test_float_zero(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_f_zero")
        cleanup.append(key)

        rust_client.put(key, {"val": 0.0})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == 0.0
        assert o_bins["val"] == 0.0


# ── Long Bin Names ─────────────────────────────────────────────────


class TestLongBinNames:
    """Aerospike bin names have a 15-character limit (prior to 7.0)."""

    def test_max_length_bin_name(self, rust_client, official_client, cleanup):
        """15-character bin name should work."""
        key = (NS, SET, "edge_longbin")
        cleanup.append(key)

        bin_name = "a" * 15
        rust_client.put(key, {bin_name: "value"})

        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins[bin_name] == "value"
        assert o_bins[bin_name] == "value"

    def test_single_char_bin_name(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_shortbin")
        cleanup.append(key)

        rust_client.put(key, {"x": 42})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["x"] == 42
        assert o_bins["x"] == 42


# ── Bytes Key and Digest ──────────────────────────────────────────


class TestBytesKeyDigest:
    """Test bytes-type primary keys.

    Note: aerospike-py uses BLOB particle type (4) for bytes keys, while the
    official Python client uses STRING particle type (3). This produces
    different digests, so cross-client bytes-key lookups are not compatible.
    Each client can read back its own bytes-key records correctly.
    """

    def test_bytes_key_rust_roundtrip(self, rust_client, cleanup):
        """Rust client can write and read back a bytes key."""
        key = (NS, SET, b"\x01\x02\x03\x04")
        cleanup.append(key)

        rust_client.put(key, {"val": "from_rust"})
        _, _, r_bins = rust_client.get(key)
        assert r_bins["val"] == "from_rust"

    def test_bytes_key_official_roundtrip(self, official_client, cleanup):
        """Official client can write and read back a bytes key."""
        key = (NS, SET, b"\xff\xfe\xfd")

        official_client.put(key, {"val": "from_official"})
        _, _, o_bins = official_client.get(key)
        assert o_bins["val"] == "from_official"

        # Cleanup via official client since digest differs
        official_client.remove(key)

    def test_bytes_key_digest_differs_from_official(self, rust_client, official_client, cleanup):
        """Document: bytes key digests differ because of particle type.

        aerospike-py: BLOB type (4), official: STRING type (3).
        """
        key = (NS, SET, b"\xaa\xbb\xcc")
        cleanup.append(key)

        rust_client.put(
            key,
            {"val": 1},
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )
        r_key, _, _ = rust_client.get(
            key,
            policy={"key": aerospike_py.POLICY_KEY_SEND},
        )

        official_client.put(
            key,
            {"val": 2},
            policy={"key": aerospike.POLICY_KEY_SEND},
        )
        o_key, _, _ = official_client.get(
            key,
            policy={"key": aerospike.POLICY_KEY_SEND},
        )

        # Digests should differ (BLOB=4 vs STRING=3 particle type in RIPEMD-160)
        r_digest = r_key[3]
        o_digest = o_key[3]
        assert r_digest != o_digest, "Unexpected digest match. aerospike-py uses BLOB(4), official uses STRING(3)."

        # Cleanup official's record separately
        official_client.remove(key)


# ── None/Null in Collections ──────────────────────────────────────


class TestNullInCollections:
    """Test None values within lists and maps."""

    def test_none_in_list(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_none_list")
        cleanup.append(key)

        rust_client.put(key, {"items": [1, None, 3, None, 5]})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["items"] == o_bins["items"]
        assert r_bins["items"] == [1, None, 3, None, 5]

    def test_none_in_map(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_none_map")
        cleanup.append(key)

        data = {"a": 1, "b": None, "c": 3}
        rust_client.put(key, {"mymap": data})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["mymap"] == o_bins["mymap"]
        assert r_bins["mymap"]["b"] is None

    def test_none_value_list_cross(self, rust_client, official_client, cleanup):
        """Official writes list with None, rust reads."""
        key = (NS, SET, "edge_none_lx")
        cleanup.append(key)

        official_client.put(key, {"items": [None, "hello", None]})
        _, _, r_bins = rust_client.get(key)
        assert r_bins["items"] == [None, "hello", None]


# ── Nested Data ────────────────────────────────────────────────────


class TestNestedDataLimits:
    """Test deeply nested and complex data structures."""

    def test_nested_list_in_map(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_nest_lm")
        cleanup.append(key)

        data = {"matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}
        rust_client.put(key, data)
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["matrix"] == o_bins["matrix"]
        assert r_bins["matrix"] == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

    def test_nested_map_in_map(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_nest_mm")
        cleanup.append(key)

        data = {
            "config": {
                "level1": {
                    "level2": {
                        "value": 42,
                        "tags": ["a", "b"],
                    }
                }
            }
        }
        rust_client.put(key, data)
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["config"] == o_bins["config"]
        assert r_bins["config"]["level1"]["level2"]["value"] == 42

    def test_mixed_types_in_list(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_mixed_list")
        cleanup.append(key)

        data = [1, "two", 3.0, True, None, [4, 5], {"k": "v"}]
        rust_client.put(key, {"mix": data})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["mix"] == o_bins["mix"]

    def test_empty_collections(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_empty_col")
        cleanup.append(key)

        rust_client.put(key, {"elist": [], "emap": {}})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins == o_bins

    def test_large_list(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_large_list")
        cleanup.append(key)

        data = list(range(1000))
        rust_client.put(key, {"big": data})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["big"] == o_bins["big"]
        assert len(r_bins["big"]) == 1000


# ── String Edge Cases ──────────────────────────────────────────────


class TestStringEdgeCases:
    """Test special string values."""

    def test_empty_string(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_empty_str")
        cleanup.append(key)

        rust_client.put(key, {"val": ""})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == ""
        assert o_bins["val"] == ""

    def test_unicode_string(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_unicode")
        cleanup.append(key)

        val = "Hello \u4e16\u754c \u2603 \u00e9\u00fc\u00f1"
        rust_client.put(key, {"val": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == val
        assert o_bins["val"] == val

    def test_long_string(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_long_str")
        cleanup.append(key)

        val = "x" * 10000
        rust_client.put(key, {"val": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == val
        assert o_bins["val"] == val

    def test_bytes_value(self, rust_client, official_client, cleanup):
        key = (NS, SET, "edge_bytes_val")
        cleanup.append(key)

        val = b"\x00\x01\x02\xff\xfe\xfd"
        rust_client.put(key, {"val": val})
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins["val"] == val
        assert o_bins["val"] == val

    def test_many_bins(self, rust_client, official_client, cleanup):
        """Write many bins at once."""
        key = (NS, SET, "edge_many_bins")
        cleanup.append(key)

        data = {f"b{i}": i for i in range(50)}
        rust_client.put(key, data)
        _, _, r_bins = rust_client.get(key)
        _, _, o_bins = official_client.get(key)

        assert r_bins == o_bins
        assert len(r_bins) == 50
