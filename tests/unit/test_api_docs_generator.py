"""Regression tests for the public-stub API documentation generator."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent.parent
STUB_PATH = ROOT / "src" / "aerospike_py" / "__init__.pyi"
GENERATOR_PATH = ROOT / "scripts" / "generate-api-docs.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_api_docs", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load API docs generator: {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()
TREE = ast.parse(STUB_PATH.read_text(encoding="utf-8"), filename=str(STUB_PATH))


def _public_methods(class_name: str) -> set[str]:
    for node in TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_")
            }
    return set()


def test_generated_reference_covers_public_stub_inventory() -> None:
    """Every public function and relevant class method gets an API heading."""
    rendered = GENERATOR.generate_client_doc(TREE)

    expected = Counter(
        node.name
        for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    )
    expected.update(_public_methods("Client") | _public_methods("AsyncClient"))
    expected.update(_public_methods("Query") | _public_methods("AsyncQuery"))

    headings = Counter(re.findall(r"^### `([A-Za-z_]\w*)\(", rendered, flags=re.MULTILINE))
    assert headings == expected


def test_previously_omitted_api_groups_are_explicit() -> None:
    """Guard the client, async query, observability, and partition regressions."""
    rendered = GENERATOR.generate_client_doc(TREE)

    required_markers = [
        "### `ping()`",
        "### `admin_create_user(username, password, roles, policy=None)`",
        "### `admin_set_quotas(role, read_quota=0, write_quota=0, policy=None)`",
        "### `async_client(config)`",
        "## Query and AsyncQuery Objects",
        'label="AsyncQuery"',
        "### `set_metrics_enabled(enabled)`",
        "### `internal_stage_profiling()`",
        "### `init_tracing()`",
        "### `partition_filter_by_range(begin, count)`",
    ]
    for marker in required_markers:
        assert marker in rendered


def test_varargs_and_raises_render_without_losing_stub_details() -> None:
    """Signatures and Google-style sections retain useful call details."""
    rendered = GENERATOR.generate_client_doc(TREE)

    assert "### `select(*bins)`" in rendered
    assert "| `*bins` | Bin names to include in the results. |" in rendered
    assert "Raises `ValueError` If ``partition_id`` is outside the valid range." in rendered


def test_markdown_note_inside_argument_is_not_a_fake_parameter() -> None:
    """A bold ``**Note:**`` inside retry's prose stays in the retry cell."""
    rendered = GENERATOR.generate_client_doc(TREE)

    assert "| `**Note` |" not in rendered
    assert rendered.count("**Note:** If a transport error occurs during retry") == 2
    assert "| `retry` | Maximum number of retries" in rendered


def test_note_section_ends_example_and_normalizes_sphinx_method_reference() -> None:
    """batch_apply's trailing Note renders separately from its fenced example."""
    rendered = GENERATOR.generate_client_doc(TREE)
    start = rendered.index("### `batch_apply(")
    end = rendered.index("\n## Query", start)
    batch_apply = rendered[start:end]

    assert "\n:::note\n" in batch_apply
    assert "(unlike `batch_write()`, which accepts ``retry: int = 0``)." in batch_apply
    assert "\n```python\n# Apply the same UDF" in batch_apply
    assert "\n    Note:" not in batch_apply
    assert ":meth:" not in rendered


def test_plural_notes_section_is_supported() -> None:
    """Google-style ``Notes:`` receives the same handling as ``Note:``."""
    parsed = GENERATOR._parse_google_docstring(
        "Summary.\n\nNotes:\n    Reuse :meth:`~Client.batch_write` only for idempotent writes."
    )

    assert parsed.summary == "Summary."
    assert parsed.notes == ["Reuse `batch_write()` only for idempotent writes."]
