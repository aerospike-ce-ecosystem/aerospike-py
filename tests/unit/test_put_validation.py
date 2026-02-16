"""Unit tests for put() input validation (no server required).

Covers:
- #118: put(key, None) should raise TypeError, not RecordNotFound
- put(key, non_dict) should raise TypeError
"""

import pytest

import aerospike_py


class TestPutBinsTypeValidation:
    """put()의 bins 인자에 dict가 아닌 값을 전달하면 TypeError를 발생시켜야 한다."""

    def _make_client(self):
        return aerospike_py.client({"hosts": [("127.0.0.1", 3000)]})

    def test_put_none_bins_raises_type_error(self):
        """put(key, None) → TypeError (not RecordNotFound)."""
        c = self._make_client()
        with pytest.raises(TypeError):
            c.put(("test", "demo", "k1"), None)

    def test_put_string_bins_raises_type_error(self):
        """put(key, "string") → TypeError."""
        c = self._make_client()
        with pytest.raises(TypeError):
            c.put(("test", "demo", "k1"), "not_a_dict")

    def test_put_int_bins_raises_type_error(self):
        """put(key, 123) → TypeError."""
        c = self._make_client()
        with pytest.raises(TypeError):
            c.put(("test", "demo", "k1"), 123)

    def test_put_list_bins_raises_type_error(self):
        """put(key, [1, 2]) → TypeError."""
        c = self._make_client()
        with pytest.raises(TypeError):
            c.put(("test", "demo", "k1"), [1, 2, 3])

    def test_put_tuple_bins_raises_type_error(self):
        """put(key, (1, 2)) → TypeError."""
        c = self._make_client()
        with pytest.raises(TypeError):
            c.put(("test", "demo", "k1"), (1, 2))
