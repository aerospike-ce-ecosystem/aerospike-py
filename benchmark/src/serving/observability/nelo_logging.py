"""Structured logging via NELO (AsyncNeloHandler from pynelo).

NELO is Naver's centralised log collection platform.  When ``NELO_ENABLED``
is ``"false"`` (or ``PYNELO_TXT_TOKEN`` is missing), the handler is not
attached and the application falls back to standard Python logging.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("serving.observability")

_handler: object | None = None  # AsyncNeloHandler, kept for shutdown


def configure_logging(service_name: str = "aerospike-benchmark") -> None:
    """Attach ``AsyncNeloHandler`` to the *serving* and *benchmark* loggers.

    Controlled by environment variables:

    * ``NELO_ENABLED`` — ``"true"`` (default) or ``"false"``
    * ``PYNELO_TXT_TOKEN`` — NELO project token (**required** when enabled)
    * ``ENV`` — environment tag (default ``"dev"``)
    * ``POD_NAME`` — Kubernetes pod name (default ``"local"``)
    """
    global _handler

    nelo_enabled = os.environ.get("NELO_ENABLED", "true").lower() != "false"
    if not nelo_enabled:
        logger.info("NELO_ENABLED=false — skipping NELO handler setup")
        return

    txt_token = os.environ.get("PYNELO_TXT_TOKEN")
    if not txt_token:
        logger.warning(
            "PYNELO_TXT_TOKEN is not set — skipping NELO handler setup. "
            "Set the env var to enable centralised log collection."
        )
        return

    # Import here so the module loads even when pynelo is not installed
    from pynelo import AsyncNeloHandler

    env = os.environ.get("ENV", "dev")
    pod_name = os.environ.get("POD_NAME", "local")

    handler = AsyncNeloHandler(
        txt_token=txt_token,
        project_version="0.2.0",
        flush_interval=2.0,
        max_batch=100,
        fixed_extra_fields={
            "logSource": f"{service_name} | {env} | {pod_name}",
            "app_name": service_name,
        },
    )

    # Attach to both application loggers
    for logger_name in ("serving", "benchmark"):
        target = logging.getLogger(logger_name)
        target.addHandler(handler)

    _handler = handler
    logger.info("NELO logging configured (token=***%s)", txt_token[-4:] if len(txt_token) >= 4 else "****")


async def shutdown_logging() -> None:
    """Flush pending log batches and stop the async NELO handler."""
    if _handler is not None:
        try:
            await _handler.stop()  # type: ignore[union-attr]
        except Exception:
            logger.warning("Failed to shut down NELO handler", exc_info=True)

    logger.info("Logging shut down")
