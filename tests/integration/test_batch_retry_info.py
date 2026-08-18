"""``BatchWriteResult.retry`` reporting — issue #425.

``retry=N`` asks for ``N + 1`` attempts but is bounded by ``total_timeout``,
which defaults to 1000 ms. Before this, the truncation was reported only through
a ``log::warn!``, so a caller reasoning about data-loss windows from the retry
count was reasoning from a number the client does not honour.

These tests pin the counters end to end. The boundary arithmetic of the guard
itself is unit-tested in ``rust/src/client_ops.rs``
(``retry_budget_permits`` tests), which is where the truncation case can be
covered deterministically.
"""

import pytest

from tests.helpers import invoke

NS = "test"
SET_NAME = "batch_retry_info"


def _records(prefix, count=10):
    return [((NS, SET_NAME, f"{prefix}_{i}"), {"v": i}) for i in range(count)]


class TestRetryInfoDefaults:
    def test_batch_write_without_retry_reports_a_single_attempt(self, client, cleanup):
        records = _records("noretry")
        cleanup.extend(k for k, _ in records)

        result = client.batch_write(records)

        assert result.retry.attempts == 1
        assert result.retry.max_attempts == 1
        assert result.retry.truncated_by_timeout is False
        assert result.retry.unresolved == 0

    def test_batch_operate_reports_the_default(self, client, cleanup):
        """No ``retry`` parameter, so nothing to report — but the field exists."""
        records = _records("operate")
        cleanup.extend(k for k, _ in records)
        client.batch_write(records)

        from aerospike_py import list_operations as lops

        result = client.batch_operate([k for k, _ in records], [lops.list_append("log", 1)])

        assert result.retry.attempts == 1
        assert result.retry.max_attempts == 1
        assert result.retry.truncated_by_timeout is False

    def test_batch_remove_reports_the_default(self, client, cleanup):
        records = _records("remove")
        client.batch_write(records)

        result = client.batch_remove([k for k, _ in records])

        assert result.retry.attempts == 1
        assert result.retry.max_attempts == 1


class TestRetryInfoWithRetryRequested:
    @pytest.mark.parametrize("retry", [1, 5, 10])
    def test_max_attempts_reflects_what_the_caller_asked_for(self, client, cleanup, retry):
        """``max_attempts`` is ``retry + 1`` even when no retry was needed.

        This is the number the caller believes they bought; ``attempts`` is what
        they actually got. Reporting both is what makes truncation visible.
        """
        records = _records(f"asked{retry}")
        cleanup.extend(k for k, _ in records)

        result = client.batch_write(records, retry=retry)

        assert result.retry.max_attempts == retry + 1
        assert result.retry.attempts >= 1
        assert result.retry.attempts <= result.retry.max_attempts

    def test_a_healthy_batch_uses_exactly_one_attempt(self, client, cleanup):
        records = _records("healthy")
        cleanup.extend(k for k, _ in records)

        result = client.batch_write(records, policy={"total_timeout": 30000}, retry=10)

        assert result.retry.attempts == 1, "a batch that succeeds outright must not retry"
        assert result.retry.unresolved == 0
        assert result.retry.truncated_by_timeout is False
        assert all(br.result == 0 for br in result.batch_records)

    def test_raising_total_timeout_does_not_change_a_successful_call(self, client, cleanup):
        """The client never lengthens the budget itself; the caller sets it."""
        records = _records("budget")
        cleanup.extend(k for k, _ in records)

        default_budget = client.batch_write(records, retry=10)
        raised_budget = client.batch_write(records, policy={"total_timeout": 30000}, retry=10)

        assert default_budget.retry == raised_budget.retry


class TestRetryInfoAsync:
    async def test_async_batch_write_reports_retry_info(self, async_client, async_cleanup):
        records = _records("async")
        async_cleanup.extend(k for k, _ in records)

        result = await async_client.batch_write(records, retry=4)

        assert result.retry.max_attempts == 5
        assert result.retry.attempts == 1
        assert result.retry.truncated_by_timeout is False

    async def test_async_batch_remove_reports_the_default(self, async_client):
        records = _records("asyncrm")
        await async_client.batch_write(records)

        result = await async_client.batch_remove([k for k, _ in records])

        assert result.retry.max_attempts == 1


class TestRetryInfoIsBackwardCompatible:
    def test_batch_records_is_still_the_first_field(self, client, cleanup):
        """Existing callers index or unpack ``batch_records`` positionally."""
        records = _records("compat")
        cleanup.extend(k for k, _ in records)

        result = client.batch_write(records)

        assert result[0] is result.batch_records
        assert len(result.batch_records) == len(records)

    async def test_any_client_batch_write_keeps_working(self, any_client, any_cleanup):
        records = _records("anyclient")
        any_cleanup.extend(k for k, _ in records)

        result = await invoke(any_client, "batch_write", records)

        assert [br.result for br in result.batch_records] == [0] * len(records)
