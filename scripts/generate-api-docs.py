#!/usr/bin/env python3
"""Generate Docusaurus API docs from .pyi stub docstrings.

Parses Google-style docstrings from type-stub files and produces
Markdown pages suitable for the Docusaurus docs site.

Usage:
    python scripts/generate-api-docs.py
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
STUB_PATH = ROOT / "src" / "aerospike_py" / "__init__.pyi"
DOCS_API_DIR = ROOT / "docs" / "docs" / "api"

AUTO_HEADER = "<!-- AUTO-GENERATED from .pyi docstrings. Do not edit manually. -->\n"


# ---------------------------------------------------------------------------
# Docstring parser
# ---------------------------------------------------------------------------


@dataclass
class ParsedDocstring:
    summary: str = ""
    args: list[tuple[str, str]] = field(default_factory=list)
    returns: str = ""
    raises: list[tuple[str, str]] = field(default_factory=list)
    example: str = ""


def _parse_google_docstring(doc: str | None) -> ParsedDocstring:
    """Parse a Google-style docstring into structured sections."""
    if not doc:
        return ParsedDocstring()

    lines = textwrap.dedent(doc).strip().splitlines()
    result = ParsedDocstring()

    # Collect summary (everything before the first section header)
    section = "summary"
    section_lines: list[str] = []
    current_item_name = ""
    current_item_lines: list[str] = []

    def _flush_item():
        nonlocal current_item_name, current_item_lines
        if current_item_name:
            desc = " ".join(current_item_lines).strip()
            if section == "args":
                result.args.append((current_item_name, desc))
            elif section == "raises":
                result.raises.append((current_item_name, desc))
        current_item_name = ""
        current_item_lines = []

    def _flush_section():
        nonlocal section, section_lines
        if section == "example":
            # Dedent before stripping to preserve relative indentation
            result.example = textwrap.dedent("\n".join(section_lines)).strip()
        else:
            text = "\n".join(section_lines).strip()
            if section == "summary":
                result.summary = text
            elif section == "returns":
                result.returns = text
        section_lines.clear()

    section_headers = {"Args:", "Returns:", "Raises:", "Example:"}
    section_map = {
        "Args:": "args",
        "Returns:": "returns",
        "Raises:": "raises",
        "Example:": "example",
    }

    for line in lines:
        stripped = line.strip()

        # Check for section header
        if stripped in section_headers:
            # Flush previous state
            _flush_item()
            _flush_section()
            section = section_map[stripped]
            continue

        if section in ("args", "raises"):
            # Check for new item: "name: description" or "Name: description"
            m = re.match(r"^\s{4,8}(\w+):\s*(.*)", line)
            if m:
                _flush_item()
                current_item_name = m.group(1)
                current_item_lines = [m.group(2)] if m.group(2) else []
            else:
                # Continuation line
                if current_item_name:
                    current_item_lines.append(stripped)
                else:
                    section_lines.append(line)
        else:
            section_lines.append(line)

    _flush_item()
    _flush_section()

    return result


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _get_method_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a human-readable signature string from an AST node."""
    args = node.args
    parts: list[str] = []

    # Positional args (skip 'self')
    all_args = args.args[:]
    defaults = list(args.defaults)
    # Pad defaults to align with args
    while len(defaults) < len(all_args):
        defaults.insert(0, None)  # type: ignore[arg-type]

    for arg, default in zip(all_args, defaults, strict=False):
        if arg.arg == "self":
            continue
        s = arg.arg
        if default is not None:
            s += f"={ast.literal_eval(default)}" if isinstance(default, ast.Constant) else "=..."
        parts.append(s)

    return ", ".join(parts)


def _is_async(node: ast.AST) -> bool:
    return isinstance(node, ast.AsyncFunctionDef)


@dataclass
class MethodInfo:
    name: str
    signature: str
    docstring: ParsedDocstring
    is_async: bool = False
    is_overload: bool = False


