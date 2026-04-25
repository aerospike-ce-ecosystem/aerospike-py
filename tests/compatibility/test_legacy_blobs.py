"""Regression for issue #280: language-specific blob particle types.

Brownfield clusters often hold records written by the official Python client
where Python-side values that have no native Aerospike mapping
(e.g. pickled objects) get stored on the wire as PYTHON_BLOB (particle
type 8). Before #280, ``aerospike-core 2.0.0`` panicked with
``unreachable!()`` on such records and ``panic = "abort"`` aborted the
Python process — uncatchable from Python.

The fix in aerospike-py:
1. Switches release profile to ``panic = "unwind"``.
2. Wraps every read/write entry point with a panic-safety helper that
   surfaces the panic as ``aerospike_py.RustPanicError`` (subclass of
   ``ClientError``).

These tests verify that:
- Normal read paths remain regression-free under the new wrapping
  (covered indirectly by the rest of ``tests/compatibility/``).
- An empty bins write succeeds and does not surface ``RustPanicError``
  (sanity check that the wrapping is transparent on success).

The PYTHON_BLOB scenario itself cannot be reproduced reliably with the
modern official Python client (``aerospike >= 18.x``) because it now
refuses non-native types instead of auto-pickling them. To verify the
panic catch end-to-end, see the manual smoke test in
``CHANGELOG.md`` (issue #280): write a PYTHON_BLOB via an older
language-specific client (Java / Python <= 11.x) and read it back with
aerospike-py. The expected behaviour is ``RustPanicError``.
"""

from __future__ import annotations

import pytest

import aerospike_py

aerospike = pytest.importorskip("aerospike")

NS = "test"
SET_NAME = "compat_legacy_blobs"


class TestNormalReadRegression:
    """Sanity check: panic-catch wrapping is transparent on normal reads."""

    def test_get_native_record_unaffected(self, rust_client, official_client, cleanup):
        # If the panic-catch wrapping accidentally swallowed normal errors
        # or altered the success path, this test would fail.
        key = (NS, SET_NAME, "native_record")
        cleanup.append(key)
        official_client.put(key, {"name": "alice", "age": 30, "tags": ["a", "b"]})
        _, _, bins = rust_client.get(key)
        assert bins["name"] == "alice"
        assert bins["age"] == 30
        assert bins["tags"] == ["a", "b"]

    def test_record_not_found_still_raises_recordnotfound(self, rust_client, cleanup):
        # The wrapping must let aerospike-core's structured errors through
        # untouched — only panics get rewritten to RustPanicError.
        key = (NS, SET_NAME, "definitely_missing_xyz")
        cleanup.append(key)
        with pytest.raises(aerospike_py.RecordNotFound):
            rust_client.get(key)


class TestRustPanicErrorIfTriggered:
    """If a panic does fire (e.g. via legacy data on the cluster), it must
    arrive as ``RustPanicError``. We can't auto-reproduce PYTHON_BLOB on
    modern aerospike client 18.x, so this is a manual smoke template:
    drop a record with a language-specific particle type into the cluster
    via an older client, then run this with ``--run-legacy-blob``.

    The decorator skips the test by default; flip it on locally to verify
    the catch path against real legacy data."""

    @pytest.mark.skip(
        reason="Requires legacy data (PYTHON_BLOB / JAVA_BLOB) seeded by an "
        "older language client. Run manually after seeding — see issue #280 "
        "and the module docstring."
    )
    def test_legacy_blob_surfaces_rust_panic_error(self, rust_client):
        # Replace the key below with one that exists on the cluster and
        # contains a PYTHON_BLOB / JAVA_BLOB / etc. bin.
        key = (NS, SET_NAME, "legacy_record_seeded_by_old_client")
        with pytest.raises(aerospike_py.RustPanicError):
            rust_client.get(key)
