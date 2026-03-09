"""Type stubs for bit_operations module.

Each function returns an ``Operation`` dict for use with
``client.operate()`` and ``client.operate_ordered()``.

Write flags constants (import from ``aerospike_py``):
    ``BIT_WRITE_DEFAULT``, ``BIT_WRITE_CREATE_ONLY``, ``BIT_WRITE_UPDATE_ONLY``,
    ``BIT_WRITE_NO_FAIL``, ``BIT_WRITE_PARTIAL``.

Resize flags constants:
    ``BIT_RESIZE_DEFAULT``, ``BIT_RESIZE_FROM_FRONT``, ``BIT_RESIZE_GROW_ONLY``,
    ``BIT_RESIZE_SHRINK_ONLY``.

Overflow action constants:
    ``BIT_OVERFLOW_FAIL``, ``BIT_OVERFLOW_SATURATE``, ``BIT_OVERFLOW_WRAP``.
"""

from typing import Optional, Union

from aerospike_py._types import Operation

def bit_resize(
    bin: str,
    byte_size: int,
    resize_flags: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Resize a bytes bin to *byte_size* according to *resize_flags*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        byte_size: Target size in bytes.
        resize_flags: ``BIT_RESIZE_DEFAULT``, ``BIT_RESIZE_FROM_FRONT``,
            ``BIT_RESIZE_GROW_ONLY``, or ``BIT_RESIZE_SHRINK_ONLY``.
        policy: Optional bit write flags (``BIT_WRITE_*`` constant).
    """

def bit_insert(
    bin: str,
    byte_offset: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Insert *value* bytes at *byte_offset*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        byte_offset: Byte position at which to insert.
        value: Bytes to insert.
        policy: Optional bit write flags.
    """

def bit_remove(
    bin: str,
    byte_offset: int,
    byte_size: int,
    policy: Optional[int] = None,
) -> Operation:
    """Remove *byte_size* bytes starting at *byte_offset*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        byte_offset: Starting byte position.
        byte_size: Number of bytes to remove.
        policy: Optional bit write flags.
    """

def bit_set(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Set bits at *bit_offset* for *bit_size* to *value*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to set.
        value: Byte value to write.
        policy: Optional bit write flags.
    """

def bit_or(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise OR on bin at *bit_offset* for *bit_size* with *value*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to OR with.
        policy: Optional bit write flags.
    """

def bit_xor(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise XOR on bin at *bit_offset* for *bit_size* with *value*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to XOR with.
        policy: Optional bit write flags.
    """

def bit_and(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: Union[bytes, bytearray],
    policy: Optional[int] = None,
) -> Operation:
    """Perform bitwise AND on bin at *bit_offset* for *bit_size* with *value*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits.
        value: Byte value to AND with.
        policy: Optional bit write flags.
    """

def bit_not(
    bin: str,
    bit_offset: int,
    bit_size: int,
    policy: Optional[int] = None,
) -> Operation:
    """Negate bits in bin starting at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to negate.
        policy: Optional bit write flags.
    """

def bit_lshift(
    bin: str,
    bit_offset: int,
    bit_size: int,
    shift: int,
    policy: Optional[int] = None,
) -> Operation:
    """Left-shift bits in bin starting at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits in the region to shift.
        shift: Number of bit positions to shift left.
        policy: Optional bit write flags.
    """

def bit_rshift(
    bin: str,
    bit_offset: int,
    bit_size: int,
    shift: int,
    policy: Optional[int] = None,
) -> Operation:
    """Right-shift bits in bin starting at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits in the region to shift.
        shift: Number of bit positions to shift right.
        policy: Optional bit write flags.
    """

def bit_add(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    signed: bool = False,
    action: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Add *value* to the integer at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to add.
        signed: If ``True``, treat the bits as a signed number.
        action: Overflow action (``BIT_OVERFLOW_FAIL``, ``BIT_OVERFLOW_SATURATE``,
            ``BIT_OVERFLOW_WRAP``).
        policy: Optional bit write flags.
    """

def bit_subtract(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    signed: bool = False,
    action: int = 0,
    policy: Optional[int] = None,
) -> Operation:
    """Subtract *value* from the integer at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to subtract.
        signed: If ``True``, treat the bits as a signed number.
        action: Overflow action (``BIT_OVERFLOW_FAIL``, ``BIT_OVERFLOW_SATURATE``,
            ``BIT_OVERFLOW_WRAP``).
        policy: Optional bit write flags.
    """

def bit_set_int(
    bin: str,
    bit_offset: int,
    bit_size: int,
    value: int,
    policy: Optional[int] = None,
) -> Operation:
    """Set the integer value at *bit_offset* for *bit_size*. (Write operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits (must be <= 64).
        value: Integer value to set.
        policy: Optional bit write flags.
    """

def bit_get(bin: str, bit_offset: int, bit_size: int) -> Operation:
    """Return bits from bin starting at *bit_offset* for *bit_size*. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to read.
    """

def bit_count(bin: str, bit_offset: int, bit_size: int) -> Operation:
    """Return the count of set bits starting at *bit_offset* for *bit_size*. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
    """

def bit_lscan(bin: str, bit_offset: int, bit_size: int, value: bool) -> Operation:
    """Return offset of first bit matching *value* scanning left-to-right. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
        value: Bit value to search for (``True`` for 1, ``False`` for 0).
    """

def bit_rscan(bin: str, bit_offset: int, bit_size: int, value: bool) -> Operation:
    """Return offset of last bit matching *value* scanning right-to-left. (Read operation)

    Args:
        bin: Name of the bytes bin.
        bit_offset: Starting bit position.
        bit_size: Number of bits to scan.
        value: Bit value to search for (``True`` for 1, ``False`` for 0).
    """

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
