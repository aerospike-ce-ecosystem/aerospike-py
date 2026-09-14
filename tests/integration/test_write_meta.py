"""Integration tests for the per-call ``meta`` dict on single-record writes.

``WriteMeta`` documents six keys (``gen``, ``ttl``, ``key``, ``exists``,
``commit_level``, ``durable_delete``); every one of them must reach the server
on ``put()`` / ``remove()`` / ``touch()`` / ``operate()``, not just ``gen`` and
``ttl``.  ``durable_delete`` is Enterprise-only, so it is covered by the Rust
unit tests rather than here.
"""

import pytest

import aerospike_py


class TestWriteMetaExists:
    def test_put_meta_exists_create_only_on_existing_record(self, client, cleanup):
        """``meta={"exists": CREATE_ONLY}`` must fail instead of overwriting."""
        key = ("test", "demo", "meta_exists_existing")
        cleanup.append(key)
        client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordExistsError):
            client.put(key, {"val": 2}, meta={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})

        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_put_meta_exists_create_only_on_new_record(self, client, cleanup):
        """``meta={"exists": CREATE_ONLY}`` still writes a record that is absent."""
        key = ("test", "demo", "meta_exists_new")
        cleanup.append(key)

        client.put(key, {"val": 1}, meta={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})

        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_policy_dict_overrides_meta(self, client, cleanup):
        """Precedence is unchanged: an explicit ``policy`` wins over ``meta``."""
        key = ("test", "demo", "meta_exists_override")
        cleanup.append(key)
        client.put(key, {"val": 1})

        client.put(
            key,
            {"val": 2},
            meta={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            policy={"exists": aerospike_py.POLICY_EXISTS_IGNORE},
        )

        _, _, bins = client.get(key)
        assert bins["val"] == 2


class TestWriteMetaKeyAndCommitLevel:
    def test_put_meta_key_send_persists_user_key(self, client, cleanup):
        """``meta={"key": POLICY_KEY_SEND}`` stores the primary key server-side.

        ``get()`` echoes back the key it was handed, so persistence is checked
        through a scan, whose keys come from the server.
        """
        sent = ("test", "meta_keysend", "meta_key_sent")
        digest_only = ("test", "meta_keysend", "meta_key_digest")
        cleanup.append(sent)
        cleanup.append(digest_only)

        client.put(sent, {"val": 1}, meta={"key": aerospike_py.POLICY_KEY_SEND})
        client.put(digest_only, {"val": 2})

        # Key the assertions on the two known digests so leftovers from an
        # aborted earlier run on a shared server cannot break the test.
        sent_digest = client.get(sent)[0][3]
        digest_only_digest = client.get(digest_only)[0][3]

        scanned = {record_key[3]: record_key[2] for record_key, _, _ in client.query("test", "meta_keysend").results()}
        assert scanned[sent_digest] == "meta_key_sent"
        assert scanned[digest_only_digest] is None

    def test_put_meta_commit_level_master(self, client, cleanup):
        """``meta={"commit_level": ...}`` is accepted and does not break the write."""
        key = ("test", "demo", "meta_commit_master")
        cleanup.append(key)

        client.put(
            key,
            {"val": 1},
            meta={"commit_level": aerospike_py.POLICY_COMMIT_LEVEL_MASTER},
        )

        _, _, bins = client.get(key)
        assert bins["val"] == 1

    def test_put_meta_gen_and_ttl_still_work(self, client, cleanup):
        """The two pre-existing meta keys keep their semantics."""
        key = ("test", "demo", "meta_gen_ttl")
        cleanup.append(key)
        client.put(key, {"val": 1})

        _, meta, _ = client.get(key)
        client.put(key, {"val": 2}, meta={"gen": meta.gen, "ttl": 3600})

        _, new_meta, _ = client.get(key)
        assert new_meta.gen == meta.gen + 1
        assert 0 < new_meta.ttl <= 3600

        # The stale generation is now rejected (CAS semantics preserved).
        with pytest.raises(aerospike_py.RecordGenerationError):
            client.put(key, {"val": 3}, meta={"gen": meta.gen})


class TestWriteMetaAsync:
    async def test_async_put_meta_exists_create_only(self, async_client, async_cleanup):
        key = ("test", "demo", "meta_exists_async")
        async_cleanup.append(key)
        await async_client.put(key, {"val": 1})

        with pytest.raises(aerospike_py.RecordExistsError):
            await async_client.put(
                key,
                {"val": 2},
                meta={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
            )

        _, _, bins = await async_client.get(key)
        assert bins["val"] == 1

    async def test_async_put_meta_exists_create_only_on_new_record(self, async_client, async_cleanup):
        key = ("test", "demo", "meta_exists_new_async")
        async_cleanup.append(key)

        await async_client.put(
            key,
            {"val": 1},
            meta={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY},
        )

        _, _, bins = await async_client.get(key)
        assert bins["val"] == 1
