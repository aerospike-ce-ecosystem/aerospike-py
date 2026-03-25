"""Global Aerospike exception → HTTP status mapping.

Registers FastAPI exception handlers so that Aerospike-specific errors
are translated into appropriate HTTP responses without duplicating
try/except blocks in every router.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aerospike_py.exception import (
    AerospikeError,
    AerospikeTimeoutError,
    BackpressureError,
    BinNameError,
    ClientError,
    ClusterError,
    FilteredOut,
    InvalidArgError,
    RecordExistsError,
    RecordGenerationError,
    RecordNotFound,
    RecordTooBig,
)

logger = logging.getLogger("aerospike_py.fastapi")

_STATUS_MAP: dict[type, int] = {
    RecordNotFound: 404,
    RecordExistsError: 409,
    RecordGenerationError: 409,
    InvalidArgError: 400,
    BinNameError: 400,
    RecordTooBig: 413,
    FilteredOut: 412,
    BackpressureError: 503,
    AerospikeTimeoutError: 504,
    ClusterError: 503,
    ClientError: 502,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Register a catch-all handler for :class:`AerospikeError`."""

    @app.exception_handler(AerospikeError)
    async def _handle_aerospike_error(request: Request, exc: AerospikeError) -> JSONResponse:
        status = _STATUS_MAP.get(type(exc), 500)
        detail = str(exc)

        if status >= 500:
            logger.error("Aerospike error (HTTP %d): %s", status, detail)
        else:
            logger.debug("Aerospike error (HTTP %d): %s", status, detail)

        return JSONResponse(status_code=status, content={"detail": detail})