def _extract_methods(
    cls_node: ast.ClassDef,
    target_names: set[str] | None = None,
) -> list[MethodInfo]:
    """Extract methods from a class AST node."""
    methods: list[MethodInfo] = []
    seen_overloads: set[str] = set()

    for node in cls_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        name = node.name
        if name.startswith("_"):
            continue

        if target_names and name not in target_names:
            continue

        # Skip @overload decorated variants, keep the implementation
        decorators = [d.id if isinstance(d, ast.Name) else "" for d in node.decorator_list]
        if "overload" in decorators:
            seen_overloads.add(name)
            continue

        doc = ast.get_docstring(node)
        parsed = _parse_google_docstring(doc)
        sig = _get_method_signature(node)

        methods.append(
            MethodInfo(
                name=name,
                signature=sig,
                docstring=parsed,
                is_async=_is_async(node),
            )
        )

    return methods


def _extract_functions(
    tree: ast.Module,
    target_names: set[str] | None = None,
) -> list[MethodInfo]:
    """Extract top-level functions from the module."""
    functions: list[MethodInfo] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if name.startswith("_"):
            continue
        if target_names and name not in target_names:
            continue

        doc = ast.get_docstring(node)
        parsed = _parse_google_docstring(doc)
        sig = _get_method_signature(node)
        functions.append(
            MethodInfo(
                name=name,
                signature=sig,
                docstring=parsed,
                is_async=_is_async(node),
            )
        )
    return functions


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------


def _render_method_section(
    sync_method: MethodInfo | None,
    async_method: MethodInfo | None,
) -> str:
    """Render a Markdown section for a method with Sync/Async tabs."""
    method = sync_method or async_method
    if not method:
        return ""

    lines: list[str] = []
    ds = method.docstring
    name = method.name

    # Heading
    sig = method.signature
    lines.append(f"### `{name}({sig})`\n")

    # Summary
    if ds.summary:
        lines.append(ds.summary)
        lines.append("")

    # Args table
    if ds.args:
        lines.append("| Parameter | Description |")
        lines.append("|-----------|-------------|")
        for param_name, desc in ds.args:
            # Escape pipes in description
            desc_escaped = desc.replace("|", "\\|")
            lines.append(f"| `{param_name}` | {desc_escaped} |")
        lines.append("")

    # Returns
    if ds.returns:
        lines.append(f"**Returns:** {ds.returns}")
        lines.append("")

    # Raises
    if ds.raises:
        for exc_name, desc in ds.raises:
            lines.append(":::note\n")
            lines.append(f"Raises `{exc_name}` {desc}\n")
            lines.append(":::\n")

    # Examples with tabs
    if sync_method and async_method and sync_method.docstring.example and async_method.docstring.example:
        lines.append("<Tabs>")
        lines.append('  <TabItem value="sync" label="Sync Client" default>\n')
        lines.append(sync_method.docstring.example)
        lines.append("")
        lines.append("  </TabItem>")
        lines.append('  <TabItem value="async" label="Async Client">\n')
        lines.append(async_method.docstring.example)
        lines.append("")
        lines.append("  </TabItem>")
        lines.append("</Tabs>\n")
    elif ds.example:
        lines.append(ds.example)
        lines.append("")

    return "\n".join(lines)


def _render_standalone_section(method: MethodInfo) -> str:
    """Render a Markdown section for a standalone function."""
    lines: list[str] = []
    ds = method.docstring

    sig = method.signature
    lines.append(f"### `{method.name}({sig})`\n")

    if ds.summary:
        lines.append(ds.summary)
        lines.append("")

    if ds.args:
        lines.append("| Parameter | Description |")
        lines.append("|-----------|-------------|")
        for param_name, desc in ds.args:
            desc_escaped = desc.replace("|", "\\|")
            lines.append(f"| `{param_name}` | {desc_escaped} |")
        lines.append("")

    if ds.returns:
        lines.append(f"**Returns:** {ds.returns}")
        lines.append("")

    if ds.example:
        lines.append(ds.example)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------


