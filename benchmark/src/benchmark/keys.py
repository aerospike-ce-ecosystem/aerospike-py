"""Key extraction from request JSON — mirrors the service-layer key construction."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.config import SET_KEY_FIELD, get_namespace

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_REQUEST_FILE = DATA_DIR / "sample_request200real.json"


def load_request(path: Path | str | None = None) -> dict:
    """Load a request payload from JSON.

    Accepts both ``{"request": {...}}`` envelope and flat structures.
    """
    resolved = Path(path) if path else DEFAULT_REQUEST_FILE
    with open(resolved, encoding="utf-8") as fh:
        raw = json.load(fh)
    if isinstance(raw, dict) and "request" in raw:
        return raw["request"]
    return raw


def extract_all_keys(request: dict) -> dict[str, list[str]]:
    """Derive per-set key strings from *request* candidate ads.

    Returns ``{set_name: [key_string, ...]}``.
    """
    channel_id = request["channelId"]
    bcookie = request.get("bcookie", "")
    candidates = request["candidateAds"]

    result: dict[str, list[str]] = {s: [] for s in SET_KEY_FIELD}

    for ad in candidates:
        ad_id = str(ad["adId"])
        adgroup_id = str(ad["adGroupId"])
        campaign_id = str(ad["campaignId"])
        nv_mid = str(ad["nvMid"])

        result["nccsh_adid"].append(ad_id)
        result["nccsh_adgroupid"].append(adgroup_id)
        result["nccsh_campaignid"].append(campaign_id)
        result["nccsh_adid_channelid"].append(f"{ad_id}_{channel_id}")
        result["nccsh_adgroupid_channelid"].append(f"{adgroup_id}_{channel_id}")
        result["nccsh_campaignid_channelid"].append(f"{campaign_id}_{channel_id}")
        result["nccsh_nvmid"].append(nv_mid)
        result["nccsh_hconvvalue_nvmid"].append(nv_mid)
        result["nccsh_userid"].append(str(bcookie))

    return result


def build_batch_keys(
    set_name: str,
    key_strings: list[str],
    batch_size: int,
) -> list[tuple[str, str, str]]:
    """Build ``(namespace, set, key)`` tuples truncated to *batch_size*."""
    ns = get_namespace()
    return [(ns, set_name, k) for k in key_strings[:batch_size]]
