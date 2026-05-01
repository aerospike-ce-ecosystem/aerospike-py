"""Unit tests for ``batch_apply`` API surface (no server required).

Verifies that:
- ``BatchUDFPolicy`` / ``BatchUDFMeta`` TypedDicts can be instantiated
  and are re-exported at the top-level ``aerospike_py`` namespace.
- The ``batch_apply`` method is exposed on ``Client`` and ``AsyncClient``
  with the documented signature.
"""

from __future__ import annotations

import inspect

import pytest

import aerospike_py
from aerospike_py.types import BatchUDFMeta, BatchUDFPolicy


class TestBatchUDFPolicy:
    def test_empty_policy_is_valid(self):
        policy: BatchUDFPolicy = {}
        assert policy == {}

    def test_full_policy_fields(self):
        policy: BatchUDFPolicy = {
            "commit_level": aerospike_py.POLICY_COMMIT_LEVEL_MASTER,
            "ttl": 3600,
            "key": aerospike_py.POLICY_KEY_SEND,
            "durable_delete": False,
        }
        assert policy["commit_level"] == aerospike_py.POLICY_COMMIT_LEVEL_MASTER
        assert policy["ttl"] == 3600
        assert policy["key"] == aerospike_py.POLICY_KEY_SEND
        assert policy["durable_delete"] is False


class TestBatchUDFMeta:
    def test_call_overrides(self):
        meta: BatchUDFMeta = {
            "module": "other_module",
            "function": "other_function",
            "args": [1, 2, "three"],
        }
        assert meta["module"] == "other_module"
        assert meta["function"] == "other_function"
        assert meta["args"] == [1, 2, "three"]

    def test_policy_overrides_in_same_dict(self):
        meta: BatchUDFMeta = {
            "ttl": 60,
            "commit_level": aerospike_py.POLICY_COMMIT_LEVEL_MASTER,
            "key": aerospike_py.POLICY_KEY_SEND,
            "durable_delete": True,
        }
        assert meta["ttl"] == 60
        assert meta["commit_level"] == aerospike_py.POLICY_COMMIT_LEVEL_MASTER
        assert meta["durable_delete"] is True

    def test_call_and_policy_in_same_dict(self):
        meta: BatchUDFMeta = {
            "args": [42],
            "ttl": 120,
        }
        assert meta["args"] == [42]
        assert meta["ttl"] == 120


class TestPublicReexports:
    def test_batch_udf_policy_at_module_level(self):
        assert aerospike_py.BatchUDFPolicy is BatchUDFPolicy

    def test_batch_udf_meta_at_module_level(self):
        assert aerospike_py.BatchUDFMeta is BatchUDFMeta

    def test_in_all_exports(self):
        assert "BatchUDFPolicy" in aerospike_py.__all__
        assert "BatchUDFMeta" in aerospike_py.__all__


class TestClientBatchApplyMethod:
    def test_sync_client_has_batch_apply(self):
        assert hasattr(aerospike_py.Client, "batch_apply")
        # Inspect the wrapper signature on the Python class.
        sig = inspect.signature(aerospike_py.Client.batch_apply)
        params = list(sig.parameters.keys())
        # self, keys, module, function, args, policy
        assert "keys" in params
        assert "module" in params
        assert "function" in params
        assert "args" in params
        assert "policy" in params

    def test_async_client_has_batch_apply(self):
        assert hasattr(aerospike_py.AsyncClient, "batch_apply")
        sig = inspect.signature(aerospike_py.AsyncClient.batch_apply)
        params = list(sig.parameters.keys())
        assert "keys" in params
        assert "module" in params
        assert "function" in params
        assert "args" in params
        assert "policy" in params

    def test_batch_apply_requires_connection(self):
        """Calling batch_apply on an unconnected client should raise."""
        client = aerospike_py.client({"hosts": [("127.0.0.1", 1)]})
        with pytest.raises(aerospike_py.ClientError):
            client.batch_apply([("test", "demo", "k")], "m", "f")
