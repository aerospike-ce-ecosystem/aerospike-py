"""FastAPI + ASGI compatibility test (requires Aerospike server).

Uses fastapi.testclient.TestClient to test the FastAPI app in-process,
avoiding subprocess/fork issues entirely.
"""

import pytest

pytest.importorskip("fastapi")

import aerospike_py  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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


@pytest.fixture(scope="module")
def client():
    app = _create_app()
    with TestClient(app) as c:
        yield c


class TestFastAPIFeasibility:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["connected"] is True

    def test_put_get_delete(self, client):
        r = client.put("/kv/ftest1", params={"value": 42})
        assert r.status_code == 200

        r = client.get("/kv/ftest1")
        assert r.status_code == 200
        assert r.json()["bins"]["v"] == 42

        r = client.delete("/kv/ftest1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    def test_concurrent_requests(self, client):
        """50 sequential requests via TestClient."""
        for i in range(50):
            key = f"fconcur_{i}"
            client.put(f"/kv/{key}", params={"value": i})
            r = client.get(f"/kv/{key}")
            assert r.json()["bins"]["v"] == i
            client.delete(f"/kv/{key}")
