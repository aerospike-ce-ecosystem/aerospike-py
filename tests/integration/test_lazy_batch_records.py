"""Integration tests for `batch_read()` returning a `LazyBatchRecords`.

The async path completes with near-zero GIL hold (Arc::new + Py::new);
materialisation is via ``lazy_records.to_dict()`` /
``lazy_records.to_numpy(dtype)`` in the calling coroutine, so concurrent
``batch_read`` futures release their ``spawn_blocking`` threads almost
immediately.
"""

import asyncio

import pytest

NS = "test"
SET = "lazy_batch_records"


@pytest.fixture(autouse=True)
async def _seed_records(async_client, async_cleanup):
    """Seed 5 records and clean up after each test."""
    keys = [(NS, SET, f"h_{i}") for i in range(5)]
    for i, k in enumerate(keys):
        async_cleanup.append(k)
        await async_client.put(k, {"name": f"user_{i}", "score": i * 10})
    yield keys


class TestLazyBatchRecordsDict:
    """Tests for ``batch_read().to_dict()`` returning dict[UserKey, AerospikeRecord]."""

    async def test_returns_lazy_records(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)
        # batch_read no longer eagerly materialises; .to_dict() does.
        assert not isinstance(lazy_records, dict)
        result = lazy_records.to_dict()
        assert isinstance(result, dict)
        assert len(result) == 5

    async def test_dict_values(self, async_client, _seed_records):
        """Dict maps user_key to bins dict."""
        keys = _seed_records
        result = (await async_client.batch_read(keys)).to_dict()

        for i in range(5):
            key_val = f"h_{i}"
            assert key_val in result
            assert result[key_val]["name"] == f"user_{i}"
            assert result[key_val]["score"] == i * 10

    async def test_specific_bins(self, async_client, _seed_records):
        """bins parameter filters returned bins."""
        keys = _seed_records
        result = (await async_client.batch_read(keys, bins=["name"])).to_dict()

        for i in range(5):
            bins = result[f"h_{i}"]
            assert "name" in bins
            assert "score" not in bins

    async def test_missing_records_excluded(self, async_client, _seed_records):
        """Missing records are excluded from the dict."""
        keys = _seed_records
        missing = [(NS, SET, "missing_1"), (NS, SET, "missing_2")]
        result = (await async_client.batch_read(keys + missing)).to_dict()

        assert len(result) == 5  # Only found records
        assert "missing_1" not in result
        assert "missing_2" not in result

    async def test_empty_keys(self, async_client):
        """Empty keys list yields an empty dict via .to_dict()."""
        result = (await async_client.batch_read([])).to_dict()
        assert result == {}

    async def test_dict_iteration(self, async_client, _seed_records):
        """Standard dict iteration patterns work on .to_dict()."""
        keys = _seed_records
        result = (await async_client.batch_read(keys)).to_dict()

        # items()
        for user_key, bins_dict in result.items():
            assert isinstance(user_key, str)
            assert isinstance(bins_dict, dict)
            assert "name" in bins_dict

        # keys()
        assert set(result.keys()) == {f"h_{i}" for i in range(5)}

    async def test_integer_keys(self, async_client, async_cleanup):
        """Integer user keys work correctly."""
        keys = [(NS, SET, i) for i in range(3)]
        for k in keys:
            async_cleanup.append(k)
            await async_client.put(k, {"val": k[2] * 10})

        result = (await async_client.batch_read(keys)).to_dict()
        assert len(result) == 3
        for i in range(3):
            assert result[i]["val"] == i * 10


class TestBatchReadConcurrency:
    """Test GIL contention elimination with concurrent batch_read."""

    async def test_concurrent_gather(self, async_client, _seed_records):
        """Multiple concurrent batch_read calls via asyncio.gather."""
        keys = _seed_records

        async def read_task():
            lazy_records = await async_client.batch_read(keys)
            result = lazy_records.to_dict()
            assert len(result) == 5
            return result

        results = await asyncio.gather(*(read_task() for _ in range(8)))
        assert len(results) == 8
        for d in results:
            assert isinstance(d, dict)
            assert len(d) == 5