# Methods to include in the generated client doc, grouped by section
CLIENT_METHOD_SECTIONS = [
    ("Connection", ["connect", "is_connected", "close", "get_node_names"]),
    ("Info", ["info_all", "info_random_node"]),
    ("CRUD Operations", ["put", "get", "select", "exists", "remove", "touch"]),
    ("String / Numeric Operations", ["append", "prepend", "increment", "remove_bin"]),
    ("Multi-Operation", ["operate", "operate_ordered"]),
    ("Batch Operations", ["batch_read", "batch_operate", "batch_remove"]),
    ("Query & Scan", ["query", "scan"]),
    ("Index Management", ["index_integer_create", "index_string_create", "index_geo2dsphere_create", "index_remove"]),
    ("Truncate", ["truncate"]),
    ("UDF", ["udf_put", "udf_remove", "apply"]),
]


def generate_client_doc(tree: ast.Module) -> str:
    """Generate the client.md API documentation."""
    # Find Client and AsyncClient classes
    classes: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in ("Client", "AsyncClient"):
            classes[node.name] = node

    sync_cls = classes.get("Client")
    async_cls = classes.get("AsyncClient")

    if not sync_cls:
        raise RuntimeError("Client class not found in stub")

    # Extract all methods
    sync_methods_list = _extract_methods(sync_cls)
    async_methods_list = _extract_methods(async_cls) if async_cls else []

    sync_methods = {m.name: m for m in sync_methods_list}
    async_methods = {m.name: m for m in async_methods_list}

    # Extract Query and Scan classes
    query_cls = None
    scan_cls = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name == "Query":
                query_cls = node
            elif node.name == "Scan":
                scan_cls = node

    # Extract factory functions
    factory_functions = _extract_functions(
        tree,
        {"client", "set_log_level", "get_metrics", "start_metrics_server", "stop_metrics_server"},
    )

    # Build document
    lines: list[str] = [
        AUTO_HEADER,
        "---",
        "title: Client",
        "sidebar_label: Client (Sync & Async)",
        "sidebar_position: 1",
        "description: Complete API reference for the synchronous Client and asynchronous AsyncClient classes.",
        "---\n",
        "import Tabs from '@theme/Tabs';",
        "import TabItem from '@theme/TabItem';\n",
        "aerospike-py provides both synchronous (`Client`) and asynchronous (`AsyncClient`) APIs with identical functionality.\n",
    ]

    # Factory functions
    lines.append("## Factory Functions\n")
    for func in factory_functions:
        lines.append(_render_standalone_section(func))

    # Client methods grouped by section
    for section_title, method_names in CLIENT_METHOD_SECTIONS:
        lines.append(f"## {section_title}\n")
        for name in method_names:
            sm = sync_methods.get(name)
            am = async_methods.get(name)
            if sm or am:
                lines.append(_render_method_section(sm, am))

    # Query class
    if query_cls:
        query_methods = _extract_methods(query_cls)
        lines.append("## Query Object\n")
        query_doc = ast.get_docstring(query_cls)
        if query_doc:
            parsed = _parse_google_docstring(query_doc)
            if parsed.summary:
                lines.append(parsed.summary)
                lines.append("")
            if parsed.example:
                lines.append(parsed.example)
                lines.append("")

        for m in query_methods:
            lines.append(_render_standalone_section(m))

    # Scan class
    if scan_cls:
        scan_methods = _extract_methods(scan_cls)
        lines.append("## Scan Object\n")
        scan_doc = ast.get_docstring(scan_cls)
        if scan_doc:
            parsed = _parse_google_docstring(scan_doc)
            if parsed.summary:
                lines.append(parsed.summary)
                lines.append("")
            if parsed.example:
                lines.append(parsed.example)
                lines.append("")

        for m in scan_methods:
            lines.append(_render_standalone_section(m))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: parse stubs and write Markdown files."""
    if not STUB_PATH.exists():
        print(f"ERROR: Stub file not found: {STUB_PATH}")
        raise SystemExit(1)

    source = STUB_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(STUB_PATH))

    # Ensure output directory exists
    DOCS_API_DIR.mkdir(parents=True, exist_ok=True)

    # Generate client.md
    client_md = generate_client_doc(tree)
    out_path = DOCS_API_DIR / "client.md"
    out_path.write_text(client_md, encoding="utf-8")
    print(f"Generated {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
