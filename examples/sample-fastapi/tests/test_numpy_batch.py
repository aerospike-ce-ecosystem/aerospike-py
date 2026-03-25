"""Integration tests — 500x 128-dim vector batch_read via TestClient + Aerospike."""

from __future__ import annotations

import base64

import numpy as np

NS, SET = "test", "np_vec"
DIM = 128
N = 500
BLOB_SIZE = DIM * 4  # float32


def _key_body(pk: str):
    return {"namespace": NS, "set_name": SET, "key": pk}


def _seed_vectors(aerospike_client, cleanup):
    """Insert 500 L2-normalized 128-dim vectors + score bin into Aerospike."""
    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((N, DIM)).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / norms  # L2 normalize

    keys = []
    for i in range(N):
        key = (NS, SET, f"v_{i}")
        aerospike_client.put(
            key,
            {"embedding": vectors[i].tobytes(), "score": float(i)},
            meta={"ttl": 3600},
        )
        keys.append(key)
        cleanup.append(key)
    return vectors, keys


# ── columnar batch read ─────────────────────────────────────


def test_batch_read_500_vectors_as_bytes(client, aerospike_client, cleanup):
    """Batch-read 500 vectors as S{blob_size} dtype and verify byte round-trip."""
    vectors, _ = _seed_vectors(aerospike_client, cleanup)

    resp = client.post(
        "/numpy-batch/read",
        json={
            "keys": [_key_body(f"v_{i}") for i in range(N)],
            "dtype": [
                {"name": "embedding", "dtype": f"S{BLOB_SIZE}"},
                {"name": "score", "dtype": "f8"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == N
    assert all(rc == 0 for rc in data["result_codes"])

    # Verify score values
    scores = data["columns"]["score"]
    assert len(scores) == N
    for i in range(N):
        assert scores[i] == float(i)

    # Decode base64 embedding bytes → float32 and compare with originals
    blobs_b64 = data["columns"]["embedding"]
    assert len(blobs_b64) == N
    for i in range(0, N, 50):  # sample every 50th record
        raw = base64.b64decode(blobs_b64[i])
        recovered = np.frombuffer(raw, dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, vectors[i], decimal=5)


# ── vector search (cosine similarity) ──────────────────────


def test_vector_search_top_k(client, aerospike_client, cleanup):
    """Cosine similarity top-10 search over 500 vectors."""
    vectors, _ = _seed_vectors(aerospike_client, cleanup)

    # Use v_42 as the query vector — it should rank first with score ~1.0
    query = vectors[42].tolist()

    resp = client.post(
        "/numpy-batch/vector-search",
        json={
            "keys": [_key_body(f"v_{i}") for i in range(N)],
            "query_vector": query,
            "embedding_bin": "embedding",
            "embedding_dim": DIM,
            "extra_bins": ["score"],
            "top_k": 10,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] == N

    results = data["results"]
    assert len(results) == 10

    # Top result should be v_42 itself
    assert results[0]["key"] == "v_42"
    assert results[0]["score"] >= 0.999
    assert results[0]["bins"]["score"] == 42.0

    # Verify descending score order
    for i in range(len(results) - 1):
        assert results[i]["score"] >= results[i + 1]["score"]


# ── mixed existing / missing keys ─────────────────────────────


def test_batch_read_with_missing_keys(client, aerospike_client, cleanup):
    """Batch-read a mix of existing vectors and non-existent keys."""
    _vectors, _ = _seed_vectors(aerospike_client, cleanup)

    # 0-9: existing, 10-14: non-existent
    key_bodies = [_key_body(f"v_{i}") for i in range(10)]
    key_bodies += [_key_body(f"missing_{i}") for i in range(5)]

    resp = client.post(
        "/numpy-batch/read",
        json={
            "keys": key_bodies,
            "dtype": [
                {"name": "embedding", "dtype": f"S{BLOB_SIZE}"},
                {"name": "score", "dtype": "f8"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 10  # only successful records counted

    # First 10 should succeed, remaining 5 should fail
    for i in range(10):
        assert data["result_codes"][i] == 0
    for i in range(10, 15):
        assert data["result_codes"][i] != 0
        assert data["columns"]["score"][i] == 0.0


# ── metadata verification ───────────────────────────────────


def test_batch_read_meta(client, aerospike_client, cleanup):
    """Verify gen/ttl metadata in batch_read results."""
    _seed_vectors(aerospike_client, cleanup)

    resp = client.post(
        "/numpy-batch/read",
        json={
            "keys": [_key_body(f"v_{i}") for i in range(10)],
            "dtype": [{"name": "score", "dtype": "f8"}],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    for i in range(10):
        assert data["meta"]["gen"][i] >= 1
        assert data["meta"]["ttl"][i] > 0


# ── invalid dtype rejection ─────────────────────────────────


def test_invalid_dtype_rejected(client, aerospike_client, cleanup):
    """Unicode dtype should return 400 error."""
    _seed_vectors(aerospike_client, cleanup)

    resp = client.post(
        "/numpy-batch/read",
        json={
            "keys": [_key_body("v_0")],
            "dtype": [{"name": "score", "dtype": "U10"}],
        },
    )

    assert resp.status_code == 400
    assert "kind='U'" in resp.json()["detail"]
