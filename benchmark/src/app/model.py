"""Tiny DLRM-shaped MLP used by S2/S3/S5.

Two linear layers + ReLU. Deterministic init so warm-up output matches
measurement output. Dimensions kept modest so torch doesn't drown out the
batch_read+materialise cost we're trying to compare.
"""

from __future__ import annotations

import torch

N_FEATURES = 64
HIDDEN = 256

FEATURE_NAMES: list[str] = [f"f{i}" for i in range(N_FEATURES)]

_rng = torch.Generator().manual_seed(42)
_W1 = torch.randn(N_FEATURES, HIDDEN, generator=_rng) * 0.05
_B1 = torch.zeros(HIDDEN)
_W2 = torch.randn(HIDDEN, 1, generator=_rng) * 0.05
_B2 = torch.zeros(1)


def infer(matrix: torch.Tensor) -> torch.Tensor:
    h = torch.relu(torch.matmul(matrix, _W1) + _B1)
    return torch.matmul(h, _W2) + _B2
