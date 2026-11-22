"""Regression for issue #280: language-specific blob particle types.

Brownfield clusters often hold records written by the official Python client
where Python-side values that have no native Aerospike mapping
(e.g. pickled objects) get stored on the wire as PYTHON_BLOB. Rust client 2.x
panicked with ``unreachable!()`` on such records. aerospike-py first turned
that panic into ``RustPanicError`` (panic = "unwind" plus a panic-safety
wrapper around every entry point); with Rust client 3.0 the bin is returned as
``bytes`` and nothing is raised.

Reading such records is tested in
``tests/integration/test_legacy_blob_particles.py``, which puts them on the
server through the wire protocol — the modern official client
(``aerospike >= 18.x``) refuses to write the values it used to pickle, so it
cannot seed them.

What stays here is the other half: the panic-safety wrapping is still in place
for whatever panics next, and it must stay transparent on ordinary reads and
writes next to the official client.
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
