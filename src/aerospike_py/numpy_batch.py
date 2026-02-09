"""BatchRecords to numpy structured array conversion module."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import numpy as np

__all__ = ["NumpyBatchRecords"]


class NumpyBatchRecords:
    """Holds batch_read results as a numpy structured array."""

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

        Returns:
            np.void: A single row of the structured array (numpy scalar record).

        Raises:
            KeyError: When the key does not exist in the map.
        """
        return self.batch_records[self._map[key]]


# int, uint, float, bytes, void
_ALLOWED_KINDS = {"i", "u", "f", "S", "V"}


def _batch_records_to_numpy(batch_records_obj, dtype, keys, *, strict=False):
    """Convert BatchRecords to NumpyBatchRecords.

    Args:
        batch_records_obj: BatchRecords object.
        dtype: numpy structured array dtype.
        keys: List of keys.
        strict: If True, raises warnings when dtype-defined bins are missing from records,
                or when record bins are not in dtype.
    """
    import numpy as np

    # Validate dtype: only numeric (int/float) or fixed-length bytes allowed
    for name in dtype.names:
        field_dtype = dtype[name]
        base = field_dtype.base  # Check base dtype for sub-array types
        if base.kind not in _ALLOWED_KINDS:
            raise TypeError(
                f"dtype field '{name}' must be numeric (int/float) or "
                f"fixed-length bytes, got {field_dtype} (kind='{base.kind}')"
            )

    dtype_fields = set(dtype.names)
    n = len(batch_records_obj.batch_records)
    data = np.zeros(n, dtype=dtype)
    meta = np.zeros(n, dtype=[("gen", "u4"), ("ttl", "u4")])
    result_codes = np.zeros(n, dtype=np.int32)
    key_map: dict[Union[str, int, bytes], int] = {}

    for i, br in enumerate(batch_records_obj.batch_records):
        result_codes[i] = br.result
        # key → index mapping (primary_key is key tuple[2])
        if br.key and len(br.key) >= 3:
            pk = br.key[2]
        else:
            warnings.warn(
                f"batch record at index {i} has missing or malformed key "
                f"(key={br.key!r}); falling back to integer index as map key. "
                f"NumpyBatchRecords.get() will not find this record by primary key.",
                stacklevel=2,
            )
            pk = i
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
                            stacklevel=2,
                        )
                    if extra:
                        warnings.warn(
                            f"record at index {i}: bin fields {extra} not in dtype (ignored)",
                            stacklevel=2,
                        )
                for field in dtype.names:
                    val = bins.get(field)
                    if val is not None:
                        data[i][field] = val

    return NumpyBatchRecords(data, meta, result_codes, key_map)
