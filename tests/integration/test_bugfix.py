"""Integration tests for bug fixes (requires Aerospike server).

Covers:
- #115/#116: get/select/operate should return key tuple, not None
- #118: put(key, None) raises TypeError; put(key, {"b": None}) deletes bin
- remove() on non-existent key raises RecordNotFound

Tests marked with ``any_client`` run twice (sync + async) via the
parametrized fixture.  Tests with sync-only semantics use ``client``.
"""

import pytest

import aerospike_py
from tests.helpers import invoke

# ═══════════════════════════════════════════════════════════════════
# #115/#116  key tuple returned  (sync + async)
# ═══════════════════════════════════════════════════════════════════


class TestKeyTupleReturned:
    """CRUD results should return a key tuple as (ns, set, pk, digest), not None."""

    async def test_get_returns_key_tuple(self, any_client, any_cleanup):
        key = ("test", "demo", "bugfix_get_key")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"val": 1})

        key_tuple, meta, bins = await invoke(any_client, "get", key)

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"
        assert digest is not None
        assert isinstance(digest, bytes)

    async def test_select_returns_key_tuple(self, any_client, any_cleanup):
        key = ("test", "demo", "bugfix_select_key")
        any_cleanup.append(key)
        await invoke(any_client, "put", key, {"a": 1, "b": 2})

        key_tuple, meta, bins = await invoke(any_client, "select", key, ["a"])

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"

    # ── sync-only ──

    def test_exists_returns_key_tuple(self, client, cleanup):
        key = ("test", "demo", "bugfix_exists_key")
        cleanup.append(key)
        client.put(key, {"val": 1})

        key_tuple, meta = client.exists(key)

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"

    def test_operate_returns_key_tuple(self, client, cleanup):
        key = ("test", "demo", "bugfix_operate_key")
        cleanup.append(key)
        client.put(key, {"counter": 10})

        ops = [
            {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
        ]
        key_tuple, meta, bins = client.operate(key, ops)

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"

    def test_get_with_policy_key_send(self, client, cleanup):
        """get result should include pk for a record put with POLICY_KEY_SEND."""
        key = ("test", "demo", "bugfix_key_send")
        cleanup.append(key)
        client.put(key, {"val": 1}, policy={"key": aerospike_py.POLICY_KEY_SEND})

        key_tuple, meta, bins = client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})

        assert key_tuple is not None
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"
        assert pk == "bugfix_key_send"


# ═══════════════════════════════════════════════════════════════════
# remove() RecordNotFound  (sync + async)
# ═══════════════════════════════════════════════════════════════════


class TestRemoveRecordNotFound:
    """remove() on a non-existent record should raise RecordNotFound."""

    async def test_remove_nonexistent_raises_record_not_found(self, any_client):
        key = ("test", "demo", "bugfix_remove_nonexistent")
        with pytest.raises(aerospike_py.RecordNotFound):
            await invoke(any_client, "remove", key)

    async def test_remove_twice_raises_record_not_found(self, any_client, any_cleanup):
        """put -> remove -> remove: the second remove should raise RecordNotFound."""
        key = ("test", "demo", "bugfix_remove_twice")
        await invoke(any_client, "put", key, {"val": 1})
        await invoke(any_client, "remove", key)

        with pytest.raises(aerospike_py.RecordNotFound):
            await invoke(any_client, "remove", key)

    # ── sync-only ──

    def test_remove_not_found_is_record_error(self, client):
        """RecordNotFound should be a subclass of RecordError."""
        key = ("test", "demo", "bugfix_remove_hierarchy")
        with pytest.raises(aerospike_py.RecordError):
            client.remove(key)


# ═══════════════════════════════════════════════════════════════════
# #118  put(key, {"bin": None}) bin deletion  (sync + async)
# ═══════════════════════════════════════════════════════════════════


class TestPutNoneBinDeletion:
    """put(key, {"bin": None}) should be able to delete a specific bin."""

    async def test_put_none_deletes_bin(self, any_client, any_cleanup):
        """Putting a bin value of None deletes that bin."""
        key = ("test", "demo", "bugfix_none_bin")
        any_cleanup.append(key)

        await invoke(any_client, "put", key, {"a": 1, "b": 2, "c": 3})
        _, _, bins = await invoke(any_client, "get", key)
        assert "b" in bins

        await invoke(any_client, "put", key, {"b": None})
        _, _, bins = await invoke(any_client, "get", key)
        assert "b" not in bins
        assert bins["a"] == 1
        assert bins["c"] == 3

    async def test_put_none_bins_raises_type_error(self, any_client):
        """put(key, None) -- passing None instead of a dict raises TypeError."""
        key = ("test", "demo", "bugfix_put_none")
        with pytest.raises(TypeError):
            await invoke(any_client, "put", key, None)

    # ── sync-only ──

    def test_put_none_all_bins_removes_record(self, client):
        """Setting all bins to None deletes the record itself."""
        key = ("test", "demo", "bugfix_none_all_bins")

        client.put(key, {"only": 1})
        client.put(key, {"only": None})

        _, meta = client.exists(key)
        assert meta is None
