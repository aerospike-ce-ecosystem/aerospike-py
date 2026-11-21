"""BatchRecords to numpy structured array conversion module."""

from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING, Any, Iterator, Union

if TYPE_CHECKING:
    import numpy as np

__all__ = ["NumpyBatchRecords"]


class NumpyBatchRecords:
    """Holds batch_read results as a numpy structured array.

    Row ``i`` of every array corresponds to request key ``i``, whether that
    read succeeded, missed or failed. Rows are reachable by position
    (``batch_records[i]``), by iteration, and — for rows requested with a user
    key — by that key through :meth:`get` and ``in``.

    A row requested by digest only has no user key and is therefore reachable
    by position only. When the same user key was requested more than once,
    :meth:`get` returns the last of those rows.

    Attributes:
        batch_records: Structured numpy array containing bin data.
        meta: Structured numpy array with ``(gen, ttl)`` per record.
        result_codes: int32 array of Aerospike result codes (0 = success).
    """

    __slots__ = ("_map", "batch_records", "meta", "result_codes")

    def __init__(
        self,
        batch_records: np.ndarray,
        meta: np.ndarray,
        result_codes: np.ndarray,
        _map: dict[Union[str, int, bytes], int],
    ):
        self.batch_records = batch_records
        self.meta = meta
        self.result_codes = result_codes
        self._map = _map

    def get(self, key: Union[str, int, bytes]) -> "np.void":
        """Retrieve a single record by primary key.

        Args:
            key: The primary key (string, int, or bytes) used during batch_read.

        Returns:
            A single row of the structured array (numpy scalar record). When
            the key was requested more than once, the last matching row.

        Raises:
            KeyError: When no row was requested with this user key. Rows
                requested by digest only are never found by key; read them by
                position from ``batch_records``.
        """
        try:
            return self.batch_records[self._map[key]]
        except KeyError:
            raise KeyError(f"key {key!r} not found in NumpyBatchRecords (available keys: {len(self._map)})") from None

    def __len__(self) -> int:
        """Return the number of records in the batch result."""
        return len(self.batch_records)

    def __iter__(self) -> "Iterator[np.void]":
        """Iterate over individual records in the batch result."""
        return iter(self.batch_records)

    def __contains__(self, key: Union[str, int, bytes]) -> bool:
        """Check whether a row was requested with this user key."""
        return key in self._map

    def __repr__(self) -> str:
        ok_count = int((self.result_codes == 0).sum()) if len(self.result_codes) > 0 else 0
        fields = list(self.batch_records.dtype.names) if self.batch_records.dtype.names else []
        return f"NumpyBatchRecords(count={len(self)}, ok={ok_count}, fields={fields})"


# Largest finite magnitude of the narrow float widths. A finite value beyond
# it would silently become ±inf on assignment, so it is rejected instead.
_FLOAT_MAX = {2: 65504.0, 4: 3.4028234663852886e38}


def _check_float_range(base: Any, val: Any, field: str) -> None:
    """Raise ``OverflowError`` for a finite value a narrow float cannot hold.

    NaN and ±inf pass through unchanged: they are values of their own, not the
    result of an overflow.
    """
    limit = _FLOAT_MAX.get(base.itemsize) if base.kind == "f" else None
    if limit is None or isinstance(val, bool) or not isinstance(val, (int, float)):
        return
    as_float = float(val)
    if math.isfinite(as_float) and abs(as_float) > limit:
        raise OverflowError(f"float overflow: value {val!r} does not fit in f{base.itemsize * 8} for field '{field}'")


def _check_float_range_of_array(base: Any, arr: Any, field: str) -> None:
    """Apply :func:`_check_float_range` to every element of a numeric array.

    Assigning the array would let NumPy turn an out-of-range element into
    ±inf with nothing but a ``RuntimeWarning``.
    """
    import numpy as np

    limit = _FLOAT_MAX.get(base.itemsize) if base.kind == "f" else None
    if limit is None or arr.dtype.kind not in "iuf":
        return
    wide = arr.astype(np.float64, copy=False)
    too_big = np.isfinite(wide) & (np.abs(wide) > limit)
    if too_big.any():
        first = wide[too_big].flat[0]
        raise OverflowError(
            f"float overflow: value {float(first)!r} does not fit in f{base.itemsize * 8} for field '{field}'"
        )


def _with_row_context(exc: Exception, message: str) -> Exception:
    """Return an exception of ``exc``'s kind that carries ``message``.

    The exact type is kept when it can be built from one message. A type whose
    constructor needs more (``UnicodeEncodeError`` takes five arguments) falls
    back to the built-in it derives from, so the row context is added instead
    of the conversion failing with an unrelated ``TypeError``.
    """
    try:
        return type(exc)(message)
    except TypeError:
        for kind in (OverflowError, TypeError, ValueError):
            if isinstance(exc, kind):
                return kind(message)
        raise


