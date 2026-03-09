"""Shared type aliases for aerospike_py."""

from typing import Any, TypedDict

__all__ = ["Operation", "ListPolicy", "MapPolicy", "HLLPolicy"]

Operation = dict[str, Any]
"""Operation dict for use with ``client.operate()`` and ``client.operate_ordered()``.

Required keys:
    ``op`` (int): Operation code — ``OPERATOR_READ``, ``OPERATOR_WRITE``,
        ``OPERATOR_INCR``, ``OPERATOR_APPEND``, ``OPERATOR_PREPEND``,
        ``OPERATOR_TOUCH``, ``OPERATOR_DELETE``, or CDT codes (1000+).
    ``bin`` (str): Bin name to operate on.
    ``val`` (Any): Value for write operations; ``None`` for read ops.

Optional keys (CDT operations):
    ``return_type`` (int): ``LIST_RETURN_*`` or ``MAP_RETURN_*`` constant.
    ``list_policy`` (ListPolicy): Policy for list CDT operations.
    ``map_policy`` (MapPolicy): Policy for map CDT operations.
    ``hll_policy`` (HLLPolicy): Policy for HyperLogLog CDT operations.
    ``bit_policy`` (int): Bit write flags for bitwise CDT operations (``BIT_WRITE_*``).
    ``bit_offset`` (int): Starting bit position for bitwise CDT operations.
    ``bit_size`` (int): Number of bits for bitwise CDT operations.

Use ``aerospike_py.list_operations``, ``aerospike_py.map_operations``,
``aerospike_py.hll_operations``, or ``aerospike_py.bit_operations`` helper modules
to build CDT operation dicts.
"""


class ListPolicy(TypedDict, total=False):
    """Policy for list CDT operations.

    Keys:
        order: List ordering (LIST_UNORDERED or LIST_ORDERED).
        flags: List write flags (LIST_WRITE_DEFAULT, LIST_WRITE_ADD_UNIQUE, etc.).
    """

    order: int
    flags: int


class MapPolicy(TypedDict, total=False):
    """Policy for map CDT operations.

    Keys:
        order: Map ordering (MAP_UNORDERED, MAP_KEY_ORDERED, MAP_KEY_VALUE_ORDERED).
        write_mode: Map write mode (MAP_UPDATE, MAP_UPDATE_ONLY, MAP_CREATE_ONLY).
    """

    order: int
    write_mode: int


class HLLPolicy(TypedDict, total=False):
    """Policy for HyperLogLog CDT operations.

    Keys:
        flags: HLL write flags (HLL_WRITE_DEFAULT, HLL_WRITE_CREATE_ONLY, etc.).
    """

    flags: int


_UNSET: Any = object()
"""Sentinel for unset optional parameters in CDT operations."""


def _build_op(op_code: int, bin: str, /, **kwargs: Any) -> Operation:
    """Build an operation dict, omitting keys whose value is ``_UNSET``."""
    result: Operation = {"op": op_code, "bin": bin}
    for key, value in kwargs.items():
        if value is not _UNSET:
            result[key] = value
    return result
