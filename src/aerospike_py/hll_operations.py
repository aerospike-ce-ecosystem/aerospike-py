"""HyperLogLog CDT operation helpers.

Each function returns an operation dict for use with ``client.operate()``
and ``client.operate_ordered()``.
"""

from typing import Any, Optional

from aerospike_py._types import _UNSET, HLLPolicy, Operation, _build_op

__all__ = [
    "Operation",
    "hll_init",
    "hll_add",
    "hll_get_count",
    "hll_get_union",
    "hll_get_union_count",
    "hll_get_intersect_count",
    "hll_get_similarity",
    "hll_describe",
    "hll_fold",
    "hll_set_union",
]

# HLL operation codes (must match rust/src/constants.rs HLL CDT codes)
_OP_HLL_INIT = 3001
_OP_HLL_ADD = 3002
_OP_HLL_GET_COUNT = 3003
_OP_HLL_GET_UNION = 3004
_OP_HLL_GET_UNION_COUNT = 3005
_OP_HLL_GET_INTERSECT_COUNT = 3006
_OP_HLL_GET_SIMILARITY = 3007
_OP_HLL_DESCRIBE = 3008
_OP_HLL_FOLD = 3009
_OP_HLL_SET_UNION = 3010


def hll_init(
    bin: str,
    index_bit_count: int,
    minhash_bit_count: Optional[int] = None,
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Create a new HLL or reset an existing HLL bin.

    Args:
        bin: Name of the HLL bin.
        index_bit_count: Number of index bits (4-16).
        minhash_bit_count: Number of min-hash bits (0 or 4-51). 0 disables min-hash.
        policy: Optional HLL write policy.
    """
    return _build_op(
        _OP_HLL_INIT,
        bin,
        index_bit_count=index_bit_count,
        minhash_bit_count=minhash_bit_count if minhash_bit_count is not None else _UNSET,
        hll_policy=policy if policy is not None else _UNSET,
    )


def hll_add(
    bin: str,
    values: list[Any],
    index_bit_count: Optional[int] = None,
    minhash_bit_count: Optional[int] = None,
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Add values to an HLL bin.

    If the HLL bin does not exist, ``index_bit_count`` (and optionally
    ``minhash_bit_count``) are used to create it.

    Args:
        bin: Name of the HLL bin.
        values: List of values to add.
        index_bit_count: Number of index bits for auto-creation (None = use existing).
        minhash_bit_count: Number of min-hash bits for auto-creation (None = use existing).
        policy: Optional HLL write policy.
    """
    return _build_op(
        _OP_HLL_ADD,
        bin,
        val=values,
        index_bit_count=index_bit_count if index_bit_count is not None else _UNSET,
        minhash_bit_count=minhash_bit_count if minhash_bit_count is not None else _UNSET,
        hll_policy=policy if policy is not None else _UNSET,
    )


def hll_get_count(bin: str) -> Operation:
    """Return the estimated element count of the HLL bin."""
    return _build_op(_OP_HLL_GET_COUNT, bin)


def hll_get_union(bin: str, values: list[Any]) -> Operation:
    """Return an HLL object that is the union of the bin with the given HLL list.

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
    """
    return _build_op(_OP_HLL_GET_UNION, bin, val=values)


def hll_get_union_count(bin: str, values: list[Any]) -> Operation:
    """Return the estimated count of the union of the bin with the given HLL list.

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
    """
    return _build_op(_OP_HLL_GET_UNION_COUNT, bin, val=values)


def hll_get_intersect_count(bin: str, values: list[Any]) -> Operation:
    """Return the estimated count of the intersection of the bin with the given HLL list.

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to intersect with.
    """
    return _build_op(_OP_HLL_GET_INTERSECT_COUNT, bin, val=values)


def hll_get_similarity(bin: str, values: list[Any]) -> Operation:
    """Return the estimated similarity (Jaccard index) between the bin and the given HLL list.

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to compare with.
    """
    return _build_op(_OP_HLL_GET_SIMILARITY, bin, val=values)


def hll_describe(bin: str) -> Operation:
    """Return the index_bit_count and minhash_bit_count of the HLL bin as a list of two integers."""
    return _build_op(_OP_HLL_DESCRIBE, bin)


def hll_fold(bin: str, index_bit_count: int) -> Operation:
    """Fold the HLL bin to the specified index_bit_count.

    This can only be applied when minhash_bit_count is 0.

    Args:
        bin: Name of the HLL bin.
        index_bit_count: Target number of index bits (must be less than current).
    """
    return _build_op(_OP_HLL_FOLD, bin, index_bit_count=index_bit_count)


def hll_set_union(
    bin: str,
    values: list[Any],
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Set the union of the given HLL objects into the HLL bin.

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
        policy: Optional HLL write policy.
    """
    return _build_op(
        _OP_HLL_SET_UNION,
        bin,
        val=values,
        hll_policy=policy if policy is not None else _UNSET,
    )
