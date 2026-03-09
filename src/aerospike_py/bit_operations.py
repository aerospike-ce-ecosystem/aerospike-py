"""Bitwise CDT operation helpers.

Each function returns an operation dict for use with ``client.operate()``
and ``client.operate_ordered()``.
"""

from typing import Optional, Union

from aerospike_py._types import _UNSET, Operation, _build_op

__all__ = [
    "Operation",
    "bit_resize",
    "bit_insert",
    "bit_remove",
    "bit_set",
    "bit_or",
    "bit_xor",
    "bit_and",
    "bit_not",
    "bit_lshift",
    "bit_rshift",
    "bit_add",
    "bit_subtract",
    "bit_set_int",
    "bit_get",
    "bit_count",
    "bit_lscan",
    "bit_rscan",
    "bit_get_int",
]

# Bitwise operation codes (must match rust/src/constants.rs CDT codes)
_OP_BIT_RESIZE = 4001
_OP_BIT_INSERT = 4002
_OP_BIT_REMOVE = 4003
_OP_BIT_SET = 4004
_OP_BIT_OR = 4005
_OP_BIT_XOR = 4006
_OP_BIT_AND = 4007
_OP_BIT_NOT = 4008
_OP_BIT_LSHIFT = 4009
_OP_BIT_RSHIFT = 4010
_OP_BIT_ADD = 4011
_OP_BIT_SUBTRACT = 4012
_OP_BIT_SET_INT = 4013
_OP_BIT_GET = 4050
_OP_BIT_COUNT = 4051
_OP_BIT_LSCAN = 4052
_OP_BIT_RSCAN = 4053
_OP_BIT_GET_INT = 4054


def bit_resize(
    bin: str,
    byte_size: int,
    resize_flags: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Resize a bytes bin to *byte_size* according to *resize_flags*.

    Args:
        bin: Name of the bytes bin.
        byte_size: Target size in bytes.
        resize_flags: ``BIT_RESIZE_DEFAULT``, ``BIT_RESIZE_FROM_FRONT``,
            ``BIT_RESIZE_GROW_ONLY``, or ``BIT_RESIZE_SHRINK_ONLY``.
        policy: Optional bit write flags (``BIT_WRITE_*`` constant).

    Note:
        Flag composition via bitwise OR (e.g.,
        ``BIT_RESIZE_GROW_ONLY | BIT_RESIZE_FROM_FRONT``) is not currently
        supported. Use individual flags only.
    """
    return _build_op(
        _OP_BIT_RESIZE,
        bin,
        byte_size=byte_size,
        resize_flags=resize_flags if resize_flags != 0 else _UNSET,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_insert(
    bin: str,
    byte_offset: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Insert *value* bytes at *byte_offset*.

    Args:
        bin: Name of the bytes bin.
        byte_offset: Byte position at which to insert.
        value: Bytes to insert.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_INSERT,
        bin,
        byte_offset=byte_offset,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_remove(
    bin: str,
    byte_offset: int,
    byte_size: int,
    policy: Optional[int] = None,
) -> Operation:
    """Remove *byte_size* bytes starting at *byte_offset*.

    Args:
        bin: Name of the bytes bin.
        byte_offset: Starting byte position.
        byte_size: Number of bytes to remove.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_REMOVE,
        bin,
        byte_offset=byte_offset,
        byte_size=byte_size,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_set(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Set bits at *bit_offset* for *bit_size* to *value*.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to set.
        value: Byte value to write.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_SET,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_or(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise OR on bin at *bit_offset* for *bit_size* with *value*.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to OR with.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_OR,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_xor(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise XOR on bin at *bit_offset* for *bit_size* with *value*.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to XOR with.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_XOR,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_and(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise AND on bin at *bit_offset* for *bit_size* with *value*.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to AND with.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_AND,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_not(
    bin: str,
    bit_offset: int,
    bit_size: int,
    policy: Optional[int] = None,
) -> Operation:
    """Negate bits in bin starting at *bit_offset* for *bit_size*.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to negate.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_NOT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_lshift(
    bin: str,
    bit_offset: int,
    bit_size: int,
    shift: int,
    policy: Optional[int] = None,
) -> Operation:
    """Left-shift bits in bin starting at *bit_offset* for *bit_size* by *shift* positions.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits in the region to shift.
        shift: Number of bit positions to shift left.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_LSHIFT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        shift=shift,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_rshift(
    bin: str,
    bit_offset: int,
    bit_size: int,
    shift: int,
    policy: Optional[int] = None,
) -> Operation:
    """Right-shift bits in bin starting at *bit_offset* for *bit_size* by *shift* positions.

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits in the region to shift.
        shift: Number of bit positions to shift right.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_RSHIFT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        shift=shift,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_add(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    signed: bool = False,
    action: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Add *value* to the integer at *bit_offset* for *bit_size* (max 64 bits).

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to add.
        signed: If ``True``, treat the bits as a signed number.
        action: Overflow action: ``BIT_OVERFLOW_FAIL``, ``BIT_OVERFLOW_SATURATE``,
            or ``BIT_OVERFLOW_WRAP``.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_ADD,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        signed=signed,
        action=action,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_subtract(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    signed: bool = False,
    action: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Subtract *value* from the integer at *bit_offset* for *bit_size* (max 64 bits).

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to subtract.
        signed: If ``True``, treat the bits as a signed number.
        action: Overflow action: ``BIT_OVERFLOW_FAIL``, ``BIT_OVERFLOW_SATURATE``,
            or ``BIT_OVERFLOW_WRAP``.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_SUBTRACT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        signed=signed,
        action=action,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_set_int(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    policy: Optional[int] = None,
) -> Operation:
    """Set the integer value at *bit_offset* for *bit_size* (max 64 bits).

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to set.
        policy: Optional bit write flags.
    """
    return _build_op(
        _OP_BIT_SET_INT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
        bit_policy=policy if policy is not None else _UNSET,
    )


def bit_get(bin: str, bit_offset: int, bit_size: int) -> Operation:
    """Return bits from bin starting at *bit_offset* for *bit_size*. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to read.
    """
    return _build_op(_OP_BIT_GET, bin, bit_offset=bit_offset, bit_size=bit_size)


def bit_count(bin: str, bit_offset: int, bit_size: int) -> Operation:
    """Return the count of set bits starting at *bit_offset* for *bit_size*. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
    """
    return _build_op(_OP_BIT_COUNT, bin, bit_offset=bit_offset, bit_size=bit_size)


def bit_lscan(bin: str, bit_offset: int, bit_size: int, value: bool) -> Operation:
    """Return offset of first bit matching *value* scanning left-to-right. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
        value: Bit value to search for (``True`` for 1, ``False`` for 0).
    """
    return _build_op(
        _OP_BIT_LSCAN,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
    )


def bit_rscan(bin: str, bit_offset: int, bit_size: int, value: bool) -> Operation:
    """Return offset of last bit matching *value* scanning right-to-left. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
        value: Bit value to search for (``True`` for 1, ``False`` for 0).
    """
    return _build_op(
        _OP_BIT_RSCAN,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        val=value,
    )


def bit_get_int(
    bin: str,
    bit_offset: int,
    bit_size: int,
    signed: bool = False,
) -> Operation:
    """Return an integer from bin starting at *bit_offset* for *bit_size*. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        signed: If ``True``, treat the bits as a signed number.
    """
    return _build_op(
        _OP_BIT_GET_INT,
        bin,
        bit_offset=bit_offset,
        bit_size=bit_size,
        signed=signed,
    )
