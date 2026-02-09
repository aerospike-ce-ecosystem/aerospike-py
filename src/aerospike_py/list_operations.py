"""List CDT operation helpers.

Each function returns an operation dict for use with ``client.operate()``
and ``client.operate_ordered()``.
"""

from typing import Any, Optional

# Type alias for operation dicts passed to client.operate()
Operation = dict[str, Any]

__all__ = [
    "Operation",
    "list_append",
    "list_append_items",
    "list_insert",
    "list_insert_items",
    "list_pop",
    "list_pop_range",
    "list_remove",
    "list_remove_range",
    "list_set",
    "list_trim",
    "list_clear",
    "list_size",
    "list_get",
    "list_get_range",
    "list_get_by_value",
    "list_get_by_index",
    "list_get_by_index_range",
    "list_get_by_rank",
    "list_get_by_rank_range",
    "list_get_by_value_list",
    "list_get_by_value_range",
    "list_remove_by_value",
    "list_remove_by_value_list",
    "list_remove_by_value_range",
    "list_remove_by_index",
    "list_remove_by_index_range",
    "list_remove_by_rank",
    "list_remove_by_rank_range",
    "list_increment",
    "list_sort",
    "list_set_order",
]

# List operation codes (must match rust/src/operations.rs CDT codes)
_OP_LIST_APPEND = 1001
_OP_LIST_APPEND_ITEMS = 1002
_OP_LIST_INSERT = 1003
_OP_LIST_INSERT_ITEMS = 1004
_OP_LIST_POP = 1005
_OP_LIST_POP_RANGE = 1006
_OP_LIST_REMOVE = 1007
_OP_LIST_REMOVE_RANGE = 1008
_OP_LIST_SET = 1009
_OP_LIST_TRIM = 1010
_OP_LIST_CLEAR = 1011
_OP_LIST_SIZE = 1012
_OP_LIST_GET = 1013
_OP_LIST_GET_RANGE = 1014
_OP_LIST_GET_BY_VALUE = 1015
_OP_LIST_GET_BY_INDEX = 1016
_OP_LIST_GET_BY_INDEX_RANGE = 1017
_OP_LIST_GET_BY_RANK = 1018
_OP_LIST_GET_BY_RANK_RANGE = 1019
_OP_LIST_GET_BY_VALUE_LIST = 1020
_OP_LIST_GET_BY_VALUE_RANGE = 1021
_OP_LIST_REMOVE_BY_VALUE = 1022
_OP_LIST_REMOVE_BY_VALUE_LIST = 1023
_OP_LIST_REMOVE_BY_VALUE_RANGE = 1024
_OP_LIST_REMOVE_BY_INDEX = 1025
_OP_LIST_REMOVE_BY_INDEX_RANGE = 1026
_OP_LIST_REMOVE_BY_RANK = 1027
_OP_LIST_REMOVE_BY_RANK_RANGE = 1028
_OP_LIST_INCREMENT = 1029
_OP_LIST_SORT = 1030
_OP_LIST_SET_ORDER = 1031


def list_append(bin: str, val: Any, policy: Optional[Operation] = None) -> Operation:
    """Append a value to a list bin."""
    op = {"op": _OP_LIST_APPEND, "bin": bin, "val": val}
    if policy:
        op["list_policy"] = policy
    return op


def list_append_items(
    bin: str, values: list[Any], policy: Optional[Operation] = None
) -> Operation:
    """Append multiple values to a list bin."""
    op = {"op": _OP_LIST_APPEND_ITEMS, "bin": bin, "val": values}
    if policy:
        op["list_policy"] = policy
    return op


def list_insert(
    bin: str, index: int, val: Any, policy: Optional[Operation] = None
) -> Operation:
    """Insert a value at the given index."""
    op = {"op": _OP_LIST_INSERT, "bin": bin, "index": index, "val": val}
    if policy:
        op["list_policy"] = policy
    return op


def list_insert_items(
    bin: str, index: int, values: list[Any], policy: Optional[Operation] = None
) -> Operation:
    """Insert multiple values at the given index."""
    op = {"op": _OP_LIST_INSERT_ITEMS, "bin": bin, "index": index, "val": values}
    if policy:
        op["list_policy"] = policy
    return op


def list_pop(bin: str, index: int) -> Operation:
    """Remove and return the item at the given index."""
    return {"op": _OP_LIST_POP, "bin": bin, "index": index}


def list_pop_range(bin: str, index: int, count: int) -> Operation:
    """Remove and return `count` items starting at `index`."""
    return {"op": _OP_LIST_POP_RANGE, "bin": bin, "index": index, "count": count}


def list_remove(bin: str, index: int) -> Operation:
    """Remove the item at the given index."""
    return {"op": _OP_LIST_REMOVE, "bin": bin, "index": index}


def list_remove_range(bin: str, index: int, count: int) -> Operation:
    """Remove `count` items starting at `index`."""
    return {"op": _OP_LIST_REMOVE_RANGE, "bin": bin, "index": index, "count": count}


def list_set(bin: str, index: int, val: Any) -> Operation:
    """Set the value at the given index."""
    return {"op": _OP_LIST_SET, "bin": bin, "index": index, "val": val}


def list_trim(bin: str, index: int, count: int) -> Operation:
    """Remove items outside the specified range."""
    return {"op": _OP_LIST_TRIM, "bin": bin, "index": index, "count": count}


