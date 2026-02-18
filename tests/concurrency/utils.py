"""Shared utilities for concurrency tests."""


def _drain(q):
    """Drain all items from a SimpleQueue for error reporting."""
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items
