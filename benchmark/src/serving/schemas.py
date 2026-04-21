"""Pydantic request / response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateAd(BaseModel):
    adId: str
    adGroupId: str
    campaignId: str
    channelId: str = ""


class PredictRequest(BaseModel):
    candidateAds: list[CandidateAd]
    userId: str = ""
    nvmid: str = ""
    gender: str = "U"
    age: int = 30


class PredictResult(BaseModel):
    adId: str
    score: float


class PredictResponse(BaseModel):
    predictions: list[PredictResult]
    client_type: str
    aerospike_ms: float = Field(description="Total Aerospike batch_read time (ms)")
    inference_ms: float = Field(description="DLRM inference time (ms)")
    total_ms: float = Field(description="Total pipeline time (ms)")
    records_found: int = 0
    records_total: int = 0
