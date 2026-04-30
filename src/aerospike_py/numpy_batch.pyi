"""Type stubs for numpy_batch module.

These stubs enrich the runtime ``NumpyBatchRecords`` class so type checkers
(pyright, mypy) understand the *structured* nature of the underlying numpy
arrays. In particular the dtype on ``batch_records`` is expressed as
``np.dtype[np.void]`` because batch results are always returned as a
structured (record) array — each row is a void scalar whose fields are the
caller-supplied bin names.
"""

from __future__ import annotations

from typing import Any, Iterator, TypeAlias, Union

import numpy as np

__all__ = ["NumpyBatchRecords"]

# Primary key type accepted by ``get`` / ``__contains__``. Mirrors the
# ``UserKey`` runtime type alias (str | int | bytes).
_UserKey: TypeAlias = Union[str, int, bytes]

class NumpyBatchRecords:
    """Holds batch_read results as a numpy structured array.

    Provides indexed, keyed, and iteration-based access to batch results
    stored in contiguous numpy arrays for efficient vectorized operations.

    Attributes:
        batch_records: Structured numpy array (``dtype.kind == 'V'``)
            containing one row per requested key. Field names match the
            bin names supplied via the caller's dtype.
        meta: Structured numpy array with two ``uint32`` fields per record
            named ``"gen"`` and ``"ttl"``.
        result_codes: ``int32`` array of Aerospike result codes
            (``0`` = success; non-zero = per-record error).
    """

    # NOTE: numpy 2.x typing — ``ndarray[Any, np.dtype[np.void]]`` denotes a
    # structured array. Older numpy stubs may downgrade this to ``Any``;
    # the annotation is still useful for callers that pin numpy >= 1.22.
    batch_records: np.ndarray[Any, np.dtype[np.void]]
    meta: np.ndarray[Any, np.dtype[np.void]]
    result_codes: np.ndarray[Any, np.dtype[np.int32]]

    def __init__(
        self,
        batch_records: np.ndarray[Any, np.dtype[np.void]],
        meta: np.ndarray[Any, np.dtype[np.void]],
        result_codes: np.ndarray[Any, np.dtype[np.int32]],
        _map: dict[_UserKey, int],
    ) -> None: ...
    def get(self, key: _UserKey) -> np.void:
        """Retrieve a single record by primary key.

        Args:
            key: The primary key (string, int, or bytes) used during batch_read.

        Returns:
            A single row of the structured array (numpy ``np.void`` scalar).

        Raises:
            KeyError: When the key does not exist in the result set.
        """
        ...
    def __len__(self) -> int:
        """Return the number of records in the batch result."""
        ...
    def __iter__(self) -> Iterator[np.void]:
        """Iterate over individual records in the batch result."""
        ...
    def __contains__(self, key: _UserKey) -> bool:
        """Check whether a primary key exists in the result set."""
        ...
    def __repr__(self) -> str: ...

def _batch_records_to_numpy(
    batch_records_obj: Any,
    dtype: np.dtype[Any],
    keys: list[_UserKey],
    *,
    strict: bool = False,
) -> NumpyBatchRecords:
    """Convert BatchRecords to NumpyBatchRecords.

    Args:
        batch_records_obj: BatchRecords object from batch_read.
        dtype: numpy structured array dtype defining bin field layout.
            Each field must be numeric (``int``/``uint``/``float``) or a
            fixed-length bytes (``S``) / void (``V``) field; non-numeric
            object dtypes raise ``TypeError``.
        keys: List of primary keys corresponding to batch records.
        strict: If True, warns when dtype-defined bins are missing from
            records, or when record bins are not in dtype.

    Returns:
        NumpyBatchRecords wrapping the converted numpy arrays.
    """
    ...
