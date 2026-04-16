"""Convert Aerospike bin data into DLRM model input tensors."""

from __future__ import annotations

import contextlib

import torch

# Sparse field vocab sizes (must match model.DEFAULT_SPARSE_FIELD_DIMS)
_VOCAB_SIZES = [100_000, 50_000, 20_000, 10_000, 3]

_GENDER_MAP = {"M": 0, "F": 1, "U": 2}

# Numeric bin names to extract as dense features from Aerospike records.
# Order matters -- matches the model's dense input layout (indices 1-7).
_DENSE_BIN_NAMES = [
    "impCnt",
    "clkCnt",
    "convCnt",
    "spend",
    "ctr",
    "cvr",
    "roas",
]


def _hash_feature(value: str, vocab_size: int) -> int:
    """Hash a string feature value into a bounded integer index."""
    return hash(value) % vocab_size


def extract_features(
    bins_by_set: dict[str, list[dict]],
) -> tuple[torch.LongTensor, torch.FloatTensor]:
    """Build sparse + dense tensors from Aerospike batch-read results.

    Args:
        bins_by_set: Mapping of ``set_name`` to a list of bin dicts retrieved
            from Aerospike via ``batch_read``.  The primary source set is
            ``"nccsh_adid"``.

    Returns:
        A tuple of ``(sparse_features, dense_features)`` where:

        - ``sparse_features`` has shape ``[B, 5]`` (``torch.long``):
            0. adId hashed to 100k buckets
            1. adGroupId hashed to 50k buckets
            2. campaignId hashed to 20k buckets
            3. channelId hashed to 10k buckets
            4. Gender mapped to 0/1/2

        - ``dense_features`` has shape ``[B, 8]`` (``torch.float32``):
            0. Normalized age: ``(age - 25) / 15``
            1-7. impCnt, clkCnt, convCnt, spend, ctr, cvr, roas
    """
    records = bins_by_set.get("nccsh_adid", [])
    num_records = len(records)

    sparse = torch.zeros(num_records, 5, dtype=torch.long)
    dense = torch.zeros(num_records, 8, dtype=torch.float32)

    for i, bins in enumerate(records):
        # --- Sparse features ---
        ad_id = bins.get("adId", "")
        ad_group_id = bins.get("adGroupId", "")
        campaign_id = bins.get("campaignId", "")
        channel_id = bins.get("channelId", "")
        gender = bins.get("gender", "U")

        sparse[i, 0] = _hash_feature(str(ad_id), _VOCAB_SIZES[0])
        sparse[i, 1] = _hash_feature(str(ad_group_id), _VOCAB_SIZES[1])
        sparse[i, 2] = _hash_feature(str(campaign_id), _VOCAB_SIZES[2])
        sparse[i, 3] = _hash_feature(str(channel_id), _VOCAB_SIZES[3])
        sparse[i, 4] = _GENDER_MAP.get(str(gender), 2)

        # --- Dense features ---
        # Index 0: normalized age
        age = bins.get("age")
        if age is not None:
            with contextlib.suppress(ValueError, TypeError):
                dense[i, 0] = (float(age) - 25.0) / 15.0

        # Indices 1-7: numeric bins from Aerospike
        for j, bin_name in enumerate(_DENSE_BIN_NAMES):
            val = bins.get(bin_name)
            if val is not None:
                with contextlib.suppress(ValueError, TypeError):
                    dense[i, j + 1] = float(val)

    return sparse, dense