class TestLazyBatchRecordsMapping:
    """Direct tests for the dict-style Mapping protocol on the `LazyBatchRecords`.

    The other dict tests go through ``.to_dict()`` and assert on the
    resulting plain ``dict``. This class exercises the `LazyBatchRecords`'s
    own ``__getitem__`` / ``__contains__`` / ``__iter__`` / ``__len__`` /
    ``keys`` / ``values`` / ``items`` / ``get`` so a regression dropping
    any single dunder from ``#[pymethods]`` is caught.
    """

    async def test_len_is_dict_view_cardinality(self, async_client, _seed_records):
        """``len(lazy_records)`` matches ``len(lazy_records.to_dict())`` —
        missing reads and per-record failures are excluded. The raw record
        count is available via ``len(lazy_records.batch_records)``."""
        keys = _seed_records
        missing = [(NS, SET, "missing_X"), (NS, SET, "missing_Y")]
        lazy_records = await async_client.batch_read(keys + missing)

        # Dict-view cardinality: only the 5 found records
        assert len(lazy_records) == len(keys)
        assert len(lazy_records) == len(lazy_records.to_dict())
        # Raw record count (includes missing reads) lives on `batch_records`
        assert len(lazy_records.batch_records) == len(keys) + len(missing)

    async def test_contains_iter_keys_values_items(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        assert "h_0" in lazy_records
        assert "not_a_key" not in lazy_records
        assert sorted(iter(lazy_records)) == sorted(f"h_{i}" for i in range(5))
        assert set(lazy_records.keys()) == {f"h_{i}" for i in range(5)}
        assert all(isinstance(v, dict) and "name" in v for v in lazy_records.values())
        assert {k: v["name"] for k, v in lazy_records.items()} == {f"h_{i}": f"user_{i}" for i in range(5)}

    async def test_getitem_raises_keyerror_for_missing(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        with pytest.raises(KeyError):
            _ = lazy_records["missing_record"]

    async def test_get_returns_default_for_missing(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        # default=None
        assert lazy_records.get("missing_record") is None
        # explicit default
        sentinel = {"_": "_"}
        assert lazy_records.get("missing_record", sentinel) is sentinel
        # present key
        assert lazy_records.get("h_2")["name"] == "user_2"

    async def test_dict_view_matches_keys_view(self, async_client, _seed_records):
        """``set(lazy_records.keys()) == set(lazy_records.to_dict().keys())`` invariant."""
        keys = _seed_records
        missing = [(NS, SET, "missing_Z")]
        lazy_records = await async_client.batch_read(keys + missing)
        assert set(lazy_records.keys()) == set(lazy_records.to_dict().keys())


class TestLazyBatchRecordsConversionCache:
    """``to_dict()`` returns a fresh shallow copy so mutation cannot poison
    the cached dict view used by the Mapping-protocol dunders."""

    async def test_to_dict_fresh_copy_does_not_poison_cache(self, async_client, _seed_records):
        keys = _seed_records
        lazy_records = await async_client.batch_read(keys)

        d1 = lazy_records.to_dict()
        d1["mutated_after_to_dict"] = {"name": "ghost"}
        # The Mapping-protocol view is independent of the caller's mutation
        assert "mutated_after_to_dict" not in lazy_records
        # A second `to_dict()` is also unaffected
        assert "mutated_after_to_dict" not in lazy_records.to_dict()


class TestLazyBatchRecordsAllRecordsViews:
    """``iter_records`` / ``all_user_keys`` expose every batch record,
    including digest-only and per-record-failed entries that the dict
    view filters out."""

    async def test_iter_records_includes_missing(self, async_client, _seed_records):
        keys = _seed_records
        missing = [(NS, SET, "missing_iter")]
        lazy_records = await async_client.batch_read(keys + missing)

        all_records = list(lazy_records.iter_records())
        # Every batch entry is present, including the missing one
        assert len(all_records) == len(keys) + len(missing)
        # Dict view filters the missing entry out
        assert len(lazy_records.to_dict()) == len(keys)

    async def test_all_user_keys_includes_missing(self, async_client, _seed_records):
        keys = _seed_records
        missing_key = (NS, SET, "missing_raw")
        lazy_records = await async_client.batch_read([*keys, missing_key])

        raw = list(lazy_records.all_user_keys())
        assert "missing_raw" in raw
        # Order matches the request order
        assert raw == [f"h_{i}" for i in range(5)] + ["missing_raw"]

    async def test_all_user_keys_keeps_digest_only_as_none_positional(self, async_client, _seed_records):
        """digest-only requests stay in their slot as ``None`` so
        ``zip(all_user_keys(), batch_records)`` never silently
        off-by-ones a real-world mix of user-keyed and digest-only reads.
        """
        keys = _seed_records
        # Use the seeded h_2 record's digest to construct a digest-only request:
        # 4-element tuple ``(ns, set, None, digest_bytes)``. The server still
        # returns the record body; aerospike-py drops the user_key because the
        # client requested by digest alone.
        first_read = await async_client.batch_read([keys[2]])
        # LazyBatchRecords.batch_records yields the raw PyO3 BatchRecord
        # whose .key is the unwrapped 4-tuple `(ns, set, user_key, digest)`.
        digest = first_read.batch_records[0].key[3]
        assert isinstance(digest, bytes) and len(digest) == 20

        digest_only = (NS, SET, None, digest)
        # Layout: [keys[0], keys[1], DIGEST_ONLY, keys[3], keys[4]]
        # so a positional align bug shows up as the 3rd slot being a string.
        mixed = [keys[0], keys[1], digest_only, keys[3], keys[4]]

        lazy_records = await async_client.batch_read(mixed)
        raw = list(lazy_records.all_user_keys())

        assert len(raw) == len(mixed), "all_user_keys() must preserve every request slot, including digest-only"
        assert raw[0] == "h_0"
        assert raw[1] == "h_1"
        assert raw[2] is None, "digest-only slot must be None, not skipped"
        assert raw[3] == "h_3"
        assert raw[4] == "h_4"

        # Positional alignment with batch_records must hold for downstream
        # ``zip(all_user_keys(), batch_records)`` consumers. The raw
        # PyO3 BatchRecord exposes ``.key`` as a 4-tuple
        # ``(ns, set, user_key, digest)`` — index [2] is the user_key.
        records = list(lazy_records.iter_records())
        assert len(records) == len(raw)
        for slot_key, br in zip(raw, records):
            assert br.key[2] == slot_key

        # Visible divergence between ``keys()`` (Mapping-protocol view,
        # excludes digest-only / failed slots) and ``all_user_keys()``
        # (positional view, includes them as ``None``). Locks in the
        # documented contract that the two methods *intentionally*
        # return different lengths so a future refactor merging them
        # cannot land silently. The assert messages spell out the
        # contract so a regression PR sees the *why* in the failure
        # log, not just the mismatched numbers.
        keys_view = list(lazy_records.keys())
        assert len(keys_view) == 4, (
            "keys() is the Mapping-protocol dict-view (excludes digest-only / "
            "failed slots, matches to_dict().keys()) — if you intentionally "
            "want to include digest-only slots use all_user_keys() instead"
        )
        assert len(raw) == 5, (
            "all_user_keys() is the positional view (length matches "
            "batch_records, digest-only slots surface as None) — if you "
            "intentionally want only dict-view keys use keys() instead"
        )
        assert None not in keys_view, "Mapping-protocol keys() must never expose None"
        assert None in raw, "positional all_user_keys() must surface the digest-only slot as None"

        # Pin the CHANGELOG migration snippet for the None-hashable
        # hazard. The doc shows:
        #     {k for k in handle.all_user_keys() if k is not None}
        # as the safe form; verify it actually evaluates to the
        # user-keyed subset (no None leaking into a downstream set).
        safe_set = {k for k in raw if k is not None}
        assert safe_set == {"h_0", "h_1", "h_3", "h_4"}
        # And confirm the unsafe form silently keeps None (the trap
        # the CHANGELOG warns about) so a future change that makes
        # all_user_keys filter-by-default fails this test.
        assert None in set(raw)


class TestLazyBatchRecordsReleaseCacheAsync:
    """Async mirror of the sync ``TestLazyBatchRecordsReleaseCache`` in
    ``test_batch.py``. The cache itself lives on ``PyLazyBatchRecords``
    so behaviour is shared with sync, but the async wrapper path
    (``AsyncClient.batch_read`` returning the handle out of ``await``)
    is otherwise untested — a future refactor that eagerly materialises
    on the async side would pass every existing test without this.
    """

    async def test_release_cache_keeps_handle_usable_async(self, async_client, async_cleanup):
        import aerospike_py

        keys = [(NS, SET, f"rel_async_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            async_cleanup.append(k)
            await async_client.put(k, {"v": i})

        handle = await async_client.batch_read(keys)
        # The async wrapper must hand back a real `LazyBatchRecords`
        # instance (not a private subclass) so that downstream
        # `isinstance(...)` checks behave the same as on the sync path.
        assert isinstance(handle, aerospike_py.LazyBatchRecords)
        assert "rel_async_1" in handle
        first_dict = handle.to_dict()

        handle.release_cache()
        assert len(handle) == 3
        assert handle.found_count() == 3
        assert [br.result for br in handle.batch_records] == [0, 0, 0]

        # Mapping access after release rebuilds the cache transparently
        assert handle["rel_async_0"]["v"] == 0
        assert handle.to_dict() == first_dict

    async def test_release_cache_does_not_invalidate_to_numpy_async(self, async_client, async_cleanup):
        import numpy as np

        keys = [(NS, SET, f"rel_async_np_{i}") for i in range(3)]
        for i, k in enumerate(keys):
            async_cleanup.append(k)
            await async_client.put(k, {"score": i * 10})

        handle = await async_client.batch_read(keys)
        _ = handle.to_dict()
        handle.release_cache()

        np_batch = handle.to_numpy(np.dtype([("score", "<i8")]))
        assert int((np_batch.result_codes == 0).sum()) == 3


class TestLazyBatchRecordsMerge:
    """``merge_to_dict`` (single-GIL merge of multiple `LazyBatchRecords`)."""

    async def test_merge_to_dict_combines_lazy_records(self, async_client, async_cleanup):
        from aerospike_py import LazyBatchRecords

        keys_a = [(NS, SET, f"merge_a_{i}") for i in range(3)]
        keys_b = [(NS, SET, f"merge_b_{i}") for i in range(2)]
        for k in keys_a + keys_b:
            async_cleanup.append(k)
            await async_client.put(k, {"v": k[2]})

        ra = await async_client.batch_read(keys_a)
        rb = await async_client.batch_read(keys_b)

        merged = LazyBatchRecords.merge_to_dict([ra, rb])
        assert len(merged) == 2
        assert set(merged[0].keys()) == {f"merge_a_{i}" for i in range(3)}
        assert set(merged[1].keys()) == {f"merge_b_{i}" for i in range(2)}

    async def test_merge_to_dict_empty_list(self):
        from aerospike_py import LazyBatchRecords

        assert LazyBatchRecords.merge_to_dict([]) == []


class TestLazyBatchRecordsToList:
    """``to_list()`` — positional bulk conversion (`list[bins | None]`)."""

    async def test_to_list_positional_order(self, async_client, _seed_records):
        keys = _seed_records
        result = (await async_client.batch_read(keys)).to_list()
        assert isinstance(result, list)
        assert len(result) == len(keys)
        for i, bins in enumerate(result):
            assert bins is not None
            assert bins["name"] == f"user_{i}"
            assert bins["score"] == i * 10

    async def test_to_list_missing_records_are_none_slots(self, async_client, _seed_records):
        """to_dict 는 miss 를 제외하지만 to_list 는 None 슬롯으로 위치를 보존한다."""
        keys = list(_seed_records)
        keys.insert(2, (NS, SET, "to_list_missing_1"))
        keys.append((NS, SET, "to_list_missing_2"))
        result = (await async_client.batch_read(keys)).to_list()
        assert len(result) == len(keys)
        assert result[2] is None
        assert result[-1] is None
        assert result[0]["name"] == "user_0"
        assert result[3]["name"] == "user_2"  # insert 로 한 칸 밀림

    async def test_to_list_duplicate_user_key_across_sets_no_collision(self, async_client, async_cleanup):
        """같은 user_key 가 서로 다른 set 에 동시에 batch 될 때 dict 뷰는 한쪽을
        잃지만 to_list 는 양쪽 모두 위치대로 보존한다 (feature-store 시나리오)."""
        set_b = f"{SET}_b"
        shared = "dup_key_1"
        ka = (NS, SET, shared)
        kb = (NS, set_b, shared)
        async_cleanup.append(ka)
        async_cleanup.append(kb)
        await async_client.put(ka, {"src": "set_a", "a_only": 1})
        await async_client.put(kb, {"src": "set_b", "b_only": 2})

        handle = await async_client.batch_read([ka, kb])
        result = handle.to_list()
        assert len(result) == 2
        assert result[0]["src"] == "set_a"
        assert result[1]["src"] == "set_b"
        # dict 뷰는 user_key 충돌로 하나만 남는다 (비교 기준)
        assert len(handle.to_dict()) == 1

    async def test_to_list_fresh_not_cached(self, async_client, _seed_records):
        """반환 리스트/내부 bins 는 호출마다 fresh — 변형이 다음 호출에 안 보임."""
        handle = await async_client.batch_read(_seed_records)
        first = handle.to_list()
        first[0]["name"] = "mutated"
        second = handle.to_list()
        assert second[0]["name"] == "user_0"

    async def test_to_list_empty_keys(self, async_client):
        assert (await async_client.batch_read([])).to_list() == []

    async def test_to_list_sync_client(self, client, _seed_records):
        """sync Client.batch_read 핸들에서도 동일 동작."""
        result = client.batch_read(_seed_records).to_list()
        assert len(result) == 5
        assert result[4]["score"] == 40


class TestLazyBatchRecordsToListEdgeCases:
    """to_list() 의 result_code / digest-only / 빈 bins 경계 동작."""

    async def test_to_list_filtered_out_is_none_slot(self, async_client, _seed_records):
        """filter_expression 으로 일부만 통과시키면 탈락 슬롯은 None, 위치 보존.

        result_code 비-OK 분기 (record 본문 없이 에러 코드만 오는 경로) 를 고정한다.
        """
        from aerospike_py import exp

        keys = _seed_records  # score = 0,10,20,30,40
        expr = exp.gt(exp.int_bin("score"), exp.int_val(15))
        result = (await async_client.batch_read(keys, policy={"filter_expression": expr})).to_list()
        assert len(result) == len(keys)
        assert result[0] is None  # score=0 filtered
        assert result[1] is None  # score=10 filtered
        assert result[2] is not None and result[2]["score"] == 20
        assert result[3] is not None and result[3]["score"] == 30
        assert result[4] is not None and result[4]["score"] == 40

    async def test_to_list_digest_only_key_returns_bins(self, async_client, _seed_records):
        """digest-only 키 (ns, set, None, digest) 도 성공 read 면 bins 반환.

        dict 뷰는 user_key 가 없어 skip 하지만 positional 은 위치로 식별하므로
        레코드를 잃지 않는다 — to_list 의 의도된 차별 동작.
        """
        keys = _seed_records
        handle = await async_client.batch_read(keys)
        # batch_records[i].key = (ns, set, user_key, digest)
        digest = handle.batch_records[1].key[3]
        assert isinstance(digest, bytes) and len(digest) == 20

        digest_only_key = (NS, SET, None, digest)
        h2 = await async_client.batch_read([keys[0], digest_only_key])
        result = h2.to_list()
        assert len(result) == 2
        assert result[0]["name"] == "user_0"
        assert result[1] is not None and result[1]["name"] == "user_1"  # digest-only 성공
        # 대조: dict 뷰는 digest-only 를 담지 못한다
        assert len(h2.to_dict()) == 1

    async def test_to_list_header_only_read_is_empty_dict_not_none(self, async_client, _seed_records):
        """bins=[] (header-only) 읽기: found 슬롯은 {} — None(miss) 과 구분된다."""
        keys = list(_seed_records[:2])
        keys.append((NS, SET, "to_list_header_missing"))
        result = (await async_client.batch_read(keys, bins=[])).to_list()
        assert len(result) == 3
        assert result[0] == {} and result[0] is not None
        assert result[1] == {}
        assert result[2] is None
