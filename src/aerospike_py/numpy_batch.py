"""BatchRecords → numpy structured array 변환 모듈."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import numpy as np


class NumpyBatchRecords:
    """batch_read 결과를 numpy structured array로 보관."""

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
        """primary_key로 단일 레코드 조회.

        Returns:
            np.void: structured array의 단일 행 (numpy scalar record).

        Raises:
            KeyError: key가 _map에 존재하지 않을 때.
        """
        return self.batch_records[self._map[key]]


# int, uint, float, bytes, void
_ALLOWED_KINDS = {"i", "u", "f", "S", "V"}


def _batch_records_to_numpy(batch_records_obj, dtype, keys, *, strict=False):
    """BatchRecords → NumpyBatchRecords 변환.

    Args:
        batch_records_obj: BatchRecords 객체.
        dtype: numpy structured array dtype.
        keys: key 목록.
        strict: True이면 dtype에 정의된 bin이 레코드에 없거나,
                레코드에 있는 bin이 dtype에 없을 때 경고를 발생시킴.
    """
    import numpy as np

    # dtype 검증: 숫자(int/float) 또는 고정 길이 bytes만 허용
    for name in dtype.names:
        field_dtype = dtype[name]
        base = field_dtype.base  # sub-array인 경우 base dtype 확인
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
        # key → index 매핑 (primary_key는 key tuple의 [2])
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
            # meta 채우기
            if record_meta:
                meta[i]["gen"] = record_meta.get("gen", 0)
                meta[i]["ttl"] = record_meta.get("ttl", 0)
            # bins → structured array 채우기
            if bins:
                if strict:
                    bin_keys = set(bins.keys())
                    missing = dtype_fields - bin_keys
                    extra = bin_keys - dtype_fields
                    if missing:
                        warnings.warn(
                            f"record at index {i}: dtype fields {missing} "
                            f"not found in bins (zero-filled)",
                            stacklevel=2,
                        )
                    if extra:
                        warnings.warn(
                            f"record at index {i}: bin fields {extra} "
                            f"not in dtype (ignored)",
                            stacklevel=2,
                        )
                for field in dtype.names:
                    val = bins.get(field)
                    if val is not None:
                        data[i][field] = val

    return NumpyBatchRecords(data, meta, result_codes, key_map)
