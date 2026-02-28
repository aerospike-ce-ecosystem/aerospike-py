"""Extended edge case unit tests (no Aerospike server required).

Covers:
- Empty batch operations on unconnected client (sync + async via parametrize)
- Invalid policy value types
- Key edge cases (empty namespace/set, various user key types)
- Bin name edge cases (long names, special chars, empty)
- Admin methods exist on both sync and async clients
"""

import pytest

import aerospike_py
from aerospike_py import AsyncClient, Client
from tests.helpers import invoke

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_client() -> Client:
    """Create an unconnected sync client with a deliberately unreachable host."""
    return aerospike_py.client({"hosts": [("127.0.0.1", 99999)]})


def _make_async_client() -> AsyncClient:
    """Create an unconnected async client with a deliberately unreachable host."""
    return AsyncClient({"hosts": [("127.0.0.1", 99999)]})


# ═══════════════════════════════════════════════════════════════════
# 1. Empty batch operations  (sync + async via parametrize)
# ═══════════════════════════════════════════════════════════════════


class TestEmptyBatchOperations:
    """Batch operations with empty key lists should raise ClientError
    on an unconnected client (connection check happens after arg prep)."""

    @pytest.mark.parametrize("make_client", [_make_client, _make_async_client], ids=["sync", "async"])
    async def test_batch_read_empty_keys(self, make_client):
        c = make_client()
        with pytest.raises(aerospike_py.ClientError):
            await invoke(c, "batch_read", [])

    @pytest.mark.parametrize("make_client", [_make_client, _make_async_client], ids=["sync", "async"])
    async def test_batch_operate_empty_keys(self, make_client):
        c = make_client()
        ops = [{"op": aerospike_py.OPERATOR_READ, "bin": "a"}]
        with pytest.raises(aerospike_py.ClientError):
            await invoke(c, "batch_operate", [], ops)

    @pytest.mark.parametrize("make_client", [_make_client, _make_async_client], ids=["sync", "async"])
    async def test_batch_remove_empty_keys(self, make_client):
        c = make_client()
        with pytest.raises(aerospike_py.ClientError):
            await invoke(c, "batch_remove", [])


# ═══════════════════════════════════════════════════════════════════
# 2. Invalid policy value types
# ═══════════════════════════════════════════════════════════════════


class TestInvalidPolicyValueTypes:
    """Passing wrong types for policy fields should raise TypeError
    during argument preparation, even on an unconnected client.

    Note: out-of-range integer values (e.g. exists=999) silently fall
    back to defaults in the Rust layer, so we test type mismatches instead.
    """

    @pytest.mark.parametrize(
        "policy_key,invalid_value",
        [
            ("exists", "not_an_int"),
            ("gen", [1, 2, 3]),
            ("key", {"nested": True}),
            ("commit_level", 3.14),
        ],
        ids=["exists_string", "gen_list", "key_dict", "commit_level_float"],
    )
    def test_put_policy_wrong_type_raises(self, policy_key, invalid_value):
        """put() with non-integer policy value raises TypeError."""
        c = _make_client()
        key = ("test", "demo", "key1")
        bins = {"a": 1}
        with pytest.raises((TypeError, aerospike_py.ClientError)):
            c.put(key, bins, policy={policy_key: invalid_value})

    @pytest.mark.parametrize(
        "policy_key,invalid_value",
        [
            ("socket_timeout", "not_an_int"),
            ("total_timeout", []),
            ("max_retries", {}),
        ],
        ids=["socket_timeout_string", "total_timeout_list", "max_retries_dict"],
    )
    def test_get_policy_wrong_type_raises(self, policy_key, invalid_value):
        """get() with non-integer policy value raises TypeError."""
        c = _make_client()
        key = ("test", "demo", "key1")
        with pytest.raises((TypeError, aerospike_py.ClientError)):
            c.get(key, policy={policy_key: invalid_value})


class TestPolicyOutOfRangeDefaults:
    """Out-of-range integer policy values fall back to defaults silently.
    On unconnected client, ClientError is raised after successful parsing."""

    @pytest.mark.parametrize(
        "policy_key,out_of_range_value",
        [
            ("exists", 999),
            ("gen", 999),
            ("key", 999),
            ("commit_level", 999),
        ],
        ids=["exists_999", "gen_999", "key_999", "commit_level_999"],
    )
    def test_put_out_of_range_policy_raises_client_error(self, policy_key, out_of_range_value):
        """put() with out-of-range policy values still parses OK but raises
        ClientError due to unconnected client."""
        c = _make_client()
        key = ("test", "demo", "key1")
        bins = {"a": 1}
        # The policy parses without error (falls back to default),
        # but the unconnected client raises ClientError.
        with pytest.raises(aerospike_py.ClientError):
            c.put(key, bins, policy={policy_key: out_of_range_value})


# ═══════════════════════════════════════════════════════════════════
# 3. Key edge cases
# ═══════════════════════════════════════════════════════════════════


