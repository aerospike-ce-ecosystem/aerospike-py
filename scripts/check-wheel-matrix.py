#!/usr/bin/env python3
"""Fail a release build whose wheel matrix has holes in it.

`maturin --find-interpreter` builds whatever interpreters happen to be on
PATH: it never complains about the ones it did not find. Releases 0.13.0
through 0.14.2 shipped with no `cp314-cp314-macosx_*` wheel (the free-threaded
3.14t install shadowed `python3.14`) and with a single `cp314-cp314-win_amd64`
wheel (the Windows step did not pass `--find-interpreter`), so users on those
interpreters silently fell back to the sdist and needed a Rust toolchain.

Running this after each build step turns that into a red job instead.

Usage:
    python scripts/check-wheel-matrix.py dist [--platform linux|macos|windows]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# CPython minors advertised in pyproject.toml's classifiers and installed by
# the `Set up Python` step of .github/workflows/publish.yaml.
GIL_MINORS = (10, 11, 12, 13, 14)

# Free-threaded builds. actions/python-versions publishes no win-x64 build of
# 3.14t, so Windows is exempt.
FREE_THREADED_MINORS = (14,)

PLATFORMS = ("linux", "macos", "windows")


def expected_tags(platform: str) -> list[str]:
    """Return the `<python tag>-<abi tag>` pairs a wheel build must produce."""
    tags = [f"cp3{minor}-cp3{minor}" for minor in GIL_MINORS]
    if platform != "windows":
        tags += [f"cp3{minor}-cp3{minor}t" for minor in FREE_THREADED_MINORS]
    return tags


def wheel_tag(filename: str) -> str | None:
    """Return the `<python tag>-<abi tag>` pair of a wheel filename, if any."""
    if not filename.endswith(".whl"):
        return None
    # {name}-{version}[-{build}]-{python}-{abi}-{platform}.whl
    parts = filename.removesuffix(".whl").split("-")
    if len(parts) < 5:
        return None
    return f"{parts[-3]}-{parts[-2]}"


def detect_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def missing_tags(dist_dir: Path, platform: str) -> list[str]:
    """Return the expected tags that `dist_dir` has no wheel for."""
    found = {tag for tag in (wheel_tag(path.name) for path in dist_dir.glob("*.whl")) if tag is not None}
    return [tag for tag in expected_tags(platform) if tag not in found]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dist", type=Path, nargs="?", default=Path("dist"), help="directory holding the built wheels")
    parser.add_argument(
        "--platform",
        choices=PLATFORMS,
        default=None,
        help="platform whose matrix to check (default: detected from the host)",
    )
    args = parser.parse_args(argv)

    platform = args.platform or detect_platform()
    built = sorted(path.name for path in args.dist.glob("*.whl"))

    print(f"Checking the {platform} wheel matrix in {args.dist}:")
    for name in built:
        print(f"  {name}")
    if not built:
        print("  (no wheels)")

    missing = missing_tags(args.dist, platform)
    if missing:
        print(f"::error::{platform} wheel matrix is incomplete — missing {', '.join(missing)}")
        print("Every interpreter in pyproject.toml's classifiers needs a wheel; otherwise")
        print("`pip install aerospike-py` falls back to the sdist and requires a Rust toolchain.")
        return 1

    print(f"All {len(expected_tags(platform))} expected {platform} wheel tags are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
