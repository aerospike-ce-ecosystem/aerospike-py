"""Type stubs for map_operations module.

Each function returns an ``Operation`` dict for use with
``client.operate()`` and ``client.operate_ordered()``.

Common ``return_type`` constants (import from ``aerospike_py``):
    ``MAP_RETURN_NONE``, ``MAP_RETURN_INDEX``, ``MAP_RETURN_REVERSE_INDEX``,
    ``MAP_RETURN_RANK``, ``MAP_RETURN_REVERSE_RANK``, ``MAP_RETURN_COUNT``,
    ``MAP_RETURN_KEY``, ``MAP_RETURN_VALUE``, ``MAP_RETURN_KEY_VALUE``,
    ``MAP_RETURN_EXISTS``.
"""

from typing import Any, Optional

from aerospike_py._types import MapPolicy, Operation

def map_set_order(bin: str, map_order: int) -> Operation:
    """Set the ordering type of the map bin. (Write operation)

    Args:
        bin: Name of the map bin.
        map_order: ``MAP_UNORDERED``, ``MAP_KEY_ORDERED``, or
            ``MAP_KEY_VALUE_ORDERED``.
    """

def map_put(bin: str, key: Any, val: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Put a single key/value pair into the map bin. (Write operation)

    Args:
        bin: Name of the map bin.
        key: Map entry key.
        val: Map entry value.
        policy: Optional map policy (order, write mode).
    """

def map_put_items(bin: str, items: dict, policy: Optional[MapPolicy] = None) -> Operation:
    """Put multiple key/value pairs into the map bin. (Write operation)

    Args:
        bin: Name of the map bin.
        items: Dictionary of entries to insert.
        policy: Optional map policy (order, write mode).
    """

def map_increment(bin: str, key: Any, incr: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Increment the numeric value of *key* by *incr*. (Write operation)

    Args:
        bin: Name of the map bin.
        key: Map entry key whose value will be incremented.
        incr: Amount to add (may be negative).
        policy: Optional map policy.
    """

def map_decrement(bin: str, key: Any, decr: Any, policy: Optional[MapPolicy] = None) -> Operation:
    """Decrement the numeric value of *key* by *decr*. (Write operation)

    Args:
        bin: Name of the map bin.
        key: Map entry key whose value will be decremented.
        decr: Amount to subtract.
        policy: Optional map policy.
    """

def map_clear(bin: str) -> Operation:
    """Remove all entries from the map bin. (Write operation)"""

def map_remove_by_key(bin: str, key: Any, return_type: int) -> Operation:
    """Remove the entry with *key* and return result per *return_type*. (Write operation)

    Args:
        bin: Name of the map bin.
        key: Key of the entry to remove.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_key_list(bin: str, keys: list, return_type: int) -> Operation:
    """Remove entries matching any key in *keys*. (Write operation)

    Args:
        bin: Name of the map bin.
        keys: List of keys to remove.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_key_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Remove entries with keys in [begin, end). (Write operation)

    Args:
        bin: Name of the map bin.
        begin: Inclusive lower bound key.
        end: Exclusive upper bound key.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Remove entries matching *val*. (Write operation)

    Args:
        bin: Name of the map bin.
        val: Value to match and remove.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_value_list(bin: str, values: list, return_type: int) -> Operation:
    """Remove entries matching any value in *values*. (Write operation)

    Args:
        bin: Name of the map bin.
        values: List of values to match and remove.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Remove entries with values in [begin, end). (Write operation)

    Args:
        bin: Name of the map bin.
        begin: Inclusive lower bound value.
        end: Exclusive upper bound value.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Remove the entry at *index* (key-ordered position). (Write operation)

    Args:
        bin: Name of the map bin.
        index: Index position (0-based).
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove entries starting at *index*. (Write operation)

    Args:
        bin: Name of the map bin.
        index: Starting index.
        return_type: One of ``MAP_RETURN_*`` constants.
        count: Number of entries. If ``None``, removes all from *index* onward.
    """

def map_remove_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Remove the entry at *rank* (value-sorted position). (Write operation)

    Args:
        bin: Name of the map bin.
        rank: Rank position (0 = smallest value).
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_remove_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Remove entries starting at *rank* in value-sorted order. (Write operation)

    Args:
        bin: Name of the map bin.
        rank: Starting rank.
        return_type: One of ``MAP_RETURN_*`` constants.
        count: Number of entries. If ``None``, removes all from *rank* onward.
    """

def map_size(bin: str) -> Operation:
    """Return the number of entries in the map bin. (Read operation)"""

def map_get_by_key(bin: str, key: Any, return_type: int) -> Operation:
    """Get the entry with *key*, shaped by *return_type*. (Read operation)

    Args:
        bin: Name of the map bin.
        key: Key to look up.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_key_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Get entries with keys in [begin, end). (Read operation)

    Args:
        bin: Name of the map bin.
        begin: Inclusive lower bound key.
        end: Exclusive upper bound key.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_value(bin: str, val: Any, return_type: int) -> Operation:
    """Get entries matching *val*. (Read operation)

    Args:
        bin: Name of the map bin.
        val: Value to match.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_value_range(bin: str, begin: Any, end: Any, return_type: int) -> Operation:
    """Get entries with values in [begin, end). (Read operation)

    Args:
        bin: Name of the map bin.
        begin: Inclusive lower bound value.
        end: Exclusive upper bound value.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_index(bin: str, index: int, return_type: int) -> Operation:
    """Get the entry at *index* (key-ordered position). (Read operation)

    Args:
        bin: Name of the map bin.
        index: Index position (0-based).
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_index_range(bin: str, index: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Get entries starting at *index*. (Read operation)

    Args:
        bin: Name of the map bin.
        index: Starting index.
        return_type: One of ``MAP_RETURN_*`` constants.
        count: Number of entries. If ``None``, returns all from *index* onward.
    """

def map_get_by_rank(bin: str, rank: int, return_type: int) -> Operation:
    """Get the entry at *rank* (value-sorted position). (Read operation)

    Args:
        bin: Name of the map bin.
        rank: Rank position (0 = smallest value).
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_rank_range(bin: str, rank: int, return_type: int, count: Optional[int] = None) -> Operation:
    """Get entries starting at *rank* in value-sorted order. (Read operation)

    Args:
        bin: Name of the map bin.
        rank: Starting rank.
        return_type: One of ``MAP_RETURN_*`` constants.
        count: Number of entries. If ``None``, returns all from *rank* onward.
    """

def map_get_by_key_list(bin: str, keys: list, return_type: int) -> Operation:
    """Get entries matching any key in *keys*. (Read operation)

    Args:
        bin: Name of the map bin.
        keys: List of keys to look up.
        return_type: One of ``MAP_RETURN_*`` constants.
    """

def map_get_by_value_list(bin: str, values: list, return_type: int) -> Operation:
    """Get entries matching any value in *values*. (Read operation)

    Args:
        bin: Name of the map bin.
        values: List of values to match.
        return_type: One of ``MAP_RETURN_*`` constants.
    """
