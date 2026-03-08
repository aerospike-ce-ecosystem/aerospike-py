"""Multi-threaded sync client safety tests (requires Aerospike server)."""

import queue
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.concurrency.utils import _drain

NS = "test"
SET_NAME = "conc_thread"


class TestThreadSafety:
    def test_concurrent_puts_from_threads(self, client):
        """10 threads x 50 puts each, then verify all records."""
        num_threads = 10
        ops_per_thread = 50
        errors = queue.SimpleQueue()

        def put_records(thread_id):
            try:
                for i in range(ops_per_thread):
                    key = (NS, SET_NAME, f"tput_{thread_id}_{i}")
                    client.put(key, {"tid": thread_id, "idx": i})
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=put_records, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent puts: {list(_drain(errors))}"

        # Verify all records
        for tid in range(num_threads):
            for i in range(ops_per_thread):
                key = (NS, SET_NAME, f"tput_{tid}_{i}")
                _, _, bins = client.get(key)
                assert bins["tid"] == tid
                assert bins["idx"] == i
                client.remove(key)

    def test_concurrent_reads_writes(self, client):
        """5 writers incrementing + 5 readers, verify final value."""
        key = (NS, SET_NAME, "rw_counter")
        increments_per_writer = 20
        num_writers = 5
        client.put(key, {"counter": 0})
        errors = queue.SimpleQueue()

        def writer():
            try:
                for _ in range(increments_per_writer):
                    client.increment(key, "counter", 1)
            except Exception as e:
                errors.put(e)

        def reader():
            try:
                for _ in range(increments_per_writer):
                    client.get(key)
            except Exception as e:
                errors.put(e)

        threads = []
        for _ in range(num_writers):
            threads.append(threading.Thread(target=writer))
        for _ in range(5):
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent r/w: {list(_drain(errors))}"
        _, _, bins = client.get(key)
        assert bins["counter"] == num_writers * increments_per_writer
        client.remove(key)

    def test_thread_pool_executor(self, client):
        """ThreadPoolExecutor(8) with 100 put/get/remove cycles."""
        errors = queue.SimpleQueue()

        def cycle(i):
            try:
                key = (NS, SET_NAME, f"tpe_{i}")
                client.put(key, {"v": i})
                _, _, bins = client.get(key)
                assert bins["v"] == i
                client.remove(key)
            except Exception as e:
                errors.put(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(cycle, range(100)))

        assert errors.empty(), f"Errors in ThreadPoolExecutor test: {list(_drain(errors))}"

    def test_multiple_clients_from_threads(self):
        """Each thread creates its own client, uses it, and closes it."""
        num_threads = 5
        errors = queue.SimpleQueue()

        def thread_fn(tid):
            try:
                c = aerospike_py.client(AEROSPIKE_CONFIG).connect()
                for i in range(10):
                    key = (NS, SET_NAME, f"mcft_{tid}_{i}")
                    c.put(key, {"v": tid})
                    _, _, bins = c.get(key)
                    assert bins["v"] == tid
                    c.remove(key)
                c.close()
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=thread_fn, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors with per-thread clients: {list(_drain(errors))}"


class TestBatchConcurrency:
    """Batch operations under multi-threaded contention."""

    BATCH_SET = "conc_batch"

    def test_concurrent_batch_read(self, client):
        """4 threads performing batch_read simultaneously on shared keys."""
        keys = [(NS, self.BATCH_SET, f"br_{i}") for i in range(50)]
        for k in keys:
            client.put(k, {"v": int(k[2].split("_")[1])})

        errors = queue.SimpleQueue()

        def batch_reader():
            try:
                result = client.batch_read(keys, bins=["v"])
                assert len(result.batch_records) == 50
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=batch_reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent batch_read: {list(_drain(errors))}"
        for k in keys:
            client.remove(k)

    def test_concurrent_batch_operate(self, client):
        """4 threads performing batch_operate (increment) on shared keys."""
        keys = [(NS, self.BATCH_SET, f"bo_{i}") for i in range(20)]
        for k in keys:
            client.put(k, {"counter": 0})

        errors = queue.SimpleQueue()
        ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1}]

        def batch_incrementer():
            try:
                client.batch_operate(keys, ops)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=batch_incrementer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent batch_operate: {list(_drain(errors))}"
        # Each key should have been incremented 4 times
        for k in keys:
            _, _, bins = client.get(k)
            assert bins["counter"] == 4
            client.remove(k)

    def test_concurrent_batch_remove(self, client):
        """batch_remove from multiple threads on disjoint key sets."""
        errors = queue.SimpleQueue()

        def remove_batch(tid):
            try:
                keys = [(NS, self.BATCH_SET, f"brm_{tid}_{i}") for i in range(20)]
                for k in keys:
                    client.put(k, {"v": 1})
                client.batch_remove(keys)
                # Verify removal
                for k in keys:
                    result = client.exists(k)
                    assert result.meta is None
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=remove_batch, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent batch_remove: {list(_drain(errors))}"


class TestErrorPathConcurrency:
    """Concurrent operations hitting error paths (RecordNotFound, etc.)."""

    def test_concurrent_record_not_found(self, client):
        """Multiple threads reading non-existent keys should all get RecordNotFound."""
        errors = queue.SimpleQueue()
        results = queue.SimpleQueue()

        def read_missing(tid):
            try:
                key = (NS, SET_NAME, f"missing_{tid}")
                client.get(key)
                errors.put(AssertionError(f"Thread {tid}: expected RecordNotFound"))
            except aerospike_py.RecordNotFound:
                results.put(tid)
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=read_missing, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Unexpected errors: {list(_drain(errors))}"
        assert len(list(_drain(results))) == 10


class TestNumpyBatchConcurrency:
    """NumPy batch operations under concurrent access (exercises unsafe pointer code)."""

    NUMPY_SET = "conc_numpy"

    @pytest.fixture(autouse=True)
    def _requires_numpy(self):
        pytest.importorskip("numpy")

    def test_concurrent_batch_read_numpy(self, client):
        """4 threads performing batch_read with numpy dtype simultaneously."""
        import numpy as np

        keys = [(NS, self.NUMPY_SET, f"np_{i}") for i in range(30)]
        for k in keys:
            client.put(k, {"score": int(k[2].split("_")[1]) * 10, "count": 1})

        dtype = np.dtype([("score", "i4"), ("count", "i4")])
        errors = queue.SimpleQueue()

        def numpy_reader():
            try:
                result = client.batch_read(keys, bins=["score", "count"], _dtype=dtype)
                assert len(result) == 30
            except Exception as e:
                errors.put(e)

        threads = [threading.Thread(target=numpy_reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors.empty(), f"Errors during concurrent numpy batch_read: {list(_drain(errors))}"
        for k in keys:
            client.remove(k)
