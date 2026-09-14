"""Regression tests for the release wheel matrix.

`publish.yaml` builds wheels with `maturin --find-interpreter`, which silently
ships whatever interpreters happen to be on PATH. Two real releases' worth of
wheels went missing that way (no `cp314-cp314-macosx_*` because the 3.14t
install shadowed `python3.14`, and a single `cp314-cp314-win_amd64` because the
Windows step never passed `--find-interpreter`), so these tests pin both the
workflow invariants and the guard script that fails a release with holes in it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish.yaml"
GUARD_PATH = ROOT / "scripts" / "check-wheel-matrix.py"


def _load_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_wheel_matrix", GUARD_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load wheel matrix guard: {GUARD_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# publish.yaml invariants
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def test_every_maturin_build_step_finds_all_interpreters(workflow_text: str) -> None:
    """Windows built a single wheel because its step lacked --find-interpreter."""
    build_args = [
        line.strip() for line in workflow_text.splitlines() if line.strip().startswith("args: --release --out dist")
    ]
    assert len(build_args) == 3, f"expected Linux/macOS/Windows build steps, got {build_args}"
    missing = [args for args in build_args if "--find-interpreter" not in args]
    assert not missing, f"maturin build step(s) without --find-interpreter: {missing}"


def test_free_threaded_python_is_installed_before_the_gil_interpreters(workflow_text: str) -> None:
    """3.14t must not shadow `python3.14` on PATH.

    actions/setup-python prepends each install to PATH, and the free-threaded
    framework symlinks `python3.14 -> python3.14t`. Installing 3.14t *first*
    leaves the GIL 3.14 ahead of it, so `--find-interpreter` resolves both.
    """
    free_threaded_at = workflow_text.find("python-version: 3.14t")
    multi_version_at = workflow_text.find("python-version: |")
    assert free_threaded_at != -1, "no 3.14t setup-python step in publish.yaml"
    assert multi_version_at != -1, "no multi-version setup-python step in publish.yaml"
    assert free_threaded_at < multi_version_at, (
        "the 3.14t setup-python step must come before the 3.10-3.14 step, "
        "otherwise python3.14 resolves to the free-threaded build and no "
        "cp314-cp314 macOS wheel is produced"
    )


def test_build_job_guards_the_wheel_matrix(workflow_text: str) -> None:
    """A release with missing wheels must fail the build job, not ship."""
    assert "scripts/check-wheel-matrix.py" in workflow_text, (
        "publish.yaml must run scripts/check-wheel-matrix.py after building wheels"
    )


# ---------------------------------------------------------------------------
# scripts/check-wheel-matrix.py
# ---------------------------------------------------------------------------


def _write_wheels(directory: Path, filenames: list[str]) -> None:
    for name in filenames:
        (directory / name).write_bytes(b"")


def _macos_wheels(*, include_gil_314: bool) -> list[str]:
    names = [f"aerospike_py-0.14.2-cp3{minor}-cp3{minor}-macosx_11_0_arm64.whl" for minor in (10, 11, 12, 13)]
    if include_gil_314:
        names.append("aerospike_py-0.14.2-cp314-cp314-macosx_11_0_arm64.whl")
    names.append("aerospike_py-0.14.2-cp314-cp314t-macosx_11_0_arm64.whl")
    return names


def test_wheel_tag_parses_python_and_abi_tags() -> None:
    guard = _load_guard()
    assert guard.wheel_tag("aerospike_py-0.14.2-cp314-cp314t-macosx_11_0_arm64.whl") == "cp314-cp314t"
    assert guard.wheel_tag("aerospike_py-0.14.2-cp310-cp310-manylinux_2_28_x86_64.whl") == "cp310-cp310"
    assert guard.wheel_tag("aerospike_py-0.14.2.tar.gz") is None


def test_guard_rejects_the_macos_release_that_lost_its_gil_314_wheel(tmp_path: Path) -> None:
    """The exact shape of PyPI 0.13.0-0.14.2: cp314t but no cp314 on macOS."""
    guard = _load_guard()
    _write_wheels(tmp_path, _macos_wheels(include_gil_314=False))
    assert guard.missing_tags(tmp_path, "macos") == ["cp314-cp314"]


def test_guard_accepts_a_complete_macos_matrix(tmp_path: Path) -> None:
    guard = _load_guard()
    _write_wheels(tmp_path, _macos_wheels(include_gil_314=True))
    assert guard.missing_tags(tmp_path, "macos") == []


def test_guard_rejects_the_single_wheel_windows_release(tmp_path: Path) -> None:
    """The exact shape of PyPI 0.13.0-0.14.2: only cp314 on Windows."""
    guard = _load_guard()
    _write_wheels(tmp_path, ["aerospike_py-0.14.2-cp314-cp314-win_amd64.whl"])
    assert guard.missing_tags(tmp_path, "windows") == [
        "cp310-cp310",
        "cp311-cp311",
        "cp312-cp312",
        "cp313-cp313",
    ]


def test_guard_does_not_demand_a_free_threaded_wheel_on_windows(tmp_path: Path) -> None:
    """3.14t has no official windows-x64 build in actions/python-versions."""
    guard = _load_guard()
    _write_wheels(
        tmp_path,
        [f"aerospike_py-0.14.2-cp3{minor}-cp3{minor}-win_amd64.whl" for minor in (10, 11, 12, 13, 14)],
    )
    assert guard.missing_tags(tmp_path, "windows") == []


def test_guard_tolerates_extra_interpreters(tmp_path: Path) -> None:
    """manylinux images also carry 3.15/3.15t and PyPy; extras are not failures."""
    guard = _load_guard()
    _write_wheels(
        tmp_path,
        [
            *(f"aerospike_py-0.14.2-cp3{minor}-cp3{minor}-manylinux_2_28_x86_64.whl" for minor in (10, 11, 12, 13, 14)),
            "aerospike_py-0.14.2-cp314-cp314t-manylinux_2_28_x86_64.whl",
            "aerospike_py-0.14.2-cp315-cp315-manylinux_2_28_x86_64.whl",
            "aerospike_py-0.14.2-cp315-cp315t-manylinux_2_28_x86_64.whl",
            "aerospike_py-0.14.2-pp311-pypy311_pp73-manylinux_2_28_x86_64.whl",
        ],
    )
    assert guard.missing_tags(tmp_path, "linux") == []


def test_guard_main_exits_non_zero_when_wheels_are_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    guard = _load_guard()
    _write_wheels(tmp_path, _macos_wheels(include_gil_314=False))

    assert guard.main([str(tmp_path), "--platform", "macos"]) == 1
    assert "cp314-cp314" in capsys.readouterr().out

    _write_wheels(tmp_path, ["aerospike_py-0.14.2-cp314-cp314-macosx_11_0_arm64.whl"])
    assert guard.main([str(tmp_path), "--platform", "macos"]) == 0


def test_guard_main_fails_on_an_empty_dist_directory(tmp_path: Path) -> None:
    guard = _load_guard()
    assert guard.main([str(tmp_path), "--platform", "linux"]) == 1
