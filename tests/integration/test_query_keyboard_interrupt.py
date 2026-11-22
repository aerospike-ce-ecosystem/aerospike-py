"""Ctrl-C during a sync query is raised, not lost.

Python delivers a signal to the first Python code the main thread runs after
the signal arrived. While the main thread is inside ``Query.results()`` or
``Query.foreach()``, that code used to be this library's own forwarding of a
log message to ``logging``. A logger has nobody to raise to, so the
``KeyboardInterrupt`` was dropped there like a failure of the logging call,
and a scan the user had interrupted ran to its end and returned normally.
0.14.x did the same.

The original interrupt is deferred when it lands in the logging bridge, so
it is raised in the next Python code that is not the bridge: the callback of
``foreach()``, which stops the scan there, or the caller's own code once
``results()`` has returned. ``results()`` itself is still not cut short.

Each case runs in a process of its own, because the signal has to go to a
main thread that is inside the query.
"""

import subprocess
import sys
import textwrap

import pytest

import aerospike_py
from tests import AEROSPIKE_CONFIG
from tests.server import skip_or_raise

NS = "test"
SET_NAME = "query_ctrl_c"
COUNT = 3000
# The server hands the records out at this rate, so the scan lasts about two
# seconds and the signal, sent 0.4 s in, arrives while it runs.
PER_SECOND = 1500

CHILD = textwrap.dedent(
    f"""
    import os
    import signal
    import sys
    import threading

    import aerospike_py

    client = aerospike_py.client({AEROSPIKE_CONFIG!r}).connect()
    seen = []


    def note(record):
        seen.append(record)


    threading.Timer(0.4, os.kill, (os.getpid(), signal.SIGINT)).start()
    try:
        query = client.query({NS!r}, {SET_NAME!r})
        if sys.argv[1] == "results":
            seen = query.results({{"records_per_second": {PER_SECOND}}})
        else:
            query.foreach(note, {{"records_per_second": {PER_SECOND}}})
        print("returned", len(seen))
    except KeyboardInterrupt:
        print("interrupted", len(seen))
    finally:
        client.close()
    """
)


@pytest.fixture(scope="module")
def seeded():
    try:
        client = aerospike_py.client(AEROSPIKE_CONFIG).connect()
    except Exception as e:
        skip_or_raise(e)
    keys = [(NS, SET_NAME, i) for i in range(COUNT)]
    client.batch_write([(key, {"v": key[2]}) for key in keys], policy={"total_timeout": 30_000})
    yield
    client.batch_remove(keys, policy={"total_timeout": 30_000})
    client.close()


def _interrupted_during(how: str) -> tuple[str, int]:
    child = subprocess.run([sys.executable, "-c", CHILD, how], capture_output=True, text=True, timeout=120, check=False)
    assert child.returncode == 0, child.stderr[-2000:]
    outcome, count = child.stdout.split()
    return outcome, int(count)


def test_results_raises_the_interrupt_when_it_returns(seeded):
    outcome, _ = _interrupted_during("results")

    assert outcome == "interrupted"


def test_foreach_is_stopped_by_the_interrupt(seeded):
    outcome, delivered = _interrupted_during("foreach")

    assert outcome == "interrupted"
    assert delivered < COUNT, "the interrupt was raised in the callback, which ends the scan"


def test_signal_handler_runs_once_when_interrupt_arrives_in_logging(seeded):
    script = textwrap.dedent(
        f"""
        import logging
        import os
        import signal
        import threading
        import aerospike_py

        client = aerospike_py.client({AEROSPIKE_CONFIG!r}).connect()
        received = []
        def interrupt(signum, frame):
            received.append(signum)
            raise KeyboardInterrupt("original interrupt")
        class InterruptDuringLog(logging.Handler):
            fired = False
            def emit(self, record):
                if not self.fired and threading.current_thread() is threading.main_thread():
                    self.fired = True
                    os.kill(os.getpid(), signal.SIGINT)
        log = logging.getLogger()
        handler = InterruptDuringLog()
        log.addHandler(handler)
        log.setLevel(1)
        signal.signal(signal.SIGINT, interrupt)
        try:
            client.get(({NS!r}, {SET_NAME!r}, 0))
        except KeyboardInterrupt as exc:
            assert exc.args == ("original interrupt",)
        else:
            raise AssertionError("interrupt lost")
        finally:
            log.removeHandler(handler)
            client.close()
        assert len(received) == 1, received
        """
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=30)
