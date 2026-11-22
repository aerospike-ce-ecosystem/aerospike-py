"""Internal bug report helper for unexpected errors in aerospike-py."""

from __future__ import annotations

import asyncio
import functools
import logging
import platform
import sys
import traceback

__all__ = ["log_unexpected_error", "catch_unexpected"]

logger = logging.getLogger("aerospike_py")

_REPO = "aerospike-ce-ecosystem/aerospike-py"


def _shell_escape(s: str) -> str:
    """Escape single quotes for shell single-quoted strings."""
    return s.replace("'", "'\\''")


def _sanitize_for_title(s: str) -> str:
    """Collapse all whitespace (incl. newlines) into single spaces.

    Mirrors the Rust-side ``sanitize_for_title`` so the gh issue title stays
    on a single line.
    """
    return " ".join(s.split())


def log_unexpected_error(context: str, exc: BaseException) -> None:
    """Log an unexpected error with a gh issue create command.

    Only call this for errors that are NOT expected Aerospike errors
    (i.e., not subclasses of AerospikeError).
    """
    from aerospike_py import __version__

    exc_type = type(exc).__name__
    exc_msg = str(exc)
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()

    title = _sanitize_for_title(f"Unexpected error: {exc_type}: {exc_msg}")[:80]
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


#: How an argument is refused. The native layer raises these on purpose — a
#: key of a type the server cannot store, a policy value of the wrong type —
#: and so does the argument parsing in front of it. They are the caller's to
#: fix: logging them as a possible bug in this library sent callers to the
#: issue tracker for their own typos.
_ARGUMENT_ERRORS = (TypeError, ValueError, OverflowError)


def _maybe_log(method_name: str, exc: Exception) -> None:
    """Log ``exc`` as a possible bug unless it is a failure a correct library produces.

    Those are ``AerospikeError`` (the cluster or the client said no) and the
    builtin ``TypeError`` / ``ValueError`` / ``OverflowError`` (an argument was
    refused; the last one for an integer that does not fit, ``retry=-1`` say).
    """
    from aerospike_py._aerospike import AerospikeError

    if not isinstance(exc, (AerospikeError, *_ARGUMENT_ERRORS)):
        log_unexpected_error(method_name, exc)


def catch_unexpected(method_name: str):
    """Decorator that catches unexpected errors and logs a bug report.

    ``AerospikeError`` subclasses and refused arguments (``TypeError``,
    ``ValueError``) pass through unmodified and unlogged. All other
    exceptions are logged with the bug report message, then re-raised as-is
    (so the caller still sees the original error).
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
