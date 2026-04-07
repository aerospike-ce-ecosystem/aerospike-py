"""Unit tests for batch_write() method (generic, dict-based)."""

import inspect

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
