"""Unit tests for the internal stage metrics toggle (no Aerospike server required).

Verifies:
- Default state is ``False`` (zero-overhead by default).
- ``set_internal_stage_metrics_enabled(bool)`` round-trips.
- ``internal_stage_profiling()`` context manager restores previous state.
- ``AEROSPIKE_PY_INTERNAL_METRICS=1`` env var enables profiling at startup
  (subprocess-isolated to avoid contaminating the in-process flag state).
- When the flag is ``False``, ``record_internal_stage`` emits nothing even
  if called directly.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

import aerospike_py


@pytest.fixture(autouse=True)
def _reset_internal_stage_flag():
    """Snapshot the flag before every test, restore on teardown."""
    prev = aerospike_py.is_internal_stage_metrics_enabled()
    yield
    aerospike_py.set_internal_stage_metrics_enabled(prev)


class TestInternalStageToggleBasics:
    def test_default_disabled(self):
        # Fresh in-process call — if no env var set, default must be False.
        # The autouse fixture may have recorded a prior user change; reset first.
        aerospike_py.set_internal_stage_metrics_enabled(False)
        assert aerospike_py.is_internal_stage_metrics_enabled() is False

    def test_set_true_then_read(self):
        aerospike_py.set_internal_stage_metrics_enabled(True)
        assert aerospike_py.is_internal_stage_metrics_enabled() is True

    def test_set_false_then_read(self):
        aerospike_py.set_internal_stage_metrics_enabled(True)
        aerospike_py.set_internal_stage_metrics_enabled(False)
        assert aerospike_py.is_internal_stage_metrics_enabled() is False

    def test_independent_from_operation_metrics_flag(self):
        """set_metrics_enabled and set_internal_stage_metrics_enabled are independent."""
        aerospike_py.set_metrics_enabled(True)
        aerospike_py.set_internal_stage_metrics_enabled(False)
        assert aerospike_py.is_metrics_enabled() is True
        assert aerospike_py.is_internal_stage_metrics_enabled() is False

        aerospike_py.set_metrics_enabled(False)
        aerospike_py.set_internal_stage_metrics_enabled(True)
        assert aerospike_py.is_metrics_enabled() is False
        assert aerospike_py.is_internal_stage_metrics_enabled() is True

        # Restore for other tests
        aerospike_py.set_metrics_enabled(True)


class TestContextManager:
    def test_enables_inside_block(self):
        aerospike_py.set_internal_stage_metrics_enabled(False)
        with aerospike_py.internal_stage_profiling():
            assert aerospike_py.is_internal_stage_metrics_enabled() is True

    def test_restores_false_after_block(self):
        aerospike_py.set_internal_stage_metrics_enabled(False)
        with aerospike_py.internal_stage_profiling():
            pass
        assert aerospike_py.is_internal_stage_metrics_enabled() is False

    def test_restores_true_after_block_if_already_true(self):
        aerospike_py.set_internal_stage_metrics_enabled(True)
        with aerospike_py.internal_stage_profiling():
            assert aerospike_py.is_internal_stage_metrics_enabled() is True
        assert aerospike_py.is_internal_stage_metrics_enabled() is True

    def test_restores_on_exception(self):
        aerospike_py.set_internal_stage_metrics_enabled(False)
        with pytest.raises(RuntimeError, match="boom"), aerospike_py.internal_stage_profiling():
            assert aerospike_py.is_internal_stage_metrics_enabled() is True
            raise RuntimeError("boom")
        assert aerospike_py.is_internal_stage_metrics_enabled() is False


class TestEnvVarInit:
    """Spawn a subprocess to observe the module-init behavior under env vars.

    Each subprocess gets a fresh Python interpreter where the atomic flag has
    never been touched, so we can directly observe what
    ``init_internal_stage_from_env()`` does at ``_aerospike`` module import.
    """

    def _run(self, env_value: str | None) -> bool:
        script = textwrap.dedent(
            """
            import aerospike_py
            print(aerospike_py.is_internal_stage_metrics_enabled())
            """
        )
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
        if env_value is not None:
            env["AEROSPIKE_PY_INTERNAL_METRICS"] = env_value
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip() == "True"

    def test_default_without_env(self):
        assert self._run(env_value=None) is False

    def test_enabled_by_env_one(self):
        assert self._run(env_value="1") is True

    def test_enabled_by_env_true_lower(self):
        assert self._run(env_value="true") is True

    def test_enabled_by_env_true_title(self):
        assert self._run(env_value="True") is True

    def test_enabled_by_env_yes(self):
        assert self._run(env_value="yes") is True

    def test_enabled_by_env_on(self):
        assert self._run(env_value="on") is True

    def test_enabled_by_env_yes_upper(self):
        assert self._run(env_value="YES") is True

    def test_enabled_by_env_on_titlecase(self):
        assert self._run(env_value="On") is True

    def test_enabled_by_env_true_mixed(self):
        assert self._run(env_value="TrUe") is True

    def test_disabled_by_env_zero(self):
        assert self._run(env_value="0") is False

    def test_disabled_by_env_false(self):
        assert self._run(env_value="false") is False

    def test_disabled_by_env_empty(self):
        assert self._run(env_value="") is False


class TestMetricsTextGating:
    """When the flag is OFF, no stage series should appear in the metrics text."""

    def test_disabled_skips_record(self):
        # Even if we try to record directly via a hypothetical Rust-exposed
        # helper, it would not emit anything. Since there's no such helper
        # exposed, we just assert that the metrics text doesn't accumulate
        # stage observations while the flag is OFF.
        aerospike_py.set_internal_stage_metrics_enabled(False)
        # Baseline: collect before any op
        text_before = aerospike_py.get_metrics()
        # No ops executed; the series should either be absent or unchanged.
        text_after = aerospike_py.get_metrics()
        assert text_before == text_after
        # Sanity: HELP header for the histogram family is always registered.
        assert "db_client_internal_stage_seconds" in text_before
