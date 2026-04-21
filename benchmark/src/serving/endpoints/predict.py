"""Prediction endpoints — /predict/official and /predict/py-async.

Each endpoint runs the full pipeline:
  1. Extract keys from request
  2. Batch-read from Aerospike (all sets)
  3. Feature extraction (bins -> tensors)
  4. DLRM inference
  5. Build response

Every stage is traced (OTel), metered (Prometheus), and logged (NELO).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import torch
from benchmark.config import ALL_SETS, get_namespace
from benchmark.keys import extract_all_keys
from fastapi import APIRouter, Query, Request
from opentelemetry import trace

from serving.aerospike_clients import (
    batch_read_all_sets_official,
    batch_read_all_sets_py,
)
from serving.feature_extractor import extract_features
from serving.observability.metrics import (
    aerospike_batch_read_all_duration_seconds,
    aerospike_records_found_ratio,
    dlrm_inference_duration_seconds,
    feature_extraction_duration_seconds,
    key_extraction_duration_seconds,
    predict_active_requests,
    predict_duration_seconds,
    predict_requests_total,
    response_build_duration_seconds,
)
from serving.schemas import PredictResponse, PredictResult

router = APIRouter(prefix="/predict")
tracer = trace.get_tracer("serving.predict")
logger = logging.getLogger("serving")

_SAMPLE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "sample_request200real.json"
_sample_request: dict | None = None


def _get_sample_request() -> dict:
    global _sample_request
    if _sample_request is None:
        with open(_SAMPLE_PATH, encoding="utf-8") as f:
            _sample_request = json.load(f)
    return _sample_request  # type: ignore[return-value]


def _build_keys(
    keys_by_set: dict[str, list[str]],
    num_sets: int | None,
    batch_size: int | None,
) -> dict[str, list[tuple]]:
    """Build Aerospike key tuples from string keys, optionally trimmed."""
    if num_sets is not None:
        allowed = set(ALL_SETS[:num_sets])
        keys_by_set = {k: v for k, v in keys_by_set.items() if k in allowed}
    result: dict[str, list[tuple]] = {}
    for set_name, key_strings in keys_by_set.items():
        trimmed = key_strings[:batch_size] if batch_size else key_strings
        result[set_name] = [(get_namespace(), set_name, k) for k in trimmed]
    return result


# ---------------------------------------------------------------------------
# Common prediction pipeline
# ---------------------------------------------------------------------------


async def _predict_pipeline(
    request_data: dict,
    request: Request,
    client_type: str,
    mode: str = "gather",
    num_sets: int | None = None,
    batch_size: int | None = None,
    skip_inference: bool = False,
) -> PredictResponse:
    ct = client_type
    predict_active_requests.labels(client_type=ct).inc()
    try:
        return await _run_pipeline(request_data, request, ct, mode, num_sets, batch_size, skip_inference)
    except Exception:
        predict_requests_total.labels(client_type=ct, status="error").inc()
        raise
    finally:
        predict_active_requests.labels(client_type=ct).dec()


async def _run_pipeline(
    request_data: dict,
    request: Request,
    ct: str,
    mode: str,
    num_sets: int | None,
    batch_size: int | None,
    skip_inference: bool,
) -> PredictResponse:
    span_name = "official" if ct == "official" else "py_async"

    with tracer.start_as_current_span(
        f"predict.{span_name}.pipeline",
        attributes={"benchmark.client_type": ct},
    ) as root_span:
        t0 = time.perf_counter()

        # 1. Extract keys
        with tracer.start_as_current_span("predict.extract_keys"):
            t_key = time.perf_counter()
            raw_keys = extract_all_keys(request_data)
            keys_by_set = _build_keys(raw_keys, num_sets, batch_size)
            key_extraction_duration_seconds.labels(client_type=ct).observe(time.perf_counter() - t_key)

        total_keys = sum(len(v) for v in keys_by_set.values())
        root_span.set_attribute("benchmark.num_sets", len(keys_by_set))
        root_span.set_attribute("benchmark.total_keys", total_keys)

        # 2. Batch read
        with tracer.start_as_current_span(f"predict.{span_name}.aerospike_batch_read"):
            t_aero = time.perf_counter()
            if ct == "official":
                bins_by_set = await batch_read_all_sets_official(
                    request.app.state.official_client,
                    keys_by_set,
                    mode=mode,
                )
            else:
                bins_by_set = await batch_read_all_sets_py(
                    request.app.state.py_client,
                    keys_by_set,
                    mode=mode,
                )
            aerospike_s = time.perf_counter() - t_aero
            aerospike_batch_read_all_duration_seconds.labels(client_type=ct).observe(aerospike_s)

        # Count found records
        found = sum(1 for bins_list in bins_by_set.values() for b in bins_list if b)
        if total_keys > 0:
            aerospike_records_found_ratio.labels(client_type=ct).observe(found / total_keys)

        root_span.set_attribute("benchmark.aerospike_ms", round(aerospike_s * 1000, 2))
        root_span.set_attribute("benchmark.records_found", found)

        logger.info(
            "batch_read all sets completed",
            extra={
                "operation": "batch_read_all",
                "client_type": ct,
                "latency_ms": round(aerospike_s * 1000, 2),
                "num_sets": len(keys_by_set),
                "total_keys": total_keys,
                "found_count": found,
                "mode": mode,
            },
        )

        # 3 & 4. Feature extraction + Inference
        inference_ms = 0.0
        predictions: list[PredictResult] = []
        candidate_ads = request_data.get("candidateAds", [])

        if skip_inference:
            predictions = [PredictResult(adId=ad.get("adId", ""), score=0.0) for ad in candidate_ads]
        else:
            with tracer.start_as_current_span("predict.feature_extraction"):
                t_feat = time.perf_counter()
                sparse, dense = extract_features(bins_by_set)
                feature_extraction_duration_seconds.labels(client_type=ct).observe(time.perf_counter() - t_feat)

            with tracer.start_as_current_span("predict.dlrm_inference"):
                t_inf = time.perf_counter()
                with torch.no_grad():
                    scores = request.app.state.model(sparse, dense)
                inference_ms = (time.perf_counter() - t_inf) * 1000
                dlrm_inference_duration_seconds.labels(client_type=ct).observe(inference_ms / 1000)

            with tracer.start_as_current_span("predict.build_response"):
                t_resp = time.perf_counter()
                predictions = [
                    PredictResult(
                        adId=candidate_ads[i].get("adId", "") if i < len(candidate_ads) else "",
                        score=round(scores[i].item(), 6) if i < len(scores) else 0.0,
                    )
                    for i in range(len(scores))
                ]
                response_build_duration_seconds.labels(client_type=ct).observe(time.perf_counter() - t_resp)

        total_s = time.perf_counter() - t0
        predict_duration_seconds.labels(client_type=ct).observe(total_s)
        predict_requests_total.labels(client_type=ct, status="success").inc()

        root_span.set_attribute("benchmark.inference_ms", round(inference_ms, 2))
        root_span.set_attribute("benchmark.total_ms", round(total_s * 1000, 2))

        logger.info(
            "predict pipeline completed",
            extra={
                "operation": "predict_complete",
                "client_type": ct,
                "total_ms": round(total_s * 1000, 2),
                "aerospike_ms": round(aerospike_s * 1000, 2),
                "inference_ms": round(inference_ms, 2),
                "records_found": found,
                "records_total": total_keys,
            },
        )

        return PredictResponse(
            predictions=predictions,
            client_type=ct,
            aerospike_ms=round(aerospike_s * 1000, 2),
            inference_ms=round(inference_ms, 2),
            total_ms=round(total_s * 1000, 2),
            records_found=found,
            records_total=total_keys,
        )


# ---------------------------------------------------------------------------
# GET /sample endpoints (built-in sample data for load testing)
# ---------------------------------------------------------------------------


@router.get("/official/sample", response_model=PredictResponse)
async def predict_official_sample(
    request: Request,
    num_sets: int | None = Query(None, ge=1, le=9),
    batch_size: int | None = Query(None, ge=1, le=500),
    skip_inference: bool = Query(False),
    mode: str = Query("single", pattern="^(gather|sequential|single)$"),
) -> PredictResponse:
    return await _predict_pipeline(
        _get_sample_request(),
        request,
        "official",
        mode=mode,
        num_sets=num_sets,
        batch_size=batch_size,
        skip_inference=skip_inference,
    )


@router.get("/py-async/sample", response_model=PredictResponse)
async def predict_py_async_sample(
    request: Request,
    num_sets: int | None = Query(None, ge=1, le=9),
    batch_size: int | None = Query(None, ge=1, le=500),
    skip_inference: bool = Query(False),
    mode: str = Query("single", pattern="^(gather|sequential|single)$"),
) -> PredictResponse:
    return await _predict_pipeline(
        _get_sample_request(),
        request,
        "py-async",
        mode=mode,
        num_sets=num_sets,
        batch_size=batch_size,
        skip_inference=skip_inference,
    )
