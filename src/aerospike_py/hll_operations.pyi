"""Type stubs for hll_operations module.

Each function returns an ``Operation`` dict for use with
``client.operate()`` and ``client.operate_ordered()``.

Common ``policy`` flags (import from ``aerospike_py``):
    ``HLL_WRITE_DEFAULT``, ``HLL_WRITE_CREATE_ONLY``,
    ``HLL_WRITE_UPDATE_ONLY``, ``HLL_WRITE_NO_FAIL``,
    ``HLL_WRITE_ALLOW_FOLD``.
"""

from typing import Any, Optional

from aerospike_py._types import HLLPolicy, Operation

def hll_init(
    bin: str,
    index_bit_count: int,
    minhash_bit_count: Optional[int] = None,
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Create a new HLL or reset an existing HLL bin. (Write operation)

    Args:
        bin: Name of the HLL bin.
        index_bit_count: Number of index bits (4-16).
        minhash_bit_count: Number of min-hash bits (0 or 4-51). 0 disables min-hash.
        policy: Optional HLL write policy.
    """

def hll_add(
    bin: str,
    values: list[Any],
    index_bit_count: Optional[int] = None,
    minhash_bit_count: Optional[int] = None,
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Add values to an HLL bin. (Write operation)

    If the HLL bin does not exist, ``index_bit_count`` (and optionally
    ``minhash_bit_count``) are used to create it.

    Args:
        bin: Name of the HLL bin.
        values: List of values to add.
        index_bit_count: Number of index bits for auto-creation (None = use existing).
        minhash_bit_count: Number of min-hash bits for auto-creation (None = use existing).
        policy: Optional HLL write policy.
    """

def hll_get_count(bin: str) -> Operation:
    """Return the estimated element count of the HLL bin. (Read operation)"""

def hll_get_union(bin: str, values: list[Any]) -> Operation:
    """Return an HLL object that is the union of the bin with the given HLL list. (Read operation)

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
    """

def hll_get_union_count(bin: str, values: list[Any]) -> Operation:
    """Return the estimated count of the union. (Read operation)

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
    """

def hll_get_intersect_count(bin: str, values: list[Any]) -> Operation:
    """Return the estimated count of the intersection. (Read operation)

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to intersect with.
    """

def hll_get_similarity(bin: str, values: list[Any]) -> Operation:
    """Return the estimated similarity (Jaccard index). (Read operation)

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to compare with.
    """

def hll_describe(bin: str) -> Operation:
    """Return index_bit_count and minhash_bit_count as a list of two integers. (Read operation)"""

def hll_fold(bin: str, index_bit_count: int) -> Operation:
    """Fold the HLL bin to the specified index_bit_count. (Write operation)

    This can only be applied when minhash_bit_count is 0.

    Args:
        bin: Name of the HLL bin.
        index_bit_count: Target number of index bits.
    """

def hll_set_union(
    bin: str,
    values: list,
    *,
    policy: Optional[HLLPolicy] = None,
) -> Operation:
    """Set the union of the given HLL objects into the HLL bin. (Write operation)

    Args:
        bin: Name of the HLL bin.
        values: List of HLL bin values to union with.
        policy: Optional HLL write policy.
    """
