"""Unit tests for aerospike_py._bug_report module."""

import logging

import pytest

from aerospike_py._bug_report import catch_unexpected, log_unexpected_error


class TestLogUnexpectedError:
    """Tests for log_unexpected_error function."""

    def test_logs_at_error_level(self, caplog):
        exc = TypeError("test error message")
        with caplog.at_level(logging.ERROR, logger="aerospike_py"):
            log_unexpected_error("TestContext.method", exc)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR

    def test_log_contains_gh_issue_create(self, caplog):
        exc = ValueError("something broke")
        with caplog.at_level(logging.ERROR, logger="aerospike_py"):
            log_unexpected_error("Client.get", exc)

        msg = caplog.records[0].message
        assert "gh issue create --repo KimSoungRyoul/aerospike-py" in msg

    def test_log_contains_context(self, caplog):
        exc = RuntimeError("internal failure")
        with caplog.at_level(logging.ERROR, logger="aerospike_py"):
            log_unexpected_error("Client.operate", exc)

        msg = caplog.records[0].message
        assert "Client.operate" in msg

    def test_log_contains_error_type_and_message(self, caplog):
        exc = IndexError("index out of range")
        with caplog.at_level(logging.ERROR, logger="aerospike_py"):
            log_unexpected_error("Client.get", exc)

        msg = caplog.records[0].message
        assert "IndexError" in msg
        assert "index out of range" in msg

    def test_log_contains_bug_report_message(self, caplog):
        exc = TypeError("unexpected")
        with caplog.at_level(logging.ERROR, logger="aerospike_py"):
            log_unexpected_error("Client.get", exc)

        msg = caplog.records[0].message
        assert "This error may be a bug in aerospike-py" in msg


class TestCatchUnexpectedSync:
    """Tests for catch_unexpected decorator with sync functions."""

    def test_passes_through_aerospike_error(self):
        from aerospike_py._aerospike import AerospikeError

        @catch_unexpected("test.method")
        def raises_aerospike():
            raise AerospikeError("expected error")

        with pytest.raises(AerospikeError):
            raises_aerospike()

    def test_aerospike_error_not_logged(self, caplog):
        from aerospike_py._aerospike import AerospikeError

        @catch_unexpected("test.method")
        def raises_aerospike():
            raise AerospikeError("expected error")

        with caplog.at_level(logging.ERROR, logger="aerospike_py"), pytest.raises(AerospikeError):
            raises_aerospike()

        assert len(caplog.records) == 0

    def test_unexpected_error_logged_and_reraised(self, caplog):
        @catch_unexpected("test.method")
        def raises_type_error():
            raise TypeError("unexpected bug")

        with caplog.at_level(logging.ERROR, logger="aerospike_py"), pytest.raises(TypeError, match="unexpected bug"):
            raises_type_error()

        assert len(caplog.records) == 1
        assert "gh issue create" in caplog.records[0].message

    def test_normal_return_value_preserved(self):
        @catch_unexpected("test.method")
        def returns_value():
            return 42

        assert returns_value() == 42


class TestCatchUnexpectedAsync:
    """Tests for catch_unexpected decorator with async functions."""

    @pytest.mark.asyncio
    async def test_async_passes_through_aerospike_error(self):
        from aerospike_py._aerospike import AerospikeError

        @catch_unexpected("test.async_method")
        async def raises_aerospike():
            raise AerospikeError("expected error")

        with pytest.raises(AerospikeError):
            await raises_aerospike()

    @pytest.mark.asyncio
    async def test_async_aerospike_error_not_logged(self, caplog):
        from aerospike_py._aerospike import AerospikeError

        @catch_unexpected("test.async_method")
        async def raises_aerospike():
            raise AerospikeError("expected error")

        with caplog.at_level(logging.ERROR, logger="aerospike_py"), pytest.raises(AerospikeError):
            await raises_aerospike()

        assert len(caplog.records) == 0

    @pytest.mark.asyncio
    async def test_async_unexpected_error_logged_and_reraised(self, caplog):
        @catch_unexpected("test.async_method")
        async def raises_type_error():
            raise TypeError("async bug")

        with caplog.at_level(logging.ERROR, logger="aerospike_py"), pytest.raises(TypeError, match="async bug"):
            await raises_type_error()

        assert len(caplog.records) == 1
        assert "gh issue create" in caplog.records[0].message

    @pytest.mark.asyncio
    async def test_async_normal_return_value_preserved(self):
        @catch_unexpected("test.async_method")
        async def returns_value():
            return 99

        assert await returns_value() == 99
