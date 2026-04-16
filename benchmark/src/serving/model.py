"""DLRM (Deep Learning Recommendation Model) for ad CTR prediction.

Reference: Naumov et al., "Deep Learning Recommendation Model for
Personalization and Recommendation Systems" (Meta/Facebook, 2019).
"""

from __future__ import annotations

import torch
import torch.nn as nn


def _build_mlp(
    in_dim: int,
    hidden_dims: list[int],
    dropout: float,
) -> nn.Sequential:
    """Build a Linear -> BatchNorm -> ReLU -> Dropout MLP stack."""
    layers: list[nn.Module] = []
    for out_dim in hidden_dims:
        layers.append(nn.Linear(in_dim, out_dim))
        layers.append(nn.BatchNorm1d(out_dim))
        layers.append(nn.ReLU())
        layers.append(nn.Dropout(dropout))
        in_dim = out_dim
    return nn.Sequential(*layers)


class DLRM(nn.Module):
    """Deep Learning Recommendation Model for CTR prediction.

    Architecture::

        Dense features  -> Bottom MLP -> dense_embedding (embed_dim)
        Sparse features -> Embedding lookup -> [embed_1, ..., embed_n]
        All embeddings (dense_embed + sparse_embeds) -> Pairwise dot-product interaction
        Interactions + dense_embed -> Top MLP -> Sigmoid

    Key difference from DeepFM:
        - DeepFM uses FM second-order interactions (sum^2 - sum_of_squares) + deep MLP.
        - DLRM computes explicit pairwise dot products between ALL embedding vectors
          (including the bottom MLP output), capturing richer feature interactions.
    """

    def __init__(
        self,
        sparse_field_dims: list[int],
        num_dense: int = 8,
        embed_dim: int = 16,
        bottom_mlp_dims: list[int] | None = None,
        top_mlp_dims: list[int] | None = None,
        dropout: float = 0.2,
    ):
        super().__init__()
        if bottom_mlp_dims is None:
            bottom_mlp_dims = [128, 64, 16]
        if top_mlp_dims is None:
            top_mlp_dims = [256, 128, 1]

        assert bottom_mlp_dims[-1] == embed_dim, (
            f"Last bottom MLP dim ({bottom_mlp_dims[-1]}) must equal embed_dim ({embed_dim})"
        )

        self.num_sparse_fields = len(sparse_field_dims)
        self.embed_dim = embed_dim

        # --- Sparse embeddings ---
        self.embeddings = nn.ModuleList([nn.Embedding(dim, embed_dim) for dim in sparse_field_dims])

        # --- Bottom MLP: dense features -> embed_dim ---
        self.bottom_mlp = _build_mlp(num_dense, bottom_mlp_dims, dropout)

        # --- Top MLP: interaction features -> logit ---
        # Number of vectors participating in interactions: num_sparse + 1 (dense)
        n = self.num_sparse_fields + 1
        # Upper triangle (excluding diagonal) has n*(n-1)/2 elements
        num_interaction_features = n * (n - 1) // 2
        # Top MLP input: interaction features + dense embedding (skip connection)
        top_mlp_input_dim = num_interaction_features + embed_dim
        top_layers: list[nn.Module] = []
        in_dim = top_mlp_input_dim
        for i, out_dim in enumerate(top_mlp_dims):
            top_layers.append(nn.Linear(in_dim, out_dim))
            # No BatchNorm/ReLU/Dropout after the final layer (output is 1-dim logit)
            if i < len(top_mlp_dims) - 1:
                top_layers.append(nn.BatchNorm1d(out_dim))
                top_layers.append(nn.ReLU())
                top_layers.append(nn.Dropout(dropout))
            in_dim = out_dim
        self.top_mlp = nn.Sequential(*top_layers)

        # Pre-compute the upper-triangle indices for interaction extraction
        self._triu_row, self._triu_col = torch.triu_indices(n, n, offset=1)

    def forward(self, sparse_features: torch.LongTensor, dense_features: torch.FloatTensor) -> torch.FloatTensor:
        """Forward pass.

        Args:
            sparse_features: ``[B, num_sparse_fields]`` integer indices.
            dense_features: ``[B, num_dense]`` float values.

        Returns:
            ``[B]`` CTR probabilities.
        """
        # --- Sparse embeddings: list of [B, embed_dim] ---
        sparse_embeds = [emb(sparse_features[:, i]) for i, emb in enumerate(self.embeddings)]

        # --- Bottom MLP: dense features -> [B, embed_dim] ---
        dense_embed = self.bottom_mlp(dense_features)  # [B, embed_dim]

        # --- Stack all embeddings: [B, N+1, embed_dim] ---
        all_embeds = torch.stack([dense_embed, *sparse_embeds], dim=1)

        # --- Pairwise dot-product interaction ---
        # [B, N+1, N+1]
        interaction_matrix = torch.bmm(all_embeds, all_embeds.transpose(1, 2))

        # Extract upper triangle (excluding diagonal): [B, n*(n-1)/2]
        interactions = interaction_matrix[:, self._triu_row, self._triu_col]

        # --- Concatenate interactions with dense embedding (skip connection) ---
        top_input = torch.cat([interactions, dense_embed], dim=1)

        # --- Top MLP -> logit ---
        logit = self.top_mlp(top_input)  # [B, 1]

        return torch.sigmoid(logit).squeeze(1)  # [B]


# Default model configuration for ad CTR prediction
DEFAULT_SPARSE_FIELD_DIMS = [100_000, 50_000, 20_000, 10_000, 3]
DEFAULT_NUM_DENSE = 8
DEFAULT_EMBED_DIM = 16


def create_model() -> DLRM:
    """Create and initialize the DLRM model with default config."""
    torch.manual_seed(42)
    model = DLRM(
        sparse_field_dims=DEFAULT_SPARSE_FIELD_DIMS,
        num_dense=DEFAULT_NUM_DENSE,
        embed_dim=DEFAULT_EMBED_DIM,
    )
    model.eval()

    # Warmup: run a dummy forward pass to trigger JIT/lazy initializations
    with torch.no_grad():
        dummy_sparse = torch.zeros(1, len(DEFAULT_SPARSE_FIELD_DIMS), dtype=torch.long)
        dummy_dense = torch.zeros(1, DEFAULT_NUM_DENSE, dtype=torch.float32)
        model(dummy_sparse, dummy_dense)

    return model
