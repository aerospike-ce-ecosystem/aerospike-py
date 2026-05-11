"""FastAPI app modeling the production ssa-pctcvr endpoint shape.

Endpoint ``POST /predict``:
  1. (optional) NumPy NxN matmul — co-resident CPU-bound work to model
     DLRM-style GIL contention from inference threads.
  2. 9 ``batch_read`` calls in parallel via ``asyncio.gather`` — one per
     feature view, 80 keys each → 720 keys total.
  3. Returns ``{found: int, total: int}``.

Single client instance per uvicorn worker is created during ``lifespan``
startup; closed during shutdown.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import numpy as np
from fastapi import FastAPI

from . import config
from .clients import AsyncBatchReadClient, create_client
from .keys import request_keys

_client: AsyncBatchReadClient | None = None
_rng = random.Random(os.getpid())  # per-worker RNG keeps key sampling distinct


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _client
    _client = await create_client()
    yield
    if _client is not None:
        await _client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "client": config.CLIENT_KIND, "pid": str(os.getpid())}


_TORCH_MODEL = None


def _maybe_init_torch() -> None:
    """Lazily build a small DLRM-style network on first call when enabled."""
    global _TORCH_MODEL
    if _TORCH_MODEL is not None or not config.CPU_BOUND_TORCH:
        return
    import torch

    torch.set_num_threads(1)  # one Python-side worker; mimics inference threadpool=1
    _TORCH_MODEL = torch.nn.Sequential(
        torch.nn.Linear(1024, 1024),
        torch.nn.ReLU(),
        torch.nn.Linear(1024, 1024),
        torch.nn.ReLU(),
        torch.nn.Linear(1024, 1),
    ).eval()


def _cpu_burn() -> None:
    """CPU-bound work modeling DLRM inference GIL pressure.

    Three modes (selected by env):
    1. ``CPU_BOUND_TORCH=1`` — runs a 3-layer Linear network forward (preferred,
       closest to issue's prod env).
    2. ``CPU_BOUND_BURN_MS>0`` — loops NumPy matmul + Python reduction until
       the target wall-time is reached. NumPy releases GIL during matmul but
       Python-level ``.sum()`` reacquires it, creating the same hand-off
       pattern as torch CPU ops.
    3. else — legacy single NxN matmul (no Python reduction). Kept for
       backward compat with the original baseline measurements.
    """
    if config.CPU_BOUND_TORCH:
        import torch

        _maybe_init_torch()
        assert _TORCH_MODEL is not None
        with torch.no_grad():
            x = torch.randn(64, 1024)
            _ = _TORCH_MODEL(x).sum().item()
        return

    if config.CPU_BOUND_BURN_MS > 0:
        # Pure-Python loop — GIL is held continuously (no BLAS release).
        # This is the closest model of DLRM forward setup overhead (module
        # iteration, parameter access, etc.) that competes with the tokio
        # worker's GIL acquisition after batch_read I/O completes.
        target_s = config.CPU_BOUND_BURN_MS / 1000.0
        deadline = time.perf_counter() + target_s
        total = 0
        i = 0
        while time.perf_counter() < deadline:
            # Inner batch — checking perf_counter every iter is too costly,
            # so amortize over 10k iters per check.
            for _ in range(10_000):
                total += i * i
                i += 1
        return

    # Legacy single-shot path
    n = config.CPU_BOUND_MATMUL_N
    a = np.random.rand(n, n)
    b = np.random.rand(n, n)
    _ = a @ b


@app.post("/predict")
async def predict() -> dict[str, int | float]:
    assert _client is not None
    t0 = time.perf_counter()

    if config.CPU_BOUND_ENABLED:
        _cpu_burn()

    t_after_burn = time.perf_counter()
    key_matrix = request_keys(_rng)

    results = await asyncio.gather(
        *[_client.batch_read(keys) for keys in key_matrix]
    )

    total_keys = sum(len(k) for k in key_matrix)
    found = sum(results)
    elapsed = time.perf_counter() - t0
    db_elapsed = time.perf_counter() - t_after_burn

    return {
        "found": found,
        "total": total_keys,
        "elapsed_ms": round(elapsed * 1000, 3),
        "db_elapsed_ms": round(db_elapsed * 1000, 3),
    }