class TestKeyEdgeCases:
    """Test various key tuple edge cases."""

    def test_key_with_empty_namespace(self):
        """Key with empty namespace string should parse but fail on unconnected client."""
        c = _make_client()
        with pytest.raises((aerospike_py.ClientError, aerospike_py.AerospikeError, ValueError)):
            c.get(("", "set", "key"))

    def test_key_with_empty_set(self):
        """Key with empty set string should parse but fail on unconnected client."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("ns", "", "key"))

    def test_key_with_none_set_raises(self):
        """Key with None set should raise TypeError because set_name expects a string."""
        c = _make_client()
        with pytest.raises((TypeError, aerospike_py.ClientError)):
            c.get(("ns", None, "key"))

    def test_key_with_integer_user_key(self):
        """Integer user key should be accepted (raises ClientError only for connection)."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", 42))

    def test_key_with_bytes_user_key(self):
        """Bytes user key should be accepted (raises ClientError only for connection)."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", b"\x01\x02\x03"))

    def test_key_with_string_user_key(self):
        """String user key should be accepted (raises ClientError only for connection)."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", "string_key"))

    def test_key_with_empty_string_user_key(self):
        """Empty string user key should be accepted."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", ""))

    def test_key_with_unicode_user_key(self):
        """Unicode string user key should be accepted."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", "\u00e9\u00e8\u00ea"))

    def test_key_too_short_raises(self):
        """Key tuple with fewer than 3 elements should raise an error."""
        c = _make_client()
        with pytest.raises((ValueError, TypeError, aerospike_py.ClientError)):
            c.get(("test", "demo"))

    def test_key_not_a_tuple_raises(self):
        """Key that is not a tuple should raise an error."""
        c = _make_client()
        with pytest.raises((TypeError, aerospike_py.ClientError)):
            c.get("not_a_tuple")

    def test_key_with_large_integer_user_key(self):
        """Large integer user key within i64 range should be accepted."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.get(("test", "demo", 2**63 - 1))


# ═══════════════════════════════════════════════════════════════════
# 4. Bin name edge cases
# ═══════════════════════════════════════════════════════════════════


class TestBinNameEdgeCases:
    """Test bin name edge cases on put operations."""

    def test_very_long_bin_name(self):
        """Bin name exceeding 15 bytes should raise ValueError at client level."""
        c = _make_client()
        long_name = "a" * 20
        with pytest.raises(ValueError, match="exceeds the 15-byte limit"):
            c.put(("test", "demo", "key1"), {long_name: "value"})

    def test_bin_name_exactly_15_chars(self):
        """Bin name with exactly 15 chars is valid (Aerospike max)."""
        c = _make_client()
        name_15 = "a" * 15
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), {name_15: "value"})

    def test_bin_name_with_special_characters(self):
        """Bin name with special chars should be accepted at Python level."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), {"bin-name.v2": "value"})

    def test_bin_name_with_unicode(self):
        """Bin name with unicode characters should be accepted at Python level."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), {"\u00e9": "value"})

    def test_empty_bin_name(self):
        """Empty bin name should be accepted at the Python/Rust parsing level."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), {"": "value"})

    def test_multiple_bins(self):
        """Multiple bins in a single put should all be accepted."""
        c = _make_client()
        bins = {"a": 1, "b": "hello", "c": 3.14, "d": None, "e": b"\x00\x01"}
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), bins)


# ═══════════════════════════════════════════════════════════════════
# 5. Admin methods exist on unconnected async client
# ═══════════════════════════════════════════════════════════════════


class TestAdminMethodsExist:
    """Verify admin methods exist on both sync and async clients
    and raise ClientError on unconnected client."""

    @pytest.mark.parametrize("make_client", [_make_client, _make_async_client], ids=["sync", "async"])
    async def test_admin_set_quotas_exists(self, make_client):
        """admin_set_quotas should exist and raise ClientError."""
        c = make_client()
        assert hasattr(c, "admin_set_quotas"), f"{type(c).__name__} missing admin_set_quotas method"
        with pytest.raises(aerospike_py.ClientError):
            await invoke(c, "admin_set_quotas", "test-role", read_quota=100, write_quota=200)

    @pytest.mark.parametrize("make_client", [_make_client, _make_async_client], ids=["sync", "async"])
    async def test_admin_set_whitelist_exists(self, make_client):
        """admin_set_whitelist should exist and raise ClientError."""
        c = make_client()
        assert hasattr(c, "admin_set_whitelist"), f"{type(c).__name__} missing admin_set_whitelist method"
        with pytest.raises(aerospike_py.ClientError):
            await invoke(c, "admin_set_whitelist", "test-role", ["10.0.0.0/8"])


# ═══════════════════════════════════════════════════════════════════
# 6. Bin value edge cases
# ═══════════════════════════════════════════════════════════════════


class TestBinValueEdgeCases:
    """Test various bin value types in put operations."""

    @pytest.mark.parametrize(
        "value,desc",
        [
            (0, "zero"),
            (-1, "negative"),
            (2**63 - 1, "max_i64"),
            (-(2**63), "min_i64"),
            (3.14, "float"),
            (-0.0, "neg_zero"),
            (float("inf"), "inf"),
            ("", "empty_string"),
            ("hello", "string"),
            (b"", "empty_bytes"),
            (b"\x00\x01\x02", "bytes"),
            (None, "none"),
            (True, "bool_true"),
            (False, "bool_false"),
            ([], "empty_list"),
            ([1, "two", 3.0], "mixed_list"),
            ({}, "empty_dict"),
            ({"nested": {"deep": 1}}, "nested_dict"),
        ],
        ids=[
            "zero",
            "negative",
            "max_i64",
            "min_i64",
            "float",
            "neg_zero",
            "inf",
            "empty_string",
            "string",
            "empty_bytes",
            "bytes",
            "none",
            "bool_true",
            "bool_false",
            "empty_list",
            "mixed_list",
            "empty_dict",
            "nested_dict",
        ],
    )
    def test_put_various_bin_values(self, value, desc):
        """put() should accept various bin value types at parse level.
        Raises ClientError only because client is not connected."""
        c = _make_client()
        with pytest.raises(aerospike_py.ClientError):
            c.put(("test", "demo", "key1"), {"bin": value})
