"""Deterministic key generators for seed + request shaping."""

from __future__ import annotations

import random

from . import config


def seed_keys_for_set(set_name: str) -> list[tuple[str, str, str]]:
    """Keys to load at seed time: SEED_KEYS_PER_SET per FV set."""
    return [
        (config.AEROSPIKE_NAMESPACE, set_name, f"{set_name}_k{i}")
        for i in range(config.SEED_KEYS_PER_SET)
    ]


def request_keys(rng: random.Random) -> list[list[tuple[str, str, str]]]:
    """Per-request key matrix: ``NUM_FEATURE_VIEWS`` × ``KEYS_PER_FV`` keys.

    Each FV samples ``KEYS_PER_FV`` candidates from its set's seed range.
    Sampling is randomized per request to defeat any client-side caching.
    """
    matrix: list[list[tuple[str, str, str]]] = []
    for set_name in config.FV_SET_NAMES:
        indices = rng.sample(range(config.SEED_KEYS_PER_SET), config.KEYS_PER_FV)
        matrix.append(
            [
                (config.AEROSPIKE_NAMESPACE, set_name, f"{set_name}_k{i}")
                for i in indices
            ]
        )
    return matrix
