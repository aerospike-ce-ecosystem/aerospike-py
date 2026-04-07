"""Unit tests for batch_write() method (generic, dict-based)."""

import inspect

import pytest

import aerospike_py
from aerospike_py.types import BatchRecord


class TestBatchRecordInDoubt:
    """Verify BatchRecord has in_doubt field."""

    def test_batch_record_has_in_doubt_field(self):
        assert "in_doubt" in BatchRecord._fields

    def test_batch_record_field_order(self):
        assert BatchRecord._fields == ("key", "result", "record", "in_doubt")


class TestBatchWriteSignature:
    """Verify batch_write method exists and has correct signature."""

    def test_sync_client_has_batch_write(self):
        assert hasattr(aerospike_py.Client, "batch_write")

    def test_async_client_has_batch_write(self):
        assert hasattr(aerospike_py.AsyncClient, "batch_write")

    def test_sync_signature_has_records_param(self):
        sig = inspect.signature(aerospike_py.Client.batch_write)
        assert "records" in sig.parameters

    def test_sync_signature_has_policy_param(self):
        sig = inspect.signature(aerospike_py.Client.batch_write)
        assert "policy" in sig.parameters
        assert sig.parameters["policy"].default is None

    def test_sync_signature_has_retry_param(self):
        sig = inspect.signature(aerospike_py.Client.batch_write)
        assert "retry" in sig.parameters
        assert sig.parameters["retry"].default == 0

    def test_async_signature_has_records_param(self):
        sig = inspect.signature(aerospike_py.AsyncClient.batch_write)
        assert "records" in sig.parameters

    def test_async_signature_has_retry_param(self):
        sig = inspect.signature(aerospike_py.AsyncClient.batch_write)
        assert "retry" in sig.parameters
        assert sig.parameters["retry"].default == 0


class TestBatchWriteInputValidation:
    """Verify batch_write() raises correct errors for invalid inputs."""

    def test_record_must_be_tuple(self, client):
        """Non-tuple record raises TypeError."""
        with pytest.raises(TypeError, match="must be a tuple"):
            client.batch_write([{"key": ("test", "demo", "k1"), "bins": {"a": 1}}])

    def test_tuple_must_have_at_least_2_elements(self, client):
        """Single-element tuple raises ValueError."""
        with pytest.raises(ValueError, match="at least 2 elements"):
            client.batch_write([(("test", "demo", "k1"),)])

    def test_bins_must_be_dict(self, client):
        """Non-dict bins element raises TypeError."""
        with pytest.raises(TypeError, match="must be a dict"):
            client.batch_write([(("test", "demo", "k1"), [("a", 1)])])
