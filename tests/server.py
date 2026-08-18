"""Server-availability policy shared by every suite that needs a live Aerospike.

Each server-dependent fixture used to wrap ``connect()`` in a bare
``except Exception: pytest.skip(...)``. That turns any client-side regression on
the connect path — host parsing, client-policy parsing, argument validation —
into a fully-skipped suite and a green CI job, which is the exact class of
regression those suites exist to catch.

Two rules replace the bare skip:

* ``AEROSPIKE_REQUIRE_SERVER`` — set in the CI jobs that provision a server, and
  in any environment where a skip is never legitimate. Connect failures are
  re-raised instead of skipped.
* Otherwise the skip is allowed only when a TCP probe confirms the server really
  is unreachable. If the port accepts a connection, the failure came from the
  client rather than the network, so it is re-raised even locally.

The probe is what narrows the failure mode: it decides "is the server there?"
from the network rather than from an exception type, so a client-side
``TypeError`` can never read as "server not available".
"""

import os
import socket
from typing import NoReturn

import pytest

#: Set this (to anything other than an explicit falsey word) to turn an
#: unreachable server into a failure instead of a skip.
REQUIRE_SERVER_ENV = "AEROSPIKE_REQUIRE_SERVER"

_FALSEY = frozenset({"", "0", "false", "no", "off"})


def server_required() -> bool:
    """Whether an unreachable Aerospike server must fail rather than skip."""
    return os.environ.get(REQUIRE_SERVER_ENV, "").strip().lower() not in _FALSEY


def server_host_port() -> tuple[str, int]:
    """The host/port the suites connect to, honouring the usual env overrides."""
    return (
        os.environ.get("AEROSPIKE_HOST", "127.0.0.1"),
        int(os.environ.get("AEROSPIKE_PORT", "18710")),
    )


def server_reachable(host: str | None = None, port: int | None = None, timeout: float = 1.0) -> bool:
    """Whether a TCP connection to the Aerospike service port succeeds."""
    default_host, default_port = server_host_port()
    try:
        with socket.create_connection((host or default_host, port if port is not None else default_port), timeout):
            return True
    except OSError:
        return False


def skip_or_raise(exc: BaseException, reason: str = "Aerospike server not available") -> NoReturn:
    """Re-raise *exc* unless skipping is genuinely warranted.

    Call from the ``except`` block around a ``connect()``. Skips only when the
    environment permits it *and* the service port is actually closed; otherwise
    the original exception propagates with its traceback intact.
    """
    host, port = server_host_port()
    if server_required():
        raise RuntimeError(
            f"{REQUIRE_SERVER_ENV} is set, so connecting to {host}:{port} must succeed. Refusing to skip: {exc!r}"
        ) from exc
    if server_reachable():
        raise RuntimeError(
            f"{host}:{port} accepts connections, so this is a client-side failure, "
            f"not an unreachable server. Refusing to skip: {exc!r}"
        ) from exc
    pytest.skip(f"{reason} ({host}:{port}): {exc}")


def skip_or_fail_unreachable(reason: str = "Aerospike server not available") -> None:
    """Skip (or fail under ``AEROSPIKE_REQUIRE_SERVER``) when the port is closed.

    For suites that probe the socket directly instead of catching a connect
    exception. Returns normally when the server is reachable.
    """
    if server_reachable():
        return
    host, port = server_host_port()
    if server_required():
        pytest.fail(f"{REQUIRE_SERVER_ENV} is set but no Aerospike server is reachable at {host}:{port}")
    pytest.skip(f"{reason} ({host}:{port})")


# ── server lifecycle control (destructive tests only) ───────────────────────
#
# Some behaviours can only be reached by taking the server away mid-call — a
# transport error on a batch write, a query stream interrupted part-way. Tests
# that do that carry the `destructive` marker and are deselected by default,
# because restarting the server voids module-scoped client fixtures and the
# cleanup of every other module sharing the session.

CONTAINER_ENV = "AEROSPIKE_CONTAINER"
RUNTIME_ENV = "RUNTIME"


def container_name() -> str:
    return os.environ.get(CONTAINER_ENV, "aerospike")


def container_runtime() -> str:
    return os.environ.get(RUNTIME_ENV, "podman")


def can_control_server() -> bool:
    """Whether the configured container runtime can start/stop our Aerospike."""
    import shutil
    import subprocess

    runtime = container_runtime()
    if shutil.which(runtime) is None:
        return False
    try:
        listed = subprocess.run([runtime, "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return container_name() in listed.stdout.split()


def control_server(action: str) -> None:
    """Run `start` / `stop` / `restart` against the Aerospike container."""
    import subprocess

    subprocess.run([container_runtime(), action, container_name()], check=True, capture_output=True, timeout=120)


def wait_until_serving(config: dict, timeout: float = 90.0) -> None:
    """Block until a fresh client can connect, so the next test is not raced.

    Probes with a real client rather than the container's own health command:
    the container reports ready slightly before the cluster accepts client
    connections, and that gap is long enough to fail the next fixture.
    """
    import time

    import aerospike_py

    deadline = time.monotonic() + timeout
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            probe = aerospike_py.client(config).connect()
        except Exception as exc:  # cluster not accepting connections yet
            last_error = exc
            time.sleep(0.5)
            continue
        probe.close()
        return
    raise RuntimeError(f"{container_name()} did not accept a client within {timeout}s: {last_error!r}")
