"""GIL-release verification for ``LazyBatchRecords.to_numpy(dtype)``.

The PR-374 headline feature wraps the per-record numpy fill loop in
``Python::detach`` so the GIL is released while raw Aerospike values
are written into the NumPy buffer. Without this test that behaviour is
only proven by the load-test report in
``benchmark/results/gil-detach-zerocopy-loadtest.md`` — a future
refactor that wraps the loop back inside the GIL would pass every
existing test silently and only resurface as a production regression.

The test starts a sidecar Python thread that spins a counter (pure
Python work, GIL-bound) and measures whether the counter advances
during the ``to_numpy(dtype)`` call. If the GIL is released, the
sidecar advances by ≫ 0; if it is held, the sidecar barely moves.

The threshold is intentionally generous (the sidecar must advance by
*more than a tiny floor*, not match a specific rate) so the test does
not flake on a busy CI runner. The relative comparison against an
in-GIL ``to_dict()`` warm-up baseline is the load-bearing assertion.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

NS = "test"
SET_NAME = "conc_numpy"

# Big enough that the per-record fill loop is the dominant cost slice
# of the call — too small and the GIL-released window is below the
# sidecar scheduling jitter floor.
N_RECORDS = 2000
N_FEATURES = 32
DTYPE = np.dtype([(f"f{i}", "<f4") for i in range(N_FEATURES)])

# How long the sidecar spins before we measure. Long enough to absorb
# the first-call import / dtype-parse cost so the comparison is purely
# fill-loop vs. fill-loop.
WARMUP_SECONDS = 0.05


class _CounterSidecar:
    """Background thread spinning a Python counter until ``stop()``.

    Pure Python increments hold the GIL, so the counter only advances
    when the main thread has released it.
    """

    def __init__(self) -> None:
        self.count = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        # Tight Python loop — every increment requires the GIL.
        while not self._stop.is_set():
            self.count += 1

    def start(self) -> None:
        self._thread.start()
        # Brief warm-up so the thread is genuinely scheduled before we measure.
        time.sleep(WARMUP_SECONDS)

    def stop(self) -> int:
        self._stop.set()
        self._thread.join(timeout=5.0)
        return self.count


@pytest.fixture(scope="module")
def _seed_numpy_batch(client):
    """Seed ``N_RECORDS`` with ``N_FEATURES`` float bins each."""
    keys = [(NS, SET_NAME, f"gil_detach_{i}") for i in range(N_RECORDS)]
    for i, k in enumerate(keys):
        bins = {f"f{j}": float(i + j) for j in range(N_FEATURES)}
        client.put(k, bins)
    yield keys
    # cleanup runs via module-level truncate fixture in conftest


class TestToNumpyReleasesGil:
    """``to_numpy(dtype)`` must let a sidecar Python thread make progress."""

    def test_to_numpy_releases_gil_for_sidecar(self, client, _seed_numpy_batch):
        """A sidecar Python thread must reach ≥ 30 % of its alone-rate
        progress while ``to_numpy(dtype)`` runs on the main thread.

        Methodology (cross-platform robust):

        1) Calibrate the sidecar's alone-rate by sleeping the main
           thread (``time.sleep`` releases the GIL) for a fixed window.
           This is the "GIL unconditionally available" rate.
        2) Run the sidecar during ``to_numpy(dtype)``. The main thread
           is now active in native Rust code; the only way the sidecar
           can keep close to its alone-rate is if that native code
           explicitly releases the GIL via ``py.detach``.

        We don't try to assert near-100 % because CPython's GIL switch
        latency, Tokio's brief GIL touches around `into_pyobject`, and
        the OS scheduler all shave a few percent off in practice. 30 %
        is well above the floor without ``py.detach`` (single-digit
        percent in our measurements on macOS) but well below the
        observed steady-state with ``py.detach`` (typically 80-95 %).
        """
        keys = _seed_numpy_batch

        # Warm shared caches so the timed call is the fill loop, not
        # first-call setup (import, dtype parse, key_map prep).
        client.batch_read(keys).to_numpy(DTYPE)
        client.batch_read(keys).to_dict()

        # 1) Calibrate sidecar alone-rate while the main thread sleeps
        #    (sleep releases the GIL unconditionally → sidecar runs
        #    essentially uncontended on its own core).
        sidecar_alone = _CounterSidecar()
        sidecar_alone.start()
        t0 = time.perf_counter()
        time.sleep(0.05)  # 50 ms of unambiguous GIL availability
        alone_wall = time.perf_counter() - t0
        alone_count = sidecar_alone.stop()

        # 2) Measure how far the sidecar advances during a real
        #    `to_numpy(dtype)` call. With `py.detach` in place the rate
        #    should be close to `alone_rate`; without it the rate
        #    drops to whatever a GIL-rotation tick gives the sidecar.
        lazy_records_measured = client.batch_read(keys)
        sidecar_numpy = _CounterSidecar()
        sidecar_numpy.start()
        t0 = time.perf_counter()
        lazy_records_measured.to_numpy(DTYPE)
        measured_wall = time.perf_counter() - t0
        measured_count = sidecar_numpy.stop()

        # Sanity: both windows actually elapsed enough that the
        # comparison is not measuring scheduling jitter.
        assert alone_wall > 1e-3
        assert measured_wall > 1e-3, (
            f"to_numpy window too short to measure GIL release: {measured_wall * 1000:.3f} ms — raise N_RECORDS"
        )
        # Sanity: the sidecar's calibration actually counted something.
        assert alone_count > 1000, (
            f"sidecar alone-rate calibration produced {alone_count} counts "
            f"in {alone_wall * 1000:.2f} ms — system is too noisy to run this test"
        )

        alone_rate = alone_count / alone_wall
        measured_rate = measured_count / measured_wall
        share = measured_rate / alone_rate if alone_rate > 0 else 0.0

        # The load-bearing assertion: the GIL must be released for at
        # least ~30 % of the to_numpy wall-clock window. The threshold
        # is intentionally lenient (typical share is 0.8 - 0.95).
        assert share >= 0.30, (
            "to_numpy(dtype) did not release the GIL enough — sidecar reached "
            f"only {share:.1%} of its alone-rate "
            f"({measured_rate:.0f}/s during to_numpy vs {alone_rate:.0f}/s during "
            f"time.sleep). The per-record fill loop in `batch_to_numpy_py` is "
            f"probably no longer wrapped in `py.detach(...)` — see "
            f"rust/src/numpy_support.rs."
        )
