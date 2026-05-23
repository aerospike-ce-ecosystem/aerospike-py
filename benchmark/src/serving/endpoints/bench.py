"""GIL-detach benchmark endpoints.

Two routes that share the same pipeline shape (batch_read N keys →
materialise → cheap torch op → return JSON) but differ in **only one
step**: how the batch result is materialised.

* ``/bench/dict``  — ``handle.to_dict()`` then build a torch tensor from
  Python dicts. GIL held for the entire per-record loop in Rust.
* ``/bench/numpy`` — ``handle.to_numpy(dtype)`` then ``torch.from_numpy``
  the contiguous float32 column. GIL released during the buffer fill
  (see ``rust/src/numpy_support.rs::batch_to_numpy_py``).

Both endpoints run the *same* model and return the *same* response shape,
so an external load tester (``oha``) can compare RPS / p99 directly. The
keyspace is seeded by ``serving.bench_seed``.

The point of this comparison: when several uvicorn workers (or threads)
are doing CPU-bound Python work on the same process, the numpy path
should hold the GIL less and let siblings make more progress.
"""

from __future__ import annotations

import logging
import os
import time

import numpy as np
import torch
from fastapi import APIRouter, Query, Request

logger = logging.getLogger("serving.bench")
router = APIRouter(prefix="/bench")

# Match the layout written by bench_seed.py.
#
# The feature count is read from the BENCH_N_FEATURES env var so we can
# scale the conversion work without rebuilding the wheel. The default is
# tuned to make conversion + tensor-build a non-trivial slice of the
# request: small enough to keep IO fast, large enough that the GIL is
# actually under pressure while bins → tensor materialises.
N_FEATURES = int(os.environ.get("BENCH_N_FEATURES", "64"))
DTYPE = np.dtype([(f"f{i}", "f4") for i in range(N_FEATURES)])
FEATURE_NAMES = [f"f{i}" for i in range(N_FEATURES)]

NS = "test"
SET = "bench_serving"


def _keys(batch_size: int) -> list[tuple[str, str, str]]:
    return [(NS, SET, f"row_{i}") for i in range(batch_size)]


# A small two-layer MLP so the inference step does real work (not a single
# matmul) — closer to a production DLRM "top tower" than the previous
# 16×1 linear placeholder. Dimensions kept modest so torch doesn't drown
# out the conversion difference, but big enough that the call holds the
# GIL for a measurable slice of the request.
_HIDDEN = 256
_W1 = torch.randn(N_FEATURES, _HIDDEN) * 0.05
_B1 = torch.zeros(_HIDDEN)
_W2 = torch.randn(_HIDDEN, 1) * 0.05
_B2 = torch.zeros(1)


def _dummy_inference(matrix: torch.Tensor) -> torch.Tensor:
    h = torch.matmul(matrix, _W1) + _B1
    h = torch.relu(h)
    return torch.matmul(h, _W2) + _B2


@router.get("/dict")
async def bench_dict(
    request: Request,
    batch_size: int = Query(200, ge=1, le=5000),
) -> dict:
    """`to_dict()` path: handle → Python dict → ``torch.tensor`` (bulk build).

    Uses the common Python-stack idiom — collect rows into a nested list and
    hand the whole thing to ``torch.tensor`` once. This is roughly what a
    typical FastAPI/PyTorch service writes when the upstream call returns a
    dict. We deliberately avoid the cell-by-cell ``matrix[i, j] = v`` anti-
    pattern that would punish the dict path unfairly.
    """
    t0 = time.perf_counter()
    keys = _keys(batch_size)

    t_io_start = time.perf_counter()
    handle = await request.app.state.py_client.batch_read(keys)
    t_io = time.perf_counter() - t_io_start

    t_conv_start = time.perf_counter()
    result_dict = handle.to_dict()
    # Build a list-of-lists, then a single tensor allocation. This is the
    # standard "dict → tensor" pattern in Python services.
    rows: list[list[float]] = []
    for i in range(batch_size):
        bins = result_dict.get(f"row_{i}") or {}
        rows.append([bins.get(name, 0.0) for name in FEATURE_NAMES])
    matrix = torch.tensor(rows, dtype=torch.float32)
    t_conv = time.perf_counter() - t_conv_start

    t_inf_start = time.perf_counter()
    out = _dummy_inference(matrix)
    t_inf = time.perf_counter() - t_inf_start

    return {
        "path": "dict",
        "batch_size": batch_size,
        "found": len(result_dict),
        "io_ms": round(t_io * 1000, 3),
        "conv_ms": round(t_conv * 1000, 3),
        "inference_ms": round(t_inf * 1000, 3),
        "total_ms": round((time.perf_counter() - t0) * 1000, 3),
        "score_sum": round(float(out.sum()), 4),
    }


@router.get("/numpy")
async def bench_numpy(
    request: Request,
    batch_size: int = Query(200, ge=1, le=5000),
) -> dict:
    """`to_numpy(dtype)` path: handle → numpy → torch.from_numpy."""
    t0 = time.perf_counter()
    keys = _keys(batch_size)

    t_io_start = time.perf_counter()
    handle = await request.app.state.py_client.batch_read(keys)
    t_io = time.perf_counter() - t_io_start

    t_conv_start = time.perf_counter()
    np_batch = handle.to_numpy(DTYPE)
    # Lift structured array to a contiguous float32 matrix the model can eat.
    # `np.column_stack` produces fresh contiguous memory; `torch.from_numpy`
    # then shares that buffer (no copy).
    structured = np_batch.batch_records
    matrix_np = np.column_stack([structured[name] for name in FEATURE_NAMES]).astype(
        np.float32, copy=False
    )
    matrix = torch.from_numpy(matrix_np)
    t_conv = time.perf_counter() - t_conv_start

    t_inf_start = time.perf_counter()
    out = _dummy_inference(matrix)
    t_inf = time.perf_counter() - t_inf_start

    return {
        "path": "numpy",
        "batch_size": batch_size,
        "found": int((np_batch.result_codes == 0).sum()),
        "io_ms": round(t_io * 1000, 3),
        "conv_ms": round(t_conv * 1000, 3),
        "inference_ms": round(t_inf * 1000, 3),
        "total_ms": round((time.perf_counter() - t0) * 1000, 3),
        "score_sum": round(float(out.sum()), 4),
    }
