"""Numpy batch_read API — columnar batch read and vector similarity search."""

from __future__ import annotations

import base64
from typing import Any

import numpy as np
from aerospike_py import AsyncClient
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_client
from app.models import (
    NumpyBatchReadRequest,
    NumpyBatchReadResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
)

router = APIRouter(prefix="/numpy-batch", tags=["numpy-batch"])


def _build_dtype(fields) -> np.dtype:
    """DtypeField 리스트 → np.dtype 변환."""
    spec = []
    for f in fields:
        if f.shape:
            spec.append((f.name, f.dtype, tuple(f.shape)))
        else:
            spec.append((f.name, f.dtype))
    return np.dtype(spec)


def _field_to_json(arr: np.ndarray) -> list[Any]:
    """numpy 필드 배열을 JSON-serializable 리스트로 변환."""
    if arr.dtype.kind == "S":  # bytes → base64
        return [base64.b64encode(v).decode() for v in arr]
    if arr.dtype.kind == "V":  # void → base64
        return [base64.b64encode(bytes(v)).decode() for v in arr]
    if arr.ndim > 1:  # sub-array → nested list
        return arr.tolist()
    return arr.tolist()


@router.post("/read", response_model=NumpyBatchReadResponse)
async def numpy_batch_read(
    body: NumpyBatchReadRequest,
    client: AsyncClient = Depends(get_client),
):
    """Batch read records and return as columnar numpy-converted data.

    Returns data in columnar format for efficient analytics:
    each field becomes an array rather than per-record dicts.
    """
    try:
        dtype = _build_dtype(body.dtype)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid dtype: {e}")

    keys = [k.to_tuple() for k in body.keys]
    bin_names = body.bins or [f.name for f in body.dtype]

    try:
        result = await client.batch_read(keys, bins=bin_names, _dtype=dtype)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    columns = {}
    for name in dtype.names:
        columns[name] = _field_to_json(result.batch_records[name])

    pk_list = [k.key for k in body.keys]

    return NumpyBatchReadResponse(
        columns=columns,
        meta={
            "gen": result.meta["gen"].tolist(),
            "ttl": result.meta["ttl"].tolist(),
        },
        result_codes=result.result_codes.tolist(),
        keys=pk_list,
        count=len(result.batch_records),
    )


@router.post("/vector-search", response_model=VectorSearchResponse)
async def vector_search(
    body: VectorSearchRequest,
    client: AsyncClient = Depends(get_client),
):
    """Batch read vector embeddings and rank by cosine similarity.

    Reads embedding blobs from Aerospike, converts to numpy arrays,
    and computes cosine similarity against the query vector.
    """
    dim = body.embedding_dim
    blob_size = dim * 4  # float32

    # dtype 구성: embedding (bytes) + extra bins (float64)
    dtype_spec: list[tuple] = [(body.embedding_bin, f"S{blob_size}")]
    if body.extra_bins:
        for b in body.extra_bins:
            dtype_spec.append((b, "f8"))
    dtype = np.dtype(dtype_spec)

    keys = [k.to_tuple() for k in body.keys]
    bin_names = [body.embedding_bin] + (body.extra_bins or [])
    result = await client.batch_read(keys, bins=bin_names, _dtype=dtype)

    ok_mask = result.result_codes == 0
    total_found = int(ok_mask.sum())

    if total_found == 0:
        return VectorSearchResponse(results=[], total_found=0)

    # bytes → float32 vectors
    raw_blobs = result.batch_records[body.embedding_bin]
    all_vectors = np.zeros((len(raw_blobs), dim), dtype=np.float32)
    for i in range(len(raw_blobs)):
        if ok_mask[i] and len(raw_blobs[i]) == blob_size:
            all_vectors[i] = np.frombuffer(raw_blobs[i], dtype=np.float32)

    query = np.array(body.query_vector, dtype=np.float32)

    # cosine similarity (vectorized)
    query_norm = np.linalg.norm(query)
    vec_norms = np.linalg.norm(all_vectors, axis=1)
    # 0-norm 방지
    safe_norms = np.where(vec_norms > 0, vec_norms, 1.0)
    similarities = (all_vectors @ query) / (safe_norms * query_norm)
    similarities = np.where(ok_mask, similarities, -2.0)  # 실패 레코드 제외

    # top-k
    top_k = min(body.top_k, total_found)
    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []
    pk_list = [k.key for k in body.keys]
    for idx in top_indices:
        idx = int(idx)
        if not ok_mask[idx]:
            continue
        extra = {}
        if body.extra_bins:
            for b in body.extra_bins:
                extra[b] = float(result.batch_records[idx][b])
        results.append(
            VectorSearchResult(
                key=pk_list[idx],
                score=float(similarities[idx]),
                bins=extra or None,
            )
        )

    return VectorSearchResponse(results=results, total_found=total_found)
