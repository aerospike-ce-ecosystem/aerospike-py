"""Unit tests for the skip-vs-fail policy that guards server-dependent suites.

Pins the behaviour issue #428 asks for: an unreachable server is a hard failure
under ``AEROSPIKE_REQUIRE_SERVER``, and a client-side error is never reported as
"server not available" even when skipping is otherwise allowed.
"""

import pytest

from tests import server as server_policy


@pytest.fixture(autouse=True)
def _clear_require_server(monkeypatch):
    monkeypatch.delenv(server_policy.REQUIRE_SERVER_ENV, raising=False)


def _set_reachable(monkeypatch, reachable):
    monkeypatch.setattr(server_policy, "server_reachable", lambda *a, **kw: reachable)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "anything"])
def test_server_required_true_values(monkeypatch, value):
    monkeypatch.setenv(server_policy.REQUIRE_SERVER_ENV, value)
    assert server_policy.server_required()


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "  FALSE  "])
def test_server_required_false_values(monkeypatch, value):
    monkeypatch.setenv(server_policy.REQUIRE_SERVER_ENV, value)
    assert not server_policy.server_required()


def test_server_required_unset(monkeypatch):
    assert not server_policy.server_required()


def test_skip_or_raise_skips_when_unreachable_and_not_required(monkeypatch):
    """The local-dev convenience path: port closed, skipping allowed."""
    _set_reachable(monkeypatch, False)
    with pytest.raises(pytest.skip.Exception):
        server_policy.skip_or_raise(OSError("connection refused"))


def test_skip_or_raise_refuses_to_skip_when_required(monkeypatch):
    """CI path: an unreachable server must fail, not skip."""
    monkeypatch.setenv(server_policy.REQUIRE_SERVER_ENV, "1")
    _set_reachable(monkeypatch, False)
    with pytest.raises(RuntimeError, match="must succeed"):
        server_policy.skip_or_raise(OSError("connection refused"))


def test_skip_or_raise_refuses_to_skip_a_client_side_error(monkeypatch):
    """Port open means the client failed, so never report it as an absent server."""
    _set_reachable(monkeypatch, True)
    with pytest.raises(RuntimeError, match="client-side failure"):
        server_policy.skip_or_raise(TypeError("bad argument"))


def test_skip_or_raise_chains_the_original_exception(monkeypatch):
    _set_reachable(monkeypatch, True)
    original = TypeError("bad argument")
    with pytest.raises(RuntimeError) as excinfo:
        server_policy.skip_or_raise(original)
    assert excinfo.value.__cause__ is original


def test_skip_or_fail_unreachable_returns_when_reachable(monkeypatch):
    _set_reachable(monkeypatch, True)
    assert server_policy.skip_or_fail_unreachable() is None


def test_skip_or_fail_unreachable_skips_when_not_required(monkeypatch):
    _set_reachable(monkeypatch, False)
    with pytest.raises(pytest.skip.Exception):
        server_policy.skip_or_fail_unreachable()


def test_skip_or_fail_unreachable_fails_when_required(monkeypatch):
    monkeypatch.setenv(server_policy.REQUIRE_SERVER_ENV, "1")
    _set_reachable(monkeypatch, False)
    with pytest.raises(pytest.fail.Exception):
        server_policy.skip_or_fail_unreachable()
