"""Type stubs for list_operations module.

Each function returns an ``Operation`` dict for use with
``client.operate()`` and ``client.operate_ordered()``.

Common ``return_type`` constants (import from ``aerospike_py``):
    ``LIST_RETURN_NONE``, ``LIST_RETURN_INDEX``, ``LIST_RETURN_REVERSE_INDEX``,
    ``LIST_RETURN_RANK``, ``LIST_RETURN_REVERSE_RANK``, ``LIST_RETURN_COUNT``,
    ``LIST_RETURN_VALUE``, ``LIST_RETURN_EXISTS``.
"""

from typing import Any, Optional

from aerospike_py._types import ListPolicy, Operation

def list_append(bin: str, val: Any, policy: Optional[ListPolicy] = None) -> Operation:
    """Append *val* to the end of the list bin. (Write operation)

    Args:
        bin: Name of the list bin.
        val: Value to append.
        policy: Optional list policy (order, write flags).
    """

def list_append_items(bin: str, values: list, policy: Optional[ListPolicy] = None) -> Operation:
    """Append multiple *values* to the end of the list bin. (Write operation)

    Args:
        bin: Name of the list bin.
        values: List of values to append.
        policy: Optional list policy (order, write flags).
    """

def list_insert(bin: str, index: int, val: Any, policy: Optional[ListPolicy] = None) -> Operation:
    """Insert *val* at the given *index* in the list bin. (Write operation)

    Args:
        bin: Name of the list bin.
        index: Position at which to insert (0-based, negative indices supported).
        val: Value to insert.
        policy: Optional list policy (order, write flags).
    """

def list_insert_items(
    bin: str,
    index: int,
    values: list,
    policy: Optional[ListPolicy] = None,
) -> Operation:
    """Insert multiple *values* starting at *index*. (Write operation)

    Args:
        bin: Name of the list bin.
        index: Position at which to insert.
        values: List of values to insert.
        policy: Optional list policy (order, write flags).
    """

def list_pop(bin: str, index: int) -> Operation:
    """Remove and return the item at *index*. (Write operation)"""

def list_pop_range(bin: str, index: int, count: int) -> Operation:
    """Remove and return *count* items starting at *index*. (Write operation)"""

def list_remove(bin: str, index: int) -> Operation:
    """Remove the item at *index* without returning it. (Write operation)"""

def list_remove_range(bin: str, index: int, count: int) -> Operation:
    """Remove *count* items starting at *index*. (Write operation)"""

def list_set(bin: str, index: int, val: Any) -> Operation:
    """Overwrite the value at *index* with *val*. (Write operation)"""

def list_trim(bin: str, index: int, count: int) -> Operation:
    """Remove all items outside the range [index, index+count). (Write operation)"""

def list_clear(bin: str) -> Operation:
    """Remove all items from the list bin. (Write operation)"""

def list_size(bin: str) -> Operation:
    """Return the number of items in the list bin. (Read operation)"""

def list_get(bin: str, index: int) -> Operation:
    """Return the item at *index*. (Read operation)"""

def list_get_range(bin: str, index: int, count: int) -> Operation:
    """Return *count* items starting at *index*. (Read operation)"""

def list_get_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Return items matching *val*, shaped by *return_type*. (Read operation)

    Args:
        bin: Name of the list bin.
        val: Value to match.
        return_type: One of ``LIST_RETURN_*`` constants (e.g. ``LIST_RETURN_INDEX``).
    """

def list_get_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Return the item at *index*, shaped by *return_type*. (Read operation)

    Args:
        bin: Name of the list bin.
        index: List index (0-based, negative indices supported).
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_get_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Return items starting at *index*, shaped by *return_type*. (Read operation)

    Args:
        bin: Name of the list bin.
        index: Starting index.
        return_type: One of ``LIST_RETURN_*`` constants.
        count: Number of items. If ``None``, returns all items from *index* onward.
    """

def list_get_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Return the item at the given *rank* (sorted order). (Read operation)

    Args:
        bin: Name of the list bin.
        rank: Rank position (0 = smallest, -1 = largest).
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_get_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Return items starting at *rank* in sorted order. (Read operation)

    Args:
        bin: Name of the list bin.
        rank: Starting rank.
        return_type: One of ``LIST_RETURN_*`` constants.
        count: Number of items. If ``None``, returns all items from *rank* onward.
    """

def list_get_by_value_list(bin: str, values: list, return_type: int) -> Operation:
    """Return items matching any value in *values*. (Read operation)

    Args:
        bin: Name of the list bin.
        values: List of values to match.
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_get_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Return items with values in [begin, end). (Read operation)

    Args:
        bin: Name of the list bin.
        begin: Inclusive lower bound.
        end: Exclusive upper bound.
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Remove items matching *val* and return results per *return_type*. (Write operation)

    Args:
        bin: Name of the list bin.
        val: Value to match and remove.
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_value_list(bin: str, values: list, return_type: int) -> Operation:
    """Remove items matching any value in *values*. (Write operation)

    Args:
        bin: Name of the list bin.
        values: List of values to match and remove.
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Remove items with values in [begin, end). (Write operation)

    Args:
        bin: Name of the list bin.
        begin: Inclusive lower bound.
        end: Exclusive upper bound.
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Remove the item at *index* and return result per *return_type*. (Write operation)

    Args:
        bin: Name of the list bin.
        index: List index (0-based).
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove items starting at *index*. (Write operation)

    Args:
        bin: Name of the list bin.
        index: Starting index.
        return_type: One of ``LIST_RETURN_*`` constants.
        count: Number of items. If ``None``, removes all from *index* onward.
    """

def list_remove_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Remove the item at *rank* in sorted order. (Write operation)

    Args:
        bin: Name of the list bin.
        rank: Rank position (0 = smallest).
        return_type: One of ``LIST_RETURN_*`` constants.
    """

def list_remove_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove items starting at *rank* in sorted order. (Write operation)

    Args:
        bin: Name of the list bin.
        rank: Starting rank.
        return_type: One of ``LIST_RETURN_*`` constants.
        count: Number of items. If ``None``, removes all from *rank* onward.
    """

def list_increment(bin: str, index: int, val: int, policy: Optional[ListPolicy] = None) -> Operation:
    """Increment the numeric value at *index* by *val*. (Write operation)

    Args:
        bin: Name of the list bin.
        index: Index of the element to increment.
        val: Amount to add (may be negative).
        policy: Optional list policy.
    """

def list_sort(bin: str, sort_flags: int = 0) -> Operation:
    """Sort the list bin in place. (Write operation)

    Args:
        bin: Name of the list bin.
        sort_flags: ``LIST_SORT_DEFAULT`` or ``LIST_SORT_DROP_DUPLICATES``.
    """

def list_set_order(bin: str, list_order: int = 0) -> Operation:
    """Set the ordering type of the list bin. (Write operation)

    Args:
        bin: Name of the list bin.
        list_order: ``LIST_UNORDERED`` or ``LIST_ORDERED``.
    """
