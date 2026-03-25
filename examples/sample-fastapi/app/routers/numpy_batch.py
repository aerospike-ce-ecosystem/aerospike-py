"""Numpy batch API — columnar batch read, batch write, and vector similarity search."""

from __future__ import annotations

import base64
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

from aerospike_py import AsyncClient
from app.dependencies import get_client
from app.models import (
    NumpyBatchReadRequest,
    NumpyBatchReadResponse,
    NumpyBatchWriteRequest,
    NumpyBatchWriteResponse,
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
        raise HTTPException(status_code=400, detail=f"Invalid dtype: {e}") from e

    keys = [k.to_tuple() for k in body.keys]
    bin_names = body.bins or [f.name for f in body.dtype]

    try:
        result = await client.batch_read(keys, bins=bin_names, _dtype=dtype)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
        count=int((result.result_codes == 0).sum()),
    )


@router.post("/write", response_model=NumpyBatchWriteResponse)
async def numpy_batch_write(
    body: NumpyBatchWriteRequest,
    client: AsyncClient = Depends(get_client),
):
    """Write multiple records from a JSON payload via numpy batch_write_numpy.

    Converts the incoming row data into a numpy structured array and calls
    the high-performance batch_write_numpy API.
    """
    try:
        dtype = _build_dtype(body.dtype)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid dtype: {e}") from e

    dtype_names = {f.name for f in body.dtype}
    if body.key_field not in dtype_names:
        raise HTTPException(
            status_code=400,
            detail=f"key_field '{body.key_field}' not found in dtype fields: {sorted(dtype_names)}",
        )

    try:
        data = np.array([tuple(row) for row in body.rows], dtype=dtype)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Row data does not match dtype: {e}") from e

    results = await client.batch_write_numpy(data, body.namespace, body.set_name, dtype, key_field=body.key_field)
    # batch_write_numpy returns list of Record NamedTuples;
    # meta is not None when the write succeeded (server returns gen/ttl)
    codes = [0 if r.meta is not None else -1 for r in results]
    ok = sum(1 for c in codes if c == 0)
    return NumpyBatchWriteResponse(written=ok, failed=len(results) - ok, result_codes=codes)


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

    # Validate query_vector before I/O to avoid wasted batch reads
    query = np.array(body.query_vector, dtype=np.float32)
    if len(query) != dim:
        raise HTTPException(
            status_code=422,
            detail=f"query_vector length {len(query)} does not match embedding_dim {dim}",
        )
    query_norm = float(np.linalg.norm(query))
    if not np.isfinite(query_norm) or query_norm == 0.0:
        raise HTTPException(status_code=422, detail="query_vector must be finite and non-zero")

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

    # bytes → float32 vectors (skip records with wrong blob size or non-finite values)
    raw_blobs = result.batch_records[body.embedding_bin]
    all_vectors = np.zeros((len(raw_blobs), dim), dtype=np.float32)
    valid_mask = ok_mask.copy()
    for i in range(len(raw_blobs)):
        if ok_mask[i]:
            if len(raw_blobs[i]) == blob_size:
                vec = np.frombuffer(raw_blobs[i], dtype=np.float32)
                if np.all(np.isfinite(vec)):
                    all_vectors[i] = vec
                else:
                    valid_mask[i] = False
            else:
                valid_mask[i] = False

    # cosine similarity (vectorized)
    vec_norms = np.linalg.norm(all_vectors, axis=1)
    # 0-norm 방지
    safe_norms = np.where(vec_norms > 0, vec_norms, 1.0)
    similarities = (all_vectors @ query) / (safe_norms * query_norm)
    similarities = np.where(valid_mask, similarities, -2.0)  # 실패/잘못된 blob 레코드 제외

    # top-k: filter to valid indices first, then take top_k by similarity
    valid_indices = np.where(valid_mask)[0]
    valid_sims = similarities[valid_indices]
    top_k = min(body.top_k, len(valid_indices))
    top_within_valid = np.argsort(valid_sims)[::-1][:top_k]
    top_indices = valid_indices[top_within_valid]

    results = []
    pk_list = [k.key for k in body.keys]
    for idx in top_indices:
        idx = int(idx)
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
