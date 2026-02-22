"""Internal bug report helper for unexpected errors in aerospike-py."""

from __future__ import annotations

import asyncio
import functools
import logging
import platform
import sys
import traceback

logger = logging.getLogger("aerospike_py")

_REPO = "KimSoungRyoul/aerospike-py"


def _shell_escape(s: str) -> str:
    """Escape single quotes for shell single-quoted strings."""
    return s.replace("'", "'\\''")


def log_unexpected_error(context: str, exc: BaseException) -> None:
    """Log an unexpected error with a gh issue create command.

    Only call this for errors that are NOT expected Aerospike errors
    (i.e., not subclasses of AerospikeError).
    """
    from aerospike_py import __version__

    exc_type = type(exc).__name__
    exc_msg = str(exc)
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()

    title = f"Unexpected error: {exc_type}: {exc_msg[:80]}"
    body = (
        f"aerospike-py version: {__version__}\n"
        f"Python: {sys.version}\n"
        f"Platform: {platform.platform()}\n"
        f"Context: {context}\n"
        f"Error: {exc_type}: {exc_msg}\n\n"
        f"Traceback:\n```\n{tb_str}\n```"
    )

    logger.error(
        "Unexpected internal error in aerospike-py (%s): %s: %s\n"
        "\n"
        "This error may be a bug in aerospike-py. Please report it by running:\n"
        "gh issue create --repo %s --title '%s' --body '%s'",
        context,
        exc_type,
        exc_msg,
        _REPO,
        _shell_escape(title),
        _shell_escape(body),
    )


def _maybe_log(method_name: str, exc: Exception) -> None:
    """Log if exc is NOT an expected AerospikeError."""
    from aerospike_py._aerospike import AerospikeError

    if not isinstance(exc, AerospikeError):
        log_unexpected_error(method_name, exc)


def catch_unexpected(method_name: str):
    """Decorator that catches unexpected errors and logs a bug report.

    Expected AerospikeError subclasses pass through unmodified.
    All other exceptions are logged with the bug report message,
    then re-raised as-is (so the caller still sees the original error).
    """

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    _maybe_log(method_name, exc)
                    raise

            return async_wrapper
        else:

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    _maybe_log(method_name, exc)
                    raise

            return wrapper

    return decorator
