"""FastAPI + uvicorn ASGI compatibility test (requires Aerospike server)."""

import asyncio
import multiprocessing
import socket
import time

import pytest

httpx = pytest.importorskip("httpx")
fastapi = pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")

import aerospike_py  # noqa: E402

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET_NAME = "feasibility_fastapi"


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
def _create_app():
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    @asynccontextmanager
    async def lifespan(app):
        client = aerospike_py.AsyncClient(CONFIG)
        await client.connect()
        app.state.client = client
        yield
        await client.close()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health():
        client = app.state.client
        return {
            "status": "ok",
            "connected": client.is_connected(),
        }

    @app.put("/kv/{key}")
    async def put_key(key: str, value: int = 0):
        await app.state.client.put((NS, SET_NAME, key), {"v": value})
        return {"key": key, "value": value}

    @app.get("/kv/{key}")
    async def get_key(key: str):
        _, _, bins = await app.state.client.get((NS, SET_NAME, key))
        return {"key": key, "bins": bins}

    @app.delete("/kv/{key}")
    async def delete_key(key: str):
        await app.state.client.remove((NS, SET_NAME, key))
        return {"key": key, "deleted": True}

    return app


def _run_server(port: int):
    app = _create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


def _free_port() -> int:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Server on port {port} did not start within {timeout}s")


@pytest.fixture(scope="module")
def server_url():
    port = _free_port()
    proc = multiprocessing.Process(target=_run_server, args=(port,), daemon=True)
    proc.start()
    try:
        _wait_for_server(port)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=3)


class TestFastAPIFeasibility:
    async def test_health(self, server_url):
        async with httpx.AsyncClient(base_url=server_url) as c:
            r = await c.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
            assert r.json()["connected"] is True

    async def test_put_get_delete(self, server_url):
        async with httpx.AsyncClient(base_url=server_url) as c:
            r = await c.put("/kv/ftest1", params={"value": 42})
            assert r.status_code == 200

            r = await c.get("/kv/ftest1")
            assert r.status_code == 200
            assert r.json()["bins"]["v"] == 42

            r = await c.delete("/kv/ftest1")
            assert r.status_code == 200
            assert r.json()["deleted"] is True

    async def test_concurrent_requests(self, server_url):
        """50 concurrent HTTP requests."""

        async def do_request(c, i):
            key = f"fconcur_{i}"
            await c.put(f"/kv/{key}", params={"value": i})
            r = await c.get(f"/kv/{key}")
            assert r.json()["bins"]["v"] == i
            await c.delete(f"/kv/{key}")

        async with httpx.AsyncClient(base_url=server_url) as c:
            await asyncio.gather(*(do_request(c, i) for i in range(50)))
