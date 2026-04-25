"""Unit tests for the ``RustPanicError`` exception surface.

These tests verify the Python-visible properties of the new exception
introduced for issue #280. End-to-end behaviour (panic actually surfaces
when reading a PYTHON_BLOB record) is covered in
``tests/compatibility/test_legacy_blobs.py`` which requires a running
server and the official Python client.
"""

from __future__ import annotations

import aerospike_py


class TestRustPanicErrorSurface:
    """Properties of the exception class itself."""

    def test_importable_from_top_level(self):
        assert aerospike_py.RustPanicError is not None

    def test_importable_from_exception_module(self):
        from aerospike_py.exception import RustPanicError as FromSubmodule

        assert FromSubmodule is aerospike_py.RustPanicError

    def test_subclasses_client_error(self):
        # ClientError → AerospikeError → Exception
        assert issubclass(aerospike_py.RustPanicError, aerospike_py.ClientError)
        assert issubclass(aerospike_py.RustPanicError, aerospike_py.AerospikeError)
        assert issubclass(aerospike_py.RustPanicError, Exception)

    def test_distinct_from_other_client_errors(self):
        # Not a backpressure error, not a record error.
        assert aerospike_py.RustPanicError is not aerospike_py.BackpressureError
        assert not issubclass(aerospike_py.RustPanicError, aerospike_py.RecordError)

    def test_in_all_exports(self):
        assert "RustPanicError" in aerospike_py.__all__
        from aerospike_py.exception import __all__ as exception_all

        assert "RustPanicError" in exception_all

    def test_can_raise_and_catch(self):
        # Round-trip: instantiate, raise, catch via every level of the MRO.
        try:
            raise aerospike_py.RustPanicError("synthetic")
        except aerospike_py.RustPanicError as e:
            assert "synthetic" in str(e)

        try:
            raise aerospike_py.RustPanicError("synthetic")
        except aerospike_py.ClientError as e:
            assert isinstance(e, aerospike_py.RustPanicError)

        try:
            raise aerospike_py.RustPanicError("synthetic")
        except aerospike_py.AerospikeError as e:
            assert isinstance(e, aerospike_py.RustPanicError)
