"""Shared type aliases for aerospike_py."""

from typing import Any, TypedDict

__all__ = ["Operation", "ListPolicy", "MapPolicy"]

Operation = dict[str, Any]
"""Operation dict with 'op', 'bin', 'val' keys, for use with client.operate()."""


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


_UNSET: Any = object()
"""Sentinel for unset optional parameters in CDT operations."""


def _build_op(op_code: int, bin: str, /, **kwargs: Any) -> Operation:
    """Build an operation dict, omitting keys whose value is ``_UNSET``."""
    result: Operation = {"op": op_code, "bin": bin}
    for key, value in kwargs.items():
        if value is not _UNSET:
            result[key] = value
    return result
