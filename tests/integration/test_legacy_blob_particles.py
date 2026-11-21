"""Records written by old clients stay readable — issue #280.

A value that had no Aerospike type used to be serialised by the client and
stored with a particle type of its own: ``JAVA_BLOB``, ``PYTHON_BLOB`` (a
pickle) and so on. Rust client 2.x hit ``unreachable!()`` on such a bin; up to
0.14.x that reached Python as ``RustPanicError`` for the whole record, and
before that it aborted the process.

Rust client 3.0 hands the payload over as it is. A bin of a particle type the
client does not interpret is returned as ``bytes``, with a warning in the log,
and the rest of the record is read normally. What the bytes mean is the
application's to decide: for ``PYTHON_BLOB`` they are a pickle.

The records are put on the server by ``tests/legacy_blob.py``, which speaks the
wire protocol, because no current client writes these types.
"""

import logging
import pickle

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.helpers import invoke
from tests.legacy_blob import LANGUAGE_BLOBS, PYTHON_BLOB, write_bin_with_particle_type

NS = "test"
SET_NAME = "legacy_blob_particles"
ADDRESS = AEROSPIKE_CONFIG["hosts"][0]

LEGACY_VALUE = {"answer": 42, "tags": ["a", "b"]}
PAYLOAD = pickle.dumps(LEGACY_VALUE)


def _seed(client, key, particle_type: int) -> None:
    """A record with one ordinary bin and one bin of ``particle_type``."""
    client.put(key, {"plain": 7})
    digest = client.exists(key).key.digest
    result = write_bin_with_particle_type(ADDRESS, NS, SET_NAME, digest, "legacy", particle_type, PAYLOAD)
    assert result == 0, f"the server refused the seed write with result code {result}"


@pytest.mark.parametrize("particle_type", LANGUAGE_BLOBS.values(), ids=LANGUAGE_BLOBS.keys())
class TestEveryLanguageBlob:
    async def test_get_returns_the_payload_and_the_other_bins(self, any_client, client, cleanup, particle_type):
        key = (NS, SET_NAME, f"get_{particle_type}")
        cleanup.append(key)
        _seed(client, key, particle_type)

        record = await invoke(any_client, "get", key)

        assert record.bins == {"plain": 7, "legacy": PAYLOAD}
        assert type(record.bins["legacy"]) is bytes

    async def test_batch_read_returns_it_too(self, any_client, client, cleanup, particle_type):
        key = (NS, SET_NAME, f"batch_{particle_type}")
        cleanup.append(key)
        _seed(client, key, particle_type)

        (bins,) = (await invoke(any_client, "batch_read", [key])).to_list()

        assert bins == {"plain": 7, "legacy": PAYLOAD}


class TestPythonBlob:
    async def test_the_bytes_are_the_pickle_the_old_client_wrote(self, any_client, client, cleanup):
        key = (NS, SET_NAME, "pickle")
        cleanup.append(key)
        _seed(client, key, PYTHON_BLOB)

        record = await invoke(any_client, "get", key)

        assert pickle.loads(record.bins["legacy"]) == LEGACY_VALUE  # noqa: S301 — our own payload

    async def test_a_scan_does_not_stop_at_it(self, any_client, client, cleanup):
        keys = [(NS, SET_NAME, f"scan_{i}") for i in range(3)]
        cleanup.extend(keys)
        for key in keys:
            _seed(client, key, PYTHON_BLOB)

        records = await invoke(any_client.query(NS, SET_NAME), "results")

        seeded = [record for record in records if record.bins.get("legacy") == PAYLOAD]
        assert len(seeded) >= len(keys)

    def test_it_is_logged_as_a_warning_not_raised(self, client, cleanup, caplog):
        key = (NS, SET_NAME, "warned")
        cleanup.append(key)
        _seed(client, key, PYTHON_BLOB)

        with caplog.at_level(logging.WARNING):
            client.get(key)

        assert f"particle type {PYTHON_BLOB}" in caplog.text

    def test_writing_the_bytes_back_stores_an_ordinary_blob(self, client, cleanup, caplog):
        """Read-modify-write converts the bin: what is stored afterwards needs no warning."""
        key = (NS, SET_NAME, "rewritten")
        cleanup.append(key)
        _seed(client, key, PYTHON_BLOB)
        client.put(key, {"legacy": client.get(key).bins["legacy"]})
        caplog.clear()  # the read above was of the legacy bin and warned

        with caplog.at_level(logging.WARNING):
            record = client.get(key)

        assert record.bins["legacy"] == PAYLOAD
        assert "particle type" not in caplog.text


def test_reading_never_raises_a_panic_error(client, cleanup):
    """What 0.14.x did with every one of these records."""
    key = (NS, SET_NAME, "no_panic")
    cleanup.append(key)
    _seed(client, key, PYTHON_BLOB)

    try:
        client.get(key)
    except aerospike_py.RustPanicError as exc:  # pragma: no cover - the regression this guards
        pytest.fail(f"a legacy blob made the client panic again: {exc}")
