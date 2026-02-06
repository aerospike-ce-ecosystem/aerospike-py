"""Multi-threaded sync client safety tests (requires Aerospike server)."""

import threading
from concurrent.futures import ThreadPoolExecutor

import aerospike_py


CONFIG = {"hosts": [("127.0.0.1", 3000)], "cluster_name": "docker"}
NS = "test"
SET_NAME = "conc_thread"


class TestThreadSafety:
    def test_concurrent_puts_from_threads(self, client):
        """10 threads x 50 puts each, then verify all records."""
        num_threads = 10
        ops_per_thread = 50
        errors = []

        def put_records(thread_id):
            try:
                for i in range(ops_per_thread):
                    key = (NS, SET_NAME, f"tput_{thread_id}_{i}")
                    client.put(key, {"tid": thread_id, "idx": i})
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=put_records, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent puts: {errors}"

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
        errors = []

        def writer():
            try:
                for _ in range(increments_per_writer):
                    client.increment(key, "counter", 1)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(increments_per_writer):
                    client.get(key)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(num_writers):
            threads.append(threading.Thread(target=writer))
        for _ in range(5):
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent r/w: {errors}"
        _, _, bins = client.get(key)
        assert bins["counter"] == num_writers * increments_per_writer
        client.remove(key)

    def test_thread_pool_executor(self, client):
        """ThreadPoolExecutor(8) with 100 put/get/remove cycles."""
        errors = []

        def cycle(i):
            try:
                key = (NS, SET_NAME, f"tpe_{i}")
                client.put(key, {"v": i})
                _, _, bins = client.get(key)
                assert bins["v"] == i
                client.remove(key)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(cycle, range(100)))

        assert not errors, f"Errors in ThreadPoolExecutor test: {errors}"

    def test_multiple_clients_from_threads(self):
        """Each thread creates its own client, uses it, and closes it."""
        num_threads = 5
        errors = []

        def thread_fn(tid):
            try:
                c = aerospike_py.client(CONFIG).connect()
                for i in range(10):
                    key = (NS, SET_NAME, f"mcft_{tid}_{i}")
                    c.put(key, {"v": tid})
                    _, _, bins = c.get(key)
                    assert bins["v"] == tid
                    c.remove(key)
                c.close()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=thread_fn, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors with per-thread clients: {errors}"
