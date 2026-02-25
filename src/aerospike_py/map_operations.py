"""Map CDT operation helpers.

Each function returns an operation dict for use with ``client.operate()``
and ``client.operate_ordered()``.
"""

from typing import Any, Optional

from aerospike_py._types import MapPolicy, Operation

__all__ = [
    "Operation",
    "map_set_order",
    "map_put",
    "map_put_items",
    "map_increment",
    "map_decrement",
    "map_clear",
    "map_remove_by_key",
    "map_remove_by_key_list",
    "map_remove_by_key_range",
    "map_remove_by_value",
    "map_remove_by_value_list",
    "map_remove_by_value_range",
    "map_remove_by_index",
    "map_remove_by_index_range",
    "map_remove_by_rank",
    "map_remove_by_rank_range",
    "map_size",
    "map_get_by_key",
    "map_get_by_key_range",
    "map_get_by_value",
    "map_get_by_value_range",
    "map_get_by_index",
    "map_get_by_index_range",
    "map_get_by_rank",
    "map_get_by_rank_range",
    "map_get_by_key_list",
    "map_get_by_value_list",
]

# Map operation codes (must match rust/src/operations.rs CDT codes)
_OP_MAP_SET_ORDER = 2001
_OP_MAP_PUT = 2002
_OP_MAP_PUT_ITEMS = 2003
_OP_MAP_INCREMENT = 2004
_OP_MAP_DECREMENT = 2005
_OP_MAP_CLEAR = 2006
_OP_MAP_REMOVE_BY_KEY = 2007
_OP_MAP_REMOVE_BY_KEY_LIST = 2008
_OP_MAP_REMOVE_BY_KEY_RANGE = 2009
_OP_MAP_REMOVE_BY_VALUE = 2010
_OP_MAP_REMOVE_BY_VALUE_LIST = 2011
_OP_MAP_REMOVE_BY_VALUE_RANGE = 2012
_OP_MAP_REMOVE_BY_INDEX = 2013
_OP_MAP_REMOVE_BY_INDEX_RANGE = 2014
_OP_MAP_REMOVE_BY_RANK = 2015
_OP_MAP_REMOVE_BY_RANK_RANGE = 2016
_OP_MAP_SIZE = 2017
_OP_MAP_GET_BY_KEY = 2018
_OP_MAP_GET_BY_KEY_RANGE = 2019
_OP_MAP_GET_BY_VALUE = 2020
_OP_MAP_GET_BY_VALUE_RANGE = 2021
_OP_MAP_GET_BY_INDEX = 2022
_OP_MAP_GET_BY_INDEX_RANGE = 2023
_OP_MAP_GET_BY_RANK = 2024
_OP_MAP_GET_BY_RANK_RANGE = 2025
_OP_MAP_GET_BY_KEY_LIST = 2026
_OP_MAP_GET_BY_VALUE_LIST = 2027

# Sentinel for distinguishing "not provided" from an explicit None value.
_UNSET: Any = object()


def _build_op(op_code: int, bin: str, /, **kwargs: Any) -> Operation:
    """Build an operation dict, omitting keys whose value is ``_UNSET``."""
    result: Operation = {"op": op_code, "bin": bin}
    for key, value in kwargs.items():
        if value is not _UNSET:
            result[key] = value
    return result


def map_set_order(bin: str, map_order: int) -> Operation:
    """Set the map ordering."""
    return _build_op(_OP_MAP_SET_ORDER, bin, val=map_order)


