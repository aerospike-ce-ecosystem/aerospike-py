"""FastAPI + ASGI compatibility test (requires Aerospike server).

Uses fastapi.testclient.TestClient to test the FastAPI app in-process,
verifying that AsyncClient works correctly under the ASGI runtime across
a broad range of API operations (CRUD, batch, operations, index, etc.).
"""

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import aerospike_py  # noqa: E402

CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET_NAME = "feasibility_fastapi"
SET_NAME_TRUNC = "feasibility_fastapi_trunc"
SET_NAME_IDX = "feasibility_fastapi_idx"


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
def _create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = aerospike_py.AsyncClient(CONFIG)
        await client.connect()
        app.state.client = client
        yield
        await client.close()

    app = FastAPI(lifespan=lifespan)

    def _key(ns: str, set_name: str, key: str):
        return (ns, set_name, key)

    def _sanitize_key(key):
        """Strip digest bytes for JSON safety."""
        if isinstance(key, (tuple, list)) and len(key) > 3:
            return list(key[:3])
        return key

    # -- Health / Cluster ---------------------------------------------------

    @app.get("/health")
    async def health():
        c = app.state.client
        return {"status": "ok", "connected": c.is_connected()}

    @app.get("/cluster/connected")
    async def cluster_connected():
        return {"connected": app.state.client.is_connected()}

    @app.get("/cluster/nodes")
    async def cluster_nodes():
        nodes = await app.state.client.get_node_names()
        return {"nodes": nodes}

    # -- Basic CRUD ---------------------------------------------------------

    @app.put("/kv/{key}")
    async def put_key(key: str, value: int = 0):
        await app.state.client.put(_key(NS, SET_NAME, key), {"v": value})
        return {"key": key, "value": value}

    @app.get("/kv/{key}")
    async def get_key(key: str):
        k, meta, bins = await app.state.client.get(_key(NS, SET_NAME, key))
        return {"key": _sanitize_key(k), "meta": meta._asdict() if meta else None, "bins": bins}

    @app.delete("/kv/{key}")
    async def delete_key(key: str):
        await app.state.client.remove(_key(NS, SET_NAME, key))
        return {"key": key, "deleted": True}

    # -- Records operations -------------------------------------------------

    @app.post("/records/select")
    async def records_select(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        k, meta, bins = await app.state.client.select(key, body["bins"])
        return {"key": _sanitize_key(k), "meta": meta._asdict() if meta else None, "bins": bins}

    @app.post("/records/exists")
    async def records_exists(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        k, meta = await app.state.client.exists(key)
        return {"key": _sanitize_key(k), "exists": meta is not None, "meta": meta._asdict() if meta else None}

    @app.post("/records/touch")
    async def records_touch(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        await app.state.client.touch(key, body.get("val", 0))
        return {"message": "Record touched"}

    @app.post("/records/append")
    async def records_append(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        await app.state.client.append(key, body["bin"], body["val"])
        return {"message": "Value appended"}

    @app.post("/records/prepend")
    async def records_prepend(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        await app.state.client.prepend(key, body["bin"], body["val"])
        return {"message": "Value prepended"}

    @app.post("/records/increment")
    async def records_increment(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        await app.state.client.increment(key, body["bin"], body["offset"])
        return {"message": "Value incremented"}

    @app.post("/records/remove-bin")
    async def records_remove_bin(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        await app.state.client.remove_bin(key, body["bin_names"])
        return {"message": "Bins removed"}

    # -- Operations ---------------------------------------------------------

    @app.post("/operations/operate")
    async def operations_operate(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        meta_arg = body.get("meta")
        k, meta, bins = await app.state.client.operate(key, body["ops"], meta=meta_arg)
        return {"key": _sanitize_key(k), "meta": meta._asdict() if meta else None, "bins": bins}

    @app.post("/operations/operate-ordered")
    async def operations_operate_ordered(body: dict):
        key = _key(body["ns"], body["set"], body["key"])
        k, meta, ordered = await app.state.client.operate_ordered(key, body["ops"])
        return {
            "key": _sanitize_key(k),
            "meta": meta._asdict() if meta else None,
            "ordered_bins": [list(b) for b in ordered],
        }

    # -- Batch --------------------------------------------------------------

    @app.post("/batch/read")
    async def batch_read(body: dict):
        keys = [_key(k["ns"], k["set"], k["key"]) for k in body["keys"]]
        bins = body.get("bins")
        results = await app.state.client.batch_read(keys, bins=bins)
        sanitized = []
        for br in results.batch_records:
            if br.record is not None:
                k, meta, bins_data = br.record
                sanitized.append(
                    {
                        "key": _sanitize_key(k),
                        "meta": meta._asdict()
                        if hasattr(meta, "_asdict") and meta
                        else (meta if isinstance(meta, dict) else None),
                        "bins": bins_data,
                    }
                )
            else:
                sanitized.append(
                    {
                        "key": _sanitize_key(br.key),
                        "meta": None,
                        "bins": None,
                    }
                )
        return {"batch_records": sanitized}

    @app.post("/batch/operate")
    async def batch_operate(body: dict):
        keys = [_key(k["ns"], k["set"], k["key"]) for k in body["keys"]]
        results = await app.state.client.batch_operate(keys, body["ops"])
        sanitized = []
        for rec in results:
            k, meta, bins_data = rec
            sanitized.append(
                {
                    "key": _sanitize_key(k),
                    "meta": meta._asdict() if meta else None,
                    "bins": bins_data,
                }
            )
        return {"batch_records": sanitized}

    @app.post("/batch/remove")
    async def batch_remove(body: dict):
        keys = [_key(k["ns"], k["set"], k["key"]) for k in body["keys"]]
        results = await app.state.client.batch_remove(keys)
        return {"removed": len(results)}

    # -- Index --------------------------------------------------------------

    @app.post("/indexes")
    async def index_create(body: dict):
        idx_type = body.get("type", "integer")
        ns = body["ns"]
        set_name = body["set"]
        bin_name = body["bin"]
        name = body["name"]
        if idx_type == "string":
            await app.state.client.index_string_create(ns, set_name, bin_name, name)
        else:
            await app.state.client.index_integer_create(ns, set_name, bin_name, name)
        return {"message": f"Index {name} created"}

    @app.delete("/indexes/{ns}/{name}")
    async def index_remove(ns: str, name: str):
        await app.state.client.index_remove(ns, name)
        return {"message": f"Index {name} removed"}

    # -- Truncate -----------------------------------------------------------

    @app.post("/truncate")
    async def truncate(body: dict):
        ns = body["ns"]
        set_name = body["set"]
        nanos = body.get("nanos", 0)
        await app.state.client.truncate(ns, set_name, nanos)
        return {"message": f"Truncated {ns}/{set_name}"}

    # -- Scan ---------------------------------------------------------------

    @app.get("/scan/{ns}/{set_name}")
    async def scan(ns: str, set_name: str):
        records = await app.state.client.scan(ns, set_name)
        sanitized = []
        for rec in records:
            k, meta, bins_data = rec
            sanitized.append(
                {
                    "key": _sanitize_key(k),
                    "meta": meta._asdict() if meta else None,
                    "bins": bins_data,
                }
            )
        return {"records": sanitized}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sync_client():
    """Sync client for test data setup/cleanup."""
    try:
        c = aerospike_py.client(CONFIG).connect()
    except Exception:
        pytest.skip("Aerospike server not available")
    yield c
    c.close()


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient (runs ASGI lifespan in-process)."""
    app = _create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cleanup(sync_client):
    """Function-scoped key cleanup (same pattern as tests/integration/test_crud.py)."""
    keys = []
    yield keys
    for key in keys:
        try:
            sync_client.remove(key)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tests — Health & Cluster
# ---------------------------------------------------------------------------
class TestFastAPIHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["connected"] is True


class TestFastAPICluster:
    def test_is_connected(self, client):
        r = client.get("/cluster/connected")
        assert r.status_code == 200
        assert r.json()["connected"] is True

    def test_get_node_names(self, client):
        r = client.get("/cluster/nodes")
        assert r.status_code == 200
        nodes = r.json()["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) > 0


# ---------------------------------------------------------------------------
# Tests — CRUD
# ---------------------------------------------------------------------------
class TestFastAPICRUD:
    def test_put_and_get(self, client, cleanup):
        cleanup.append((NS, SET_NAME, "crud-1"))
        r = client.put("/kv/crud-1", params={"value": 42})
        assert r.status_code == 200

        r = client.get("/kv/crud-1")
        assert r.status_code == 200
        assert r.json()["bins"]["v"] == 42

    def test_get_not_found(self, client):
        with pytest.raises(aerospike_py.RecordNotFound):
            client.get("/kv/nonexistent-key-xyz")

    def test_delete(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "crud-del-1")
        sync_client.put(key, {"v": 1})
        cleanup.append(key)

        r = client.delete("/kv/crud-del-1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        _, meta = sync_client.exists(key)
        assert meta is None

    def test_put_get_delete_cycle(self, client):
        r = client.put("/kv/crud-cycle", params={"value": 7})
        assert r.status_code == 200

        r = client.get("/kv/crud-cycle")
        assert r.status_code == 200
        assert r.json()["bins"]["v"] == 7

        r = client.delete("/kv/crud-cycle")
        assert r.status_code == 200

    def test_scan(self, client, sync_client, cleanup):
        for i in range(3):
            key = (NS, SET_NAME, f"scan-{i}")
            sync_client.put(key, {"v": i})
            cleanup.append(key)

        r = client.get(f"/scan/{NS}/{SET_NAME}")
        assert r.status_code == 200
        records = r.json()["records"]
        assert len(records) >= 3


# ---------------------------------------------------------------------------
# Tests — Record Operations
# ---------------------------------------------------------------------------
class TestFastAPIRecordOps:
    def test_select(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-select-1")
        sync_client.put(key, {"a": 1, "b": 2, "c": 3})
        cleanup.append(key)

        r = client.post(
            "/records/select",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-select-1",
                "bins": ["a", "c"],
            },
        )
        assert r.status_code == 200
        bins = r.json()["bins"]
        assert bins["a"] == 1
        assert bins["c"] == 3
        assert "b" not in bins

    def test_exists_found(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-exists-1")
        sync_client.put(key, {"v": 1})
        cleanup.append(key)

        r = client.post(
            "/records/exists",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-exists-1",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["exists"] is True
        assert body["meta"]["gen"] >= 1

    def test_exists_not_found(self, client):
        r = client.post(
            "/records/exists",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-exists-nonexistent",
            },
        )
        assert r.status_code == 200
        assert r.json()["exists"] is False

    def test_touch(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-touch-1")
        sync_client.put(key, {"v": 1}, meta={"ttl": 100})
        cleanup.append(key)

        r = client.post(
            "/records/touch",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-touch-1",
                "val": 300,
            },
        )
        assert r.status_code == 200

        _, meta, _ = sync_client.get(key)
        assert meta.ttl > 100

    def test_append(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-append-1")
        sync_client.put(key, {"name": "Alice"})
        cleanup.append(key)

        r = client.post(
            "/records/append",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-append-1",
                "bin": "name",
                "val": "_suffix",
            },
        )
        assert r.status_code == 200

        _, _, bins = sync_client.get(key)
        assert bins["name"] == "Alice_suffix"

    def test_prepend(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-prepend-1")
        sync_client.put(key, {"name": "World"})
        cleanup.append(key)

        r = client.post(
            "/records/prepend",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-prepend-1",
                "bin": "name",
                "val": "Hello_",
            },
        )
        assert r.status_code == 200

        _, _, bins = sync_client.get(key)
        assert bins["name"] == "Hello_World"

    def test_increment(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-incr-1")
        sync_client.put(key, {"counter": 10})
        cleanup.append(key)

        r = client.post(
            "/records/increment",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-incr-1",
                "bin": "counter",
                "offset": 5,
            },
        )
        assert r.status_code == 200

        _, _, bins = sync_client.get(key)
        assert bins["counter"] == 15

    def test_remove_bin(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "rec-rmbin-1")
        sync_client.put(key, {"a": 1, "b": 2, "c": 3})
        cleanup.append(key)

        r = client.post(
            "/records/remove-bin",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "rec-rmbin-1",
                "bin_names": ["b"],
            },
        )
        assert r.status_code == 200

        _, _, bins = sync_client.get(key)
        assert "a" in bins
        assert "b" not in bins
        assert "c" in bins


# ---------------------------------------------------------------------------
# Tests — Operations
# ---------------------------------------------------------------------------
class TestFastAPIOperations:
    def test_operate(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "ops-1")
        sync_client.put(key, {"counter": 10, "name": "test"})
        cleanup.append(key)

        r = client.post(
            "/operations/operate",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "ops-1",
                "ops": [
                    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
                    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
                ],
            },
        )
        assert r.status_code == 200
        assert r.json()["bins"]["counter"] == 15

    def test_operate_with_meta(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "ops-meta-1")
        sync_client.put(key, {"counter": 0})
        cleanup.append(key)

        r = client.post(
            "/operations/operate",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "ops-meta-1",
                "ops": [
                    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
                    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
                ],
                "meta": {"ttl": 300},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["bins"]["counter"] == 1
        assert body["meta"]["gen"] >= 1

    def test_operate_ordered(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "ops-ord-1")
        sync_client.put(key, {"val": 1})
        cleanup.append(key)

        r = client.post(
            "/operations/operate-ordered",
            json={
                "ns": NS,
                "set": SET_NAME,
                "key": "ops-ord-1",
                "ops": [
                    {"op": aerospike_py.OPERATOR_READ, "bin": "val", "val": None},
                ],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["gen"] >= 1
        assert isinstance(body["ordered_bins"], list)
        assert len(body["ordered_bins"]) > 0


# ---------------------------------------------------------------------------
# Tests — Batch
# ---------------------------------------------------------------------------
class TestFastAPIBatch:
    def _key_body(self, key_str: str, set_name: str = SET_NAME):
        return {"ns": NS, "set": set_name, "key": key_str}

    def test_batch_read(self, client, sync_client, cleanup):
        keys = []
        for i in range(3):
            key = (NS, SET_NAME, f"batch-r-{i}")
            sync_client.put(key, {"v": i})
            cleanup.append(key)
            keys.append(self._key_body(f"batch-r-{i}"))

        r = client.post("/batch/read", json={"keys": keys})
        assert r.status_code == 200
        records = r.json()["batch_records"]
        assert len(records) == 3
        for rec in records:
            assert rec["bins"] is not None

    def test_batch_read_partial_not_found(self, client, sync_client, cleanup):
        key = (NS, SET_NAME, "batch-r-exists")
        sync_client.put(key, {"v": 1})
        cleanup.append(key)

        keys = [
            self._key_body("batch-r-exists"),
            self._key_body("batch-r-missing"),
        ]
        r = client.post("/batch/read", json={"keys": keys})
        assert r.status_code == 200
        records = r.json()["batch_records"]
        assert len(records) == 2
        # First record should have data, second should have None bins
        assert records[0]["bins"] is not None
        assert records[1]["bins"] is None

    def test_batch_operate(self, client, sync_client, cleanup):
        keys_body = []
        for i in range(2):
            key = (NS, SET_NAME, f"batch-op-{i}")
            sync_client.put(key, {"counter": 10})
            cleanup.append(key)
            keys_body.append(self._key_body(f"batch-op-{i}"))

        r = client.post(
            "/batch/operate",
            json={
                "keys": keys_body,
                "ops": [
                    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 5},
                    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
                ],
            },
        )
        assert r.status_code == 200
        records = r.json()["batch_records"]
        assert len(records) == 2
        for rec in records:
            counter = rec["bins"]["counter"]
            # batch_operate returns a list of results per bin (INCR→None, READ→15)
            if isinstance(counter, list):
                assert counter[-1] == 15
            else:
                assert counter == 15

    def test_batch_remove(self, client, sync_client, cleanup):
        keys_body = []
        for i in range(2):
            key = (NS, SET_NAME, f"batch-rm-{i}")
            sync_client.put(key, {"v": i})
            # Don't add to cleanup — we're removing them via batch
            keys_body.append(self._key_body(f"batch-rm-{i}"))

        r = client.post("/batch/remove", json={"keys": keys_body})
        assert r.status_code == 200

        # Verify records are gone
        for i in range(2):
            _, meta = sync_client.exists((NS, SET_NAME, f"batch-rm-{i}"))
            assert meta is None


# ---------------------------------------------------------------------------
# Tests — Index
# ---------------------------------------------------------------------------
class TestFastAPIIndex:
    def test_create_and_remove_integer_index(self, client):
        idx_name = "idx_feasibility_int"
        r = client.post(
            "/indexes",
            json={
                "ns": NS,
                "set": SET_NAME_IDX,
                "bin": "age",
                "name": idx_name,
                "type": "integer",
            },
        )
        assert r.status_code == 200
        assert idx_name in r.json()["message"]

        r = client.delete(f"/indexes/{NS}/{idx_name}")
        assert r.status_code == 200
        assert idx_name in r.json()["message"]

    def test_create_and_remove_string_index(self, client):
        idx_name = "idx_feasibility_str"
        r = client.post(
            "/indexes",
            json={
                "ns": NS,
                "set": SET_NAME_IDX,
                "bin": "name",
                "name": idx_name,
                "type": "string",
            },
        )
        assert r.status_code == 200
        assert idx_name in r.json()["message"]

        r = client.delete(f"/indexes/{NS}/{idx_name}")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Tests — Truncate
# ---------------------------------------------------------------------------
class TestFastAPITruncate:
    def test_truncate(self, client, sync_client):
        # Seed data into a dedicated set
        for i in range(3):
            sync_client.put((NS, SET_NAME_TRUNC, f"trunc-{i}"), {"v": i})

        r = client.post(
            "/truncate",
            json={
                "ns": NS,
                "set": SET_NAME_TRUNC,
            },
        )
        assert r.status_code == 200
        assert "Truncated" in r.json()["message"]


# ---------------------------------------------------------------------------
# Tests — Concurrency
# ---------------------------------------------------------------------------
class TestFastAPIConcurrency:
    def test_concurrent_requests(self, client):
        """50 sequential requests via TestClient."""
        for i in range(50):
            key = f"fconcur_{i}"
            client.put(f"/kv/{key}", params={"value": i})
            r = client.get(f"/kv/{key}")
            assert r.json()["bins"]["v"] == i
            client.delete(f"/kv/{key}")