def list_clear(bin: str) -> Operation:
    """Remove all items from a list bin."""
    return {"op": _OP_LIST_CLEAR, "bin": bin}


def list_size(bin: str) -> Operation:
    """Return the number of items in a list bin."""
    return {"op": _OP_LIST_SIZE, "bin": bin}


def list_get(bin: str, index: int) -> Operation:
    """Get the item at the given index."""
    return {"op": _OP_LIST_GET, "bin": bin, "index": index}


def list_get_range(bin: str, index: int, count: int) -> Operation:
    """Get `count` items starting at `index`."""
    return {"op": _OP_LIST_GET_RANGE, "bin": bin, "index": index, "count": count}


def list_get_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Get items matching the given value."""
    return {
        "op": _OP_LIST_GET_BY_VALUE,
        "bin": bin,
        "val": val,
        "return_type": return_type,
    }


def list_get_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Get item by index with the specified return type."""
    return {
        "op": _OP_LIST_GET_BY_INDEX,
        "bin": bin,
        "index": index,
        "return_type": return_type,
    }


def list_get_by_index_range(
    bin: str, index: int, return_type: int, count: Optional[int] = None
) -> Operation:
    """Get items by index range with the specified return type."""
    op = {
        "op": _OP_LIST_GET_BY_INDEX_RANGE,
        "bin": bin,
        "index": index,
        "return_type": return_type,
    }
    if count is not None:
        op["count"] = count
    return op


def list_get_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Get item by rank with the specified return type."""
    return {
        "op": _OP_LIST_GET_BY_RANK,
        "bin": bin,
        "rank": rank,
        "return_type": return_type,
    }


def list_get_by_rank_range(
    bin: str, rank: int, return_type: int, count: Optional[int] = None
) -> Operation:
    """Get items by rank range with the specified return type."""
    op = {
        "op": _OP_LIST_GET_BY_RANK_RANGE,
        "bin": bin,
        "rank": rank,
        "return_type": return_type,
    }
    if count is not None:
        op["count"] = count
    return op


def list_get_by_value_list(bin: str, values: list[Any], return_type: int) -> Operation:
    """Get items matching any of the given values."""
    return {
        "op": _OP_LIST_GET_BY_VALUE_LIST,
        "bin": bin,
        "val": values,
        "return_type": return_type,
    }


def list_get_by_value_range(
    bin: str, begin: Any, end: Any, return_type: int
) -> Operation:
    """Get items with values in the range [begin, end)."""
    return {
        "op": _OP_LIST_GET_BY_VALUE_RANGE,
        "bin": bin,
        "val": begin,
        "val_end": end,
        "return_type": return_type,
    }


def list_remove_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Remove items matching the given value."""
    return {
        "op": _OP_LIST_REMOVE_BY_VALUE,
        "bin": bin,
        "val": val,
        "return_type": return_type,
    }


def list_remove_by_value_list(
    bin: str, values: list[Any], return_type: int
) -> Operation:
    """Remove items matching any of the given values."""
    return {
        "op": _OP_LIST_REMOVE_BY_VALUE_LIST,
        "bin": bin,
        "val": values,
        "return_type": return_type,
    }


def list_remove_by_value_range(
    bin: str, begin: Any, end: Any, return_type: int
) -> Operation:
    """Remove items with values in the range [begin, end)."""
    return {
        "op": _OP_LIST_REMOVE_BY_VALUE_RANGE,
        "bin": bin,
        "val": begin,
        "val_end": end,
        "return_type": return_type,
    }


def list_remove_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Remove item by index with the specified return type."""
    return {
        "op": _OP_LIST_REMOVE_BY_INDEX,
        "bin": bin,
        "index": index,
        "return_type": return_type,
    }


def list_remove_by_index_range(
    bin: str, index: int, return_type: int, count: Optional[int] = None
) -> Operation:
    """Remove items by index range."""
    op = {
        "op": _OP_LIST_REMOVE_BY_INDEX_RANGE,
        "bin": bin,
        "index": index,
        "return_type": return_type,
    }
    if count is not None:
        op["count"] = count
    return op


def list_remove_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Remove item by rank."""
    return {
        "op": _OP_LIST_REMOVE_BY_RANK,
        "bin": bin,
        "rank": rank,
        "return_type": return_type,
    }


def list_remove_by_rank_range(
    bin: str, rank: int, return_type: int, count: Optional[int] = None
) -> Operation:
    """Remove items by rank range."""
    op = {
        "op": _OP_LIST_REMOVE_BY_RANK_RANGE,
        "bin": bin,
        "rank": rank,
        "return_type": return_type,
    }
    if count is not None:
        op["count"] = count
    return op


def list_increment(
    bin: str, index: int, val: int, policy: Optional[Operation] = None
) -> Operation:
    """Increment the value at the given index."""
    op = {"op": _OP_LIST_INCREMENT, "bin": bin, "index": index, "val": val}
    if policy:
        op["list_policy"] = policy
    return op


def list_sort(bin: str, sort_flags: int = 0) -> Operation:
    """Sort the list."""
    return {"op": _OP_LIST_SORT, "bin": bin, "val": sort_flags}


def list_set_order(bin: str, list_order: int = 0) -> Operation:
    """Set the list order."""
    return {"op": _OP_LIST_SET_ORDER, "bin": bin, "val": list_order}
