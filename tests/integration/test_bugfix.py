"""Integration tests for bug fixes (requires Aerospike server).

Covers:
- #115/#116: get/select/operate should return key tuple, not None
- #118: put(key, None) raises TypeError; put(key, {"b": None}) deletes bin
- remove() on non-existent key raises RecordNotFound
"""

import pytest

import aerospike_py


class TestKeyTupleReturned:
    """#115/#116: CRUD 결과에서 key tuple이 None이 아닌 (ns, set, pk, digest)로 반환되어야 한다."""

    def test_get_returns_key_tuple(self, client, cleanup):
        key = ("test", "demo", "bugfix_get_key")
        cleanup.append(key)
        client.put(key, {"val": 1})

        key_tuple, meta, bins = client.get(key)

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"
        assert digest is not None
        assert isinstance(digest, bytes)

    def test_select_returns_key_tuple(self, client, cleanup):
        key = ("test", "demo", "bugfix_select_key")
        cleanup.append(key)
        client.put(key, {"a": 1, "b": 2})

        key_tuple, meta, bins = client.select(key, ["a"])

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"

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
        """POLICY_KEY_SEND로 put한 레코드의 get 결과에 pk가 포함되어야 한다."""
        key = ("test", "demo", "bugfix_key_send")
        cleanup.append(key)
        client.put(key, {"val": 1}, policy={"key": aerospike_py.POLICY_KEY_SEND})

        key_tuple, meta, bins = client.get(key, policy={"key": aerospike_py.POLICY_KEY_SEND})

        assert key_tuple is not None
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"
        assert pk == "bugfix_key_send"


class TestRemoveRecordNotFound:
    """remove()로 존재하지 않는 레코드를 삭제하면 RecordNotFound가 발생해야 한다."""

    def test_remove_nonexistent_raises_record_not_found(self, client):
        key = ("test", "demo", "bugfix_remove_nonexistent")
        with pytest.raises(aerospike_py.RecordNotFound):
            client.remove(key)

    def test_remove_twice_raises_record_not_found(self, client):
        """put → remove → remove 시 두 번째 remove에서 RecordNotFound."""
        key = ("test", "demo", "bugfix_remove_twice")
        client.put(key, {"val": 1})
        client.remove(key)

        with pytest.raises(aerospike_py.RecordNotFound):
            client.remove(key)

    def test_remove_not_found_is_record_error(self, client):
        """RecordNotFound는 RecordError의 서브클래스여야 한다."""
        key = ("test", "demo", "bugfix_remove_hierarchy")
        with pytest.raises(aerospike_py.RecordError):
            client.remove(key)


class TestPutNoneBinDeletion:
    """put(key, {"bin": None})으로 특정 bin을 삭제할 수 있어야 한다."""

    def test_put_none_deletes_bin(self, client, cleanup):
        """bin 값을 None으로 put하면 해당 bin이 삭제된다."""
        key = ("test", "demo", "bugfix_none_bin")
        cleanup.append(key)

        client.put(key, {"a": 1, "b": 2, "c": 3})
        _, _, bins = client.get(key)
        assert "b" in bins

        # b를 None으로 설정하면 bin 삭제
        client.put(key, {"b": None})
        _, _, bins = client.get(key)
        assert "b" not in bins
        assert bins["a"] == 1
        assert bins["c"] == 3

    def test_put_none_all_bins_removes_record(self, client):
        """모든 bin을 None으로 설정하면 레코드 자체가 삭제된다."""
        key = ("test", "demo", "bugfix_none_all_bins")

        client.put(key, {"only": 1})
        client.put(key, {"only": None})

        _, meta = client.exists(key)
        assert meta is None

    def test_put_none_bins_raises_type_error(self, client):
        """put(key, None) — dict가 아닌 None을 전달하면 TypeError."""
        key = ("test", "demo", "bugfix_put_none")
        with pytest.raises(TypeError):
            client.put(key, None)


class TestAsyncKeyTupleReturned:
    """Async 버전: CRUD 결과에서 key tuple이 정상 반환되어야 한다."""

    async def test_async_get_returns_key_tuple(self, async_client, async_cleanup):
        key = ("test", "demo", "bugfix_async_get_key")
        async_cleanup.append(key)
        await async_client.put(key, {"val": 1})

        key_tuple, meta, bins = await async_client.get(key)

        assert key_tuple is not None
        assert isinstance(key_tuple, tuple)
        assert len(key_tuple) == 4
        ns, set_name, pk, digest = key_tuple
        assert ns == "test"
        assert set_name == "demo"
        assert isinstance(digest, bytes)

    async def test_async_select_returns_key_tuple(self, async_client, async_cleanup):
        key = ("test", "demo", "bugfix_async_select_key")
        async_cleanup.append(key)
        await async_client.put(key, {"a": 1, "b": 2})

        key_tuple, meta, bins = await async_client.select(key, ["a"])

        assert key_tuple is not None
        assert len(key_tuple) == 4


class TestAsyncRemoveRecordNotFound:
    """Async 버전: remove()에서 RecordNotFound 발생 테스트."""

    async def test_async_remove_nonexistent(self, async_client):
        key = ("test", "demo", "bugfix_async_remove_nonexistent")
        with pytest.raises(aerospike_py.RecordNotFound):
            await async_client.remove(key)

    async def test_async_remove_twice(self, async_client):
        key = ("test", "demo", "bugfix_async_remove_twice")
        await async_client.put(key, {"val": 1})
        await async_client.remove(key)

        with pytest.raises(aerospike_py.RecordNotFound):
            await async_client.remove(key)


class TestAsyncPutNoneBinDeletion:
    """Async 버전: put(key, {"bin": None})으로 bin 삭제 테스트."""

    async def test_async_put_none_deletes_bin(self, async_client, async_cleanup):
        key = ("test", "demo", "bugfix_async_none_bin")
        async_cleanup.append(key)

        await async_client.put(key, {"a": 1, "b": 2})
        _, _, bins = await async_client.get(key)
        assert "b" in bins

        await async_client.put(key, {"b": None})
        _, _, bins = await async_client.get(key)
        assert "b" not in bins
        assert bins["a"] == 1

    async def test_async_put_none_bins_raises_type_error(self, async_client):
        key = ("test", "demo", "bugfix_async_put_none")
        with pytest.raises(TypeError):
            await async_client.put(key, None)
