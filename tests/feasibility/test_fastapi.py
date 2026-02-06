"""FastAPI + ASGI compatibility test (requires Aerospike server).

Uses httpx.ASGITransport to test the FastAPI app in-process,
avoiding subprocess/fork issues entirely.
"""

import asyncio

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

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


@pytest.fixture(scope="module")
def app():
    return _create_app()


@pytest.fixture
async def client(app):
    """In-process ASGI test client — no subprocess needed."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


class TestFastAPIFeasibility:
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["connected"] is True

    async def test_put_get_delete(self, client):
        r = await client.put("/kv/ftest1", params={"value": 42})
        assert r.status_code == 200

        r = await client.get("/kv/ftest1")
        assert r.status_code == 200
        assert r.json()["bins"]["v"] == 42

        r = await client.delete("/kv/ftest1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

    async def test_concurrent_requests(self, client):
        """50 concurrent requests via ASGI transport."""

        async def do_request(i):
            key = f"fconcur_{i}"
            await client.put(f"/kv/{key}", params={"value": i})
            r = await client.get(f"/kv/{key}")
            assert r.json()["bins"]["v"] == i
            await client.delete(f"/kv/{key}")

        await asyncio.gather(*(do_request(i) for i in range(50)))