def _assign_value(data: Any, i: int, field: str, field_dtype: Any, val: Any) -> None:
    """Store one bin value, following the rules of the native conversion.

    A numeric sub-array field is a vector: it takes a blob of exactly
    ``itemsize`` bytes. A scalar is accepted only by a one-element vector,
    which is how releases up to 0.14.x stored ``(1,)`` fields.
    """
    import numpy as np

    base = field_dtype.base
    if field_dtype.subdtype is not None and base.kind in "iuf":
        if isinstance(val, (bytes, bytearray, memoryview)):
            if len(val) != field_dtype.itemsize:
                raise ValueError(
                    f"vector length mismatch for field '{field}': the stored blob has {len(val)} bytes, "
                    f"the dtype expects {field_dtype.itemsize}"
                )
            # The native writer stores native-endian bytes; NumPy converts to
            # the field's own byte order on assignment.
            native = np.frombuffer(bytes(val), dtype=base.newbyteorder("="))
            data[field][i] = native.reshape(field_dtype.shape)
            return
        if isinstance(val, (bool, int, float)):
            count = field_dtype.itemsize // base.itemsize
            if count != 1:
                raise ValueError(
                    f"vector length mismatch for field '{field}': the stored value is a scalar, "
                    f"the dtype expects {count} elements"
                )
            _check_float_range(base, val, field)
            data[field][i] = val
            return
        if isinstance(val, (np.ndarray, list, tuple)):
            # Already an element sequence: NumPy would broadcast a shorter one,
            # so the shape is checked rather than left to assignment.
            arr = np.asarray(val)
            if arr.shape != field_dtype.shape:
                raise ValueError(
                    f"vector length mismatch for field '{field}': the value has shape {arr.shape}, "
                    f"the dtype expects {field_dtype.shape}"
                )
            _check_float_range_of_array(base, arr, field)
            data[field][i] = arr
            return
        raise TypeError(f"unsupported value type {type(val).__name__} for numpy vector field '{field}'")

    if base.kind == "S" and isinstance(val, str):
        # The native conversion stores the UTF-8 bytes of a string; NumPy
        # alone would only accept ASCII here.
        val = val.encode("utf-8")
    _check_float_range(base, val, field)
    data[field][i] = val


def _batch_records_to_numpy(batch_records_obj, dtype, keys, *, strict=False):
    """Convert BatchRecords to NumpyBatchRecords.

    The dtype is validated by the same native validator the ``to_numpy`` and
    ``batch_write_numpy`` paths use, and rows are indexed by the same rules:
    row ``i`` is request ``i``, only real user keys are indexed, and the last
    row wins when a user key repeats.

    One rule differs on purpose. The native paths copy raw bytes and reject a
    non-native byte order; this function assigns through NumPy, which swaps
    bytes itself, so a byte-swapped dtype such as ``>i4`` is accepted here and
    round-trips correctly.

    Args:
        batch_records_obj: BatchRecords object.
        dtype: numpy structured array dtype.
        keys: List of keys.
        strict: If True, raises warnings when dtype-defined bins are missing from records,
                or when record bins are not in dtype.
    """
    import numpy as np

    from aerospike_py._aerospike import validate_numpy_dtype

    validate_numpy_dtype(dtype, require_native_byteorder=False)

    dtype_fields = set(dtype.names)
    n = len(batch_records_obj.batch_records)
    data = np.zeros(n, dtype=dtype)
    meta = np.zeros(n, dtype=[("gen", "u4"), ("ttl", "u4")])
    result_codes = np.zeros(n, dtype=np.int32)
    key_map: dict[Union[str, int, bytes], int] = {}

    for i, br in enumerate(batch_records_obj.batch_records):
        result_codes[i] = br.result
        # key → index mapping (primary_key is key tuple[2]). A row without a
        # user key — a digest-only request — is reachable by position only: no
        # stand-in key is invented for it.
        pk = br.key[2] if br.key and len(br.key) >= 3 else None
        if pk is not None:
            key_map[pk] = i

        if br.result == 0 and br.record is not None:
            _, record_meta, bins = br.record
            # Fill metadata
            if record_meta:
                meta[i]["gen"] = record_meta.get("gen", 0)
                meta[i]["ttl"] = record_meta.get("ttl", 0)
            # Fill bins into structured array
            if bins:
                if strict:
                    bin_keys = set(bins.keys())
                    missing = dtype_fields - bin_keys
                    extra = bin_keys - dtype_fields
                    if missing:
                        warnings.warn(
                            f"record at index {i}: dtype fields {missing} not found in bins (zero-filled)",
                            stacklevel=4,
                        )
                    if extra:
                        warnings.warn(
                            f"record at index {i}: bin fields {extra} not in dtype (ignored)",
                            stacklevel=4,
                        )
                for field in dtype.names:
                    val = bins.get(field)
                    if val is not None:
                        try:
                            _assign_value(data, i, field, dtype[field], val)
                        except (ValueError, TypeError, OverflowError) as exc:
                            raise _with_row_context(
                                exc,
                                f"Failed to assign value {val!r} to field '{field}' "
                                f"(dtype={dtype[field]}) for record at index {i} (key={pk!r}): {exc}",
                            ) from exc

    return NumpyBatchRecords(data, meta, result_codes, key_map)