def map_put(bin: str, key: Any, val: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Put a key/value pair into a map bin."""
    return _build_op(_OP_MAP_PUT, bin, map_key=key, val=val, map_policy=policy or _UNSET)


def map_put_items(bin: str, items: dict[str, Any], policy: Optional[MapPolicy] = None) -> Operation:
    """Put multiple key/value pairs into a map bin."""
    return _build_op(_OP_MAP_PUT_ITEMS, bin, val=items, map_policy=policy or _UNSET)


def map_increment(bin: str, key: Any, incr: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Increment a value in a map by key."""
    return _build_op(_OP_MAP_INCREMENT, bin, map_key=key, val=incr, map_policy=policy or _UNSET)


def map_decrement(bin: str, key: Any, decr: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Decrement a value in a map by key."""
    return _build_op(_OP_MAP_DECREMENT, bin, map_key=key, val=decr, map_policy=policy or _UNSET)


def map_clear(bin: str) -> Operation:
    """Remove all items from a map bin."""
    return _build_op(_OP_MAP_CLEAR, bin)


def map_remove_by_key(bin: str, key: Any, return_type: int) -> Operation:
    """Remove item by key."""
    return _build_op(_OP_MAP_REMOVE_BY_KEY, bin, map_key=key, return_type=return_type)


def map_remove_by_key_list(bin: str, keys: list[Any], return_type: int) -> Operation:
    """Remove items by key list."""
    return _build_op(_OP_MAP_REMOVE_BY_KEY_LIST, bin, val=keys, return_type=return_type)


def map_remove_by_key_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Remove items with keys in the range [begin, end)."""
    return _build_op(_OP_MAP_REMOVE_BY_KEY_RANGE, bin, val=begin, val_end=end, return_type=return_type)


def map_remove_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Remove items by value."""
    return _build_op(_OP_MAP_REMOVE_BY_VALUE, bin, val=val, return_type=return_type)


def map_remove_by_value_list(bin: str, values: list[Any], return_type: int) -> Operation:
    """Remove items matching any of the given values."""
    return _build_op(_OP_MAP_REMOVE_BY_VALUE_LIST, bin, val=values, return_type=return_type)


def map_remove_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Remove items with values in the range [begin, end)."""
    return _build_op(_OP_MAP_REMOVE_BY_VALUE_RANGE, bin, val=begin, val_end=end, return_type=return_type)


def map_remove_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Remove item by index."""
    return _build_op(_OP_MAP_REMOVE_BY_INDEX, bin, index=index, return_type=return_type)


def map_remove_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove items by index range."""
    return _build_op(
        _OP_MAP_REMOVE_BY_INDEX_RANGE,
        bin,
        index=index,
        return_type=return_type,
        count=count if count is not None else _UNSET,
    )


def map_remove_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Remove item by rank."""
    return _build_op(_OP_MAP_REMOVE_BY_RANK, bin, rank=rank, return_type=return_type)


def map_remove_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove items by rank range."""
    return _build_op(
        _OP_MAP_REMOVE_BY_RANK_RANGE,
        bin,
        rank=rank,
        return_type=return_type,
        count=count if count is not None else _UNSET,
    )


def map_size(bin: str) -> Operation:
    """Return the number of items in a map bin."""
    return _build_op(_OP_MAP_SIZE, bin)


def map_get_by_key(bin: str, key: Any, return_type: int) -> Operation:
    """Get item by key."""
    return _build_op(_OP_MAP_GET_BY_KEY, bin, map_key=key, return_type=return_type)


def map_get_by_key_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Get items with keys in the range [begin, end)."""
    return _build_op(_OP_MAP_GET_BY_KEY_RANGE, bin, val=begin, val_end=end, return_type=return_type)


def map_get_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Get items by value."""
    return _build_op(_OP_MAP_GET_BY_VALUE, bin, val=val, return_type=return_type)


def map_get_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Get items with values in the range [begin, end)."""
    return _build_op(_OP_MAP_GET_BY_VALUE_RANGE, bin, val=begin, val_end=end, return_type=return_type)


def map_get_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Get item by index."""
    return _build_op(_OP_MAP_GET_BY_INDEX, bin, index=index, return_type=return_type)


def map_get_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Get items by index range."""
    return _build_op(
        _OP_MAP_GET_BY_INDEX_RANGE,
        bin,
        index=index,
        return_type=return_type,
        count=count if count is not None else _UNSET,
    )


def map_get_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Get item by rank."""
    return _build_op(_OP_MAP_GET_BY_RANK, bin, rank=rank, return_type=return_type)


def map_get_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Get items by rank range."""
    return _build_op(
        _OP_MAP_GET_BY_RANK_RANGE,
        bin,
        rank=rank,
        return_type=return_type,
        count=count if count is not None else _UNSET,
    )


def map_get_by_key_list(bin: str, keys: list[Any], return_type: int) -> Operation:
    """Get items matching any of the given keys."""
    return _build_op(_OP_MAP_GET_BY_KEY_LIST, bin, val=keys, return_type=return_type)


def map_get_by_value_list(bin: str, values: list[Any], return_type: int) -> Operation:
    """Get items matching any of the given values."""
    return _build_op(_OP_MAP_GET_BY_VALUE_LIST, bin, val=values, return_type=return_type)
