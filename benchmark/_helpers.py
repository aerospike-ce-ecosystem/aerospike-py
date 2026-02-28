"""Shared formatting helpers for benchmark scripts."""

from __future__ import annotations

import re


def _visible_len(s: str) -> int:
    """Return display width of string, ignoring ANSI escape codes."""
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _rpad(s: str, width: int) -> str:
    """Right-pad string to width, accounting for ANSI codes."""
    pad = width - _visible_len(s)
    return s + " " * max(0, pad)


def _lpad(s: str, width: int) -> str:
    """Left-pad string to width, accounting for ANSI codes."""
    pad = width - _visible_len(s)
    return " " * max(0, pad) + s


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "-"
    return f"{val:.3f}ms"
