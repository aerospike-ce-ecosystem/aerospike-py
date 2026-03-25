"""128-dim vector 500건 batch_read 통합 테스트 (TestClient + Aerospike)."""

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
    """500개의 128-dim 정규화 벡터 + score bin을 Aerospike에 삽입."""
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
    """500개 128-dim 벡터를 S{blob_size} dtype으로 batch_read → bytes 복원 검증."""
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

    # score 검증
    scores = data["columns"]["score"]
    assert len(scores) == N
    for i in range(N):
        assert scores[i] == float(i)

    # embedding bytes (base64) → float32 복원 후 원본과 비교
    blobs_b64 = data["columns"]["embedding"]
    assert len(blobs_b64) == N
    for i in range(0, N, 50):  # 50 간격 샘플 검증
        raw = base64.b64decode(blobs_b64[i])
        recovered = np.frombuffer(raw, dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, vectors[i], decimal=5)


# ── vector search (cosine similarity) ──────────────────────


def test_vector_search_top_k(client, aerospike_client, cleanup):
    """500개 벡터에서 cosine similarity top-10 검색."""
    vectors, _ = _seed_vectors(aerospike_client, cleanup)

    # v_42를 query로 사용 → 자기 자신이 score ~1.0으로 1위
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

    # 1위는 자기 자신 (v_42)
    assert results[0]["key"] == "v_42"
    assert results[0]["score"] >= 0.999
    assert results[0]["bins"]["score"] == 42.0

    # score 내림차순 정렬 확인
    for i in range(len(results) - 1):
        assert results[i]["score"] >= results[i + 1]["score"]


# ── missing key 혼합 ────────────────────────────────────────


def test_batch_read_with_missing_keys(client, aerospike_client, cleanup):
    """존재하는 벡터 + 존재하지 않는 key 혼합 batch_read."""
    _vectors, _ = _seed_vectors(aerospike_client, cleanup)

    # 0~9: 존재, 10~14: 존재하지 않음
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
    # count는 성공한 레코드 수만 반영
    assert data["count"] == 10

    # 처음 10개는 성공, 나머지 5개는 실패
    for i in range(10):
        assert data["result_codes"][i] == 0
    for i in range(10, 15):
        assert data["result_codes"][i] != 0
        assert data["columns"]["score"][i] == 0.0


# ── meta 검증 ───────────────────────────────────────────────


def test_batch_read_meta(client, aerospike_client, cleanup):
    """batch_read 결과의 gen/ttl meta 검증."""
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


# ── invalid dtype 거부 ──────────────────────────────────────


def test_invalid_dtype_rejected(client, aerospike_client, cleanup):
    """Unicode dtype 요청 시 400 에러."""
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


# ── batch_write_numpy ─────────────────────────────────────


WRITE_SET = "np_write"


def test_batch_write_and_read_back(client, aerospike_client, cleanup):
    """batch_write_numpy로 쓴 레코드를 integer key로 write/read 라운드트립 검증."""
    resp = client.post(
        "/numpy-batch/write",
        json={
            "namespace": NS,
            "set_name": WRITE_SET,
            "dtype": [
                {"name": "_key", "dtype": "i4"},
                {"name": "temperature", "dtype": "f8"},
                {"name": "humidity", "dtype": "i4"},
            ],
            "rows": [[i, 20.0 + i * 0.5, 50 + i] for i in range(10)],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["written"] == 10
    assert data["failed"] == 0
    assert len(data["result_codes"]) == 10
    assert all(c == 0 for c in data["result_codes"])

    # cleanup 등록 (integer key)
    for i in range(10):
        cleanup.append((NS, WRITE_SET, i))

    # batch_read API로 다시 읽어서 값 검증
    resp2 = client.post(
        "/numpy-batch/read",
        json={
            "keys": [{"namespace": NS, "set_name": WRITE_SET, "key": i} for i in range(10)],
            "dtype": [
                {"name": "temperature", "dtype": "f8"},
                {"name": "humidity", "dtype": "i4"},
            ],
        },
    )

    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["count"] == 10

    # 읽기 결과의 실제 값 검증
    temps = data2["columns"]["temperature"]
    humids = data2["columns"]["humidity"]
    for i in range(10):
        assert data2["result_codes"][i] == 0
        assert abs(temps[i] - (20.0 + i * 0.5)) < 0.01
        assert humids[i] == 50 + i


def test_batch_write_invalid_rows_rejected(client):
    """dtype과 맞지 않는 row 데이터는 400 에러."""
    resp = client.post(
        "/numpy-batch/write",
        json={
            "namespace": NS,
            "set_name": WRITE_SET,
            "dtype": [
                {"name": "_key", "dtype": "i4"},
                {"name": "value", "dtype": "f8"},
            ],
            "rows": [["not_a_number", 1.0]],  # _key는 i4인데 문자열 전달
        },
    )

    assert resp.status_code == 400


# ── vector search validation ────────────────────────────────


def test_vector_search_zero_embedding_dim_rejected(client):
    """embedding_dim=0 은 Pydantic 검증에서 422 에러."""
    resp = client.post(
        "/numpy-batch/vector-search",
        json={
            "keys": [_key_body("v_0")],
            "query_vector": [0.1],
            "embedding_bin": "embedding",
            "embedding_dim": 0,
            "top_k": 1,
        },
    )

    assert resp.status_code == 422


def test_vector_search_nan_query_rejected(client, aerospike_client, cleanup):
    """NaN이 포함된 query_vector는 422 에러."""
    _seed_vectors(aerospike_client, cleanup)

    resp = client.post(
        "/numpy-batch/vector-search",
        json={
            "keys": [_key_body("v_0")],
            "query_vector": [float("nan")] * DIM,
            "embedding_bin": "embedding",
            "embedding_dim": DIM,
            "top_k": 1,
        },
    )

    assert resp.status_code == 422
    assert "finite" in resp.json()["detail"]


def test_vector_search_dim_mismatch_rejected(client, aerospike_client, cleanup):
    """query_vector 길이와 embedding_dim 불일치 시 422 에러."""
    _seed_vectors(aerospike_client, cleanup)

    resp = client.post(
        "/numpy-batch/vector-search",
        json={
            "keys": [_key_body("v_0")],
            "query_vector": [0.1, 0.2],  # DIM=128인데 2-dim 벡터
            "embedding_bin": "embedding",
            "embedding_dim": DIM,
            "top_k": 1,
        },
    )

    assert resp.status_code == 422
    assert "does not match embedding_dim" in resp.json()["detail"]
