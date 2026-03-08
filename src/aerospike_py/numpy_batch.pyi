"""Type stubs for numpy_batch module."""

from typing import Iterator, Union

import numpy as np

__all__ = ["NumpyBatchRecords"]

class NumpyBatchRecords:
    """Holds batch_read results as a numpy structured array.

    Provides indexed, keyed, and iteration-based access to batch results
    stored in contiguous numpy arrays for efficient vectorized operations.

    Attributes:
        batch_records: Structured numpy array containing bin data.
        meta: Structured numpy array with ``(gen, ttl)`` per record.
        result_codes: int32 array of Aerospike result codes (0 = success).
    """

    batch_records: np.ndarray
    meta: np.ndarray
    result_codes: np.ndarray

    def __init__(
        self,
        batch_records: np.ndarray,
        meta: np.ndarray,
        result_codes: np.ndarray,
        _map: dict[Union[str, int, bytes], int],
    ) -> None: ...
    def get(self, key: Union[str, int, bytes]) -> np.void:
        """Retrieve a single record by primary key.

        Args:
            key: The primary key (string, int, or bytes) used during batch_read.

        Returns:
            A single row of the structured array (numpy scalar record).

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
    def __contains__(self, key: Union[str, int, bytes]) -> bool:
        """Check whether a primary key exists in the result set."""
        ...
    def __repr__(self) -> str: ...

def _batch_records_to_numpy(
    batch_records_obj: object,
    dtype: np.dtype,
    keys: list,
    *,
    strict: bool = False,
) -> NumpyBatchRecords:
    """Convert BatchRecords to NumpyBatchRecords.

    Args:
        batch_records_obj: BatchRecords object from batch_read.
        dtype: numpy structured array dtype defining bin field layout.
        keys: List of primary keys corresponding to batch records.
        strict: If True, warns when dtype-defined bins are missing from records,
                or when record bins are not in dtype.

    Returns:
        NumpyBatchRecords wrapping the converted numpy arrays.
    """
    ...
