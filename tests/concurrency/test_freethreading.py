"""Free-threaded (3.14t / no-GIL) concurrency tests (requires Aerospike server)."""

import queue
import sys
import threading

import pytest

NS = "test"
SET_NAME = "conc_ft"


class TestFreeThreading:
    def test_report_gil_status(self):
        """Informational: report GIL status for the current interpreter."""
        if hasattr(sys, "_is_gil_enabled"):
            gil_enabled = sys._is_gil_enabled()
            print(f"\nGIL enabled: {gil_enabled}")
        else:
            print("\nGIL status API not available (Python < 3.13)")

    def test_parallel_increments_atomicity(self, client):
        """Barrier-synchronised 20 threads x 100 increments = 2000."""
        key = (NS, SET_NAME, "ft_incr")
        num_threads = 20
        increments_per_thread = 100
        client.put(key, {"counter": 0})

        barrier = threading.Barrier(num_threads)
        errors = queue.SimpleQueue()

        def incrementer():
            try:
                barrier.wait()
                for _ in range(increments_per_thread):
                    client.increment(key, "counter", 1)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=incrementer) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during parallel increments: {list(_drain(errors))}"
        _, _, bins = client.get(key)
        assert bins["counter"] == num_threads * increments_per_thread
        client.remove(key)

    def test_parallel_put_get_isolation(self, client):
        """20 threads each use unique keys — no cross-thread interference."""
        num_threads = 20
        ops_per_thread = 50
        errors = queue.SimpleQueue()

        def worker(tid):
            try:
                for i in range(ops_per_thread):
                    key = (NS, SET_NAME, f"ft_iso_{tid}_{i}")
                    client.put(key, {"tid": tid, "idx": i})
                    _, _, bins = client.get(key)
                    assert bins["tid"] == tid
                    assert bins["idx"] == i
                    client.remove(key)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during isolation test: {list(_drain(errors))}"

    def test_client_shared_across_threads_stress(self, client):
        """50 threads x 50 operations stress on a shared client."""
        num_threads = 50
        ops_per_thread = 50
        errors = queue.SimpleQueue()

        def stress(tid):
            try:
                for i in range(ops_per_thread):
                    key = (NS, SET_NAME, f"ft_stress_{tid}_{i}")
                    client.put(key, {"v": tid * 1000 + i})
                    _, _, bins = client.get(key)
                    assert bins["v"] == tid * 1000 + i
                    client.remove(key)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=stress, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during stress test: {list(_drain(errors))}"

    def test_verify_no_gil(self):
        """Only runs on free-threaded builds; asserts GIL is disabled."""
        if not hasattr(sys, "_is_gil_enabled"):
            pytest.skip("sys._is_gil_enabled not available (Python < 3.13)")
        if sys._is_gil_enabled():
            pytest.skip("GIL is enabled — not a free-threaded build")
        assert sys._is_gil_enabled() is False


def _drain(q):
    """Drain all items from a SimpleQueue for error reporting."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items
