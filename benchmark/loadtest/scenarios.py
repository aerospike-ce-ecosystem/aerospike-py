"""Scenario id → one-line description.

The id strings here match the `--scenario` value passed to
``loadtest/run_oha.sh`` (which is also the key written into ``meta.json``).
Keep these lines short — they render as section headers in the report.
"""

from __future__ import annotations

SCENARIO_DESCRIPTIONS: dict[str, str] = {
    "s1": (
        "Read-only — `batch_read(N keys)` → JSON count. "
        "Isolates pure ASGI + DB round trip; no ML, no per-record materialisation. "
        "Most direct measure of the `asyncio.to_thread` hop cost the official client pays."
    ),
    "s2": (
        "Dict-path inference — `batch_read` → Python dict iteration → "
        "`torch.tensor(rows)` → DLRM forward. "
        "Common FastAPI ML pattern; both clients pay per-record dict access."
    ),
    "s3": (
        "Numpy-path inference — aerospike-py: `to_numpy(dtype)` zero-copy structured array → "
        "`view(float32).reshape(-1, 64)` → `torch.from_numpy` → DLRM. "
        "Official client has no equivalent; falls back to per-bin matrix copy. "
        "Pair with S2 to see the zero-copy gain isolated from inference cost."
    ),
    "s4_gather": (
        "Fan-out — `asyncio.gather(N batch_reads)`. "
        "N concurrent DB round trips. aerospike-py's native async overlaps them; "
        "the official client serialises through `asyncio.to_thread`."
    ),
    "s4_single": (
        "Single batch_read — same N×per_group keys collapsed into ONE call. "
        "Same wire payload as S4 gather but one round trip; measures fixed-cost amortisation."
    ),
    "s5": (
        "Lazy subset — 8 of 64 bins consumed downstream. "
        "aerospike-py: `to_numpy(subset_dtype)` materialises only the 8 needed columns. "
        "Official client: every record arrives as a fully-materialised 64-key Python dict; "
        "subset access is free but the up-front dict build is unavoidable."
    ),
}
