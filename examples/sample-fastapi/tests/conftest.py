from __future__ import annotations

import contextlib
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

import aerospike_py

# Ensure the app package is importable regardless of working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_AEROSPIKE_CONFIG_TEMPLATE = """\
service {{
    cluster-name docker
}}

logging {{
    console {{
        context any info
    }}
}}

network {{
    service {{
        address any
        port 3000
        access-address 127.0.0.1
        access-port {port}
    }}

    heartbeat {{
        mode mesh
        address local
        port 3002
        interval 150
        timeout 10
    }}

    fabric {{
        address local
        port 3001
    }}
}}

namespace test {{
    replication-factor 1
    default-ttl 2592000
    nsup-period 120

    storage-engine device {{
        file /opt/aerospike/data/test.dat
        filesize 4G
        read-page-cache true
    }}
}}
"""


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def aerospike_container(tmp_path_factory):
    """Start an Aerospike CE container for the entire test session."""
    host_port = _find_free_port()

    # Write a custom config template that sets access-address/access-port
    # so the Aerospike client can reconnect via the mapped host port.
    tmpdir = tmp_path_factory.mktemp("aerospike")
    config_path = tmpdir / "aerospike.template.conf"
    config_path.write_text(_AEROSPIKE_CONFIG_TEMPLATE.format(port=host_port))

    container = (
        DockerContainer("aerospike:ce-8.1.0.3_1")
        .with_bind_ports(3000, host_port)
        .with_volume_mapping(str(config_path), "/etc/aerospike/aerospike.template.conf", "ro")
        .with_env("NAMESPACE", "test")
        .with_env("DEFAULT_TTL", "2592000")
    )
    container.start()
    wait_for_logs(container, "heartbeat-received", timeout=60)
    # Give Aerospike a moment to fully initialize after heartbeat
    time.sleep(2)
    yield container, host_port
    container.stop()


@pytest.fixture(scope="session")
def jaeger_container():
    """Start a Jaeger all-in-one container for tracing tests."""
    ui_port = _find_free_port()
    otlp_port = _find_free_port()

    container = (
        DockerContainer("jaegertracing/jaeger:latest")
        .with_bind_ports(16686, ui_port)
        .with_bind_ports(4317, otlp_port)
        .with_env("COLLECTOR_OTLP_ENABLED", "true")
    )
    container.start()
    # Wait for Jaeger HTTP API to become available
    import urllib.error
    import urllib.request

    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{ui_port}/api/services")
            break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(1)
    else:
        raise RuntimeError("Jaeger did not become ready in time")

    yield container, otlp_port, ui_port
    container.stop()


@pytest.fixture(scope="session")
def aerospike_client(aerospike_container):
    """Provide a sync Aerospike client for test data setup/teardown."""
    _, port = aerospike_container
    config = {
        "hosts": [("127.0.0.1", port)],
        "cluster_name": "docker",
        "policies": {"key": aerospike_py.POLICY_KEY_SEND},
    }
    c = aerospike_py.client(config).connect()
    yield c
    c.close()


@pytest.fixture(scope="session")
def client(aerospike_container):
    """Provide a FastAPI TestClient with a real AsyncClient connected to the container."""
    from app.main import app

    _, port = aerospike_container

    @asynccontextmanager
    async def _test_lifespan(a):
        # Disable tracing export in default test lifespan (no Jaeger by default)
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_INFO)
        aerospike_py.init_tracing()
        a.state.tracing_enabled = True

        ac = aerospike_py.AsyncClient(
            {
                "hosts": [("127.0.0.1", port)],
                "cluster_name": "docker",
                "policies": {"key": aerospike_py.POLICY_KEY_SEND},
            }
        )
        await ac.connect()
        a.state.aerospike = ac
        yield
        await ac.close()
        aerospike_py.shutdown_tracing()
        a.state.tracing_enabled = False

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app) as tc:
        yield tc
    app.router.lifespan_context = original_lifespan


@pytest.fixture(autouse=True)
def cleanup(aerospike_client):
    """Function-scoped fixture that cleans up records after each test."""
    keys: list[tuple] = []
    yield keys
    for key in keys:
        with contextlib.suppress(Exception):
            aerospike_client.remove(key)
