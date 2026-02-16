"""Validate that Python code examples in .pyi docstrings are syntactically correct.

This test extracts fenced code blocks from docstrings and verifies
they can be compiled by Python's ``compile()`` built-in — no Aerospike
server required.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
STUB_PATH = ROOT / "src" / "aerospike_py" / "__init__.pyi"

# Regex matching fenced code blocks: ```python ... ```
_CODE_BLOCK_RE = re.compile(
    r"```python\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_code_examples(source: str) -> list[tuple[str, str]]:
    """Return a list of ``(location, code)`` tuples from all docstrings."""
    tree = ast.parse(source)
    examples: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if not doc:
                continue

            # Build a human-readable location
            location = f"class {node.name}" if isinstance(node, ast.ClassDef) else f"def {node.name}"

            for i, m in enumerate(_CODE_BLOCK_RE.finditer(doc)):
                code = textwrap.dedent(m.group(1)).strip()
                label = f"{location} (example {i + 1})" if i > 0 else location
                examples.append((label, code))

    return examples


# ---------------------------------------------------------------------------
# Collect all examples once at import time for parametrization
# ---------------------------------------------------------------------------

_EXAMPLES: list[tuple[str, str]] = []
if STUB_PATH.exists():
    _source = STUB_PATH.read_text(encoding="utf-8")
    _EXAMPLES = _extract_code_examples(_source)


@pytest.mark.parametrize(
    "location,code",
    _EXAMPLES,
    ids=[loc for loc, _ in _EXAMPLES],
)
def test_docstring_example_syntax(location: str, code: str) -> None:
    """Each docstring code example must be valid Python syntax."""
    source = code
    # If the code contains await expressions, wrap it in an async function
    # so that compile() accepts the syntax.
    if "await " in code:
        indented = textwrap.indent(code, "    ")
        source = f"async def _test_wrapper():\n{indented}"
    try:
        compile(source, f"<docstring: {location}>", "exec")
    except SyntaxError as exc:
        pytest.fail(f"Syntax error in {location}:\n{exc}\n\nCode:\n{code}")
