"""Free-threaded (3.14t / no-GIL) concurrency tests (requires Aerospike server)."""

import queue
import sys
import threading

import pytest

import aerospike_py
from tests.concurrency.utils import _drain

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

    def test_ft_concurrent_batch_operate(self, client):
        """Free-threaded batch_operate with barrier-synchronised threads."""
        keys = [(NS, SET_NAME, f"ft_bo_{i}") for i in range(20)]
        for k in keys:
            client.put(k, {"counter": 0})

        num_threads = 8
        barrier = threading.Barrier(num_threads)
        errors = queue.SimpleQueue()
        ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1}]

        def batch_inc():
            try:
                barrier.wait()
                client.batch_operate(keys, ops)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=batch_inc) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during ft batch_operate: {list(_drain(errors))}"
        for k in keys:
            _, _, bins = client.get(k)
            assert bins["counter"] == num_threads
            client.remove(k)

    def test_ft_explicit_thread_shared_client(self, client):
        """Explicit threading.Thread instances sharing one client for put/get/remove."""
        num_threads = 10
        ops_per_thread = 30
        errors = queue.SimpleQueue()

        def worker(tid):
            try:
                for i in range(ops_per_thread):
                    key = (NS, SET_NAME, f"ft_shared_{tid}_{i}")
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

        assert errors.empty(), f"Errors during ft shared client: {list(_drain(errors))}"

    def test_ft_concurrent_query(self, client):
        """Free-threaded concurrent query execution with barrier synchronisation."""
        keys = [(NS, SET_NAME, f"ft_q_{i}") for i in range(20)]
        for k in keys:
            client.put(k, {"val": int(k[2].split("_")[2])})

        num_threads = 6
        barrier = threading.Barrier(num_threads)
        errors = queue.SimpleQueue()

        def query_worker():
            try:
                barrier.wait()
                q = client.query(NS, SET_NAME)
                q.select("val")
                q.results()
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=query_worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during ft concurrent query: {list(_drain(errors))}"
        for k in keys:
            client.remove(k)
