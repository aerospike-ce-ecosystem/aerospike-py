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
    notes: list[str] = field(default_factory=list)


_SPHINX_ROLE_RE = re.compile(r":(?P<role>meth|func|class|attr):`(?P<short>~?)(?P<target>[^`]+)`")


def _normalize_sphinx_roles(text: str) -> str:
    """Convert common Sphinx cross-references into readable Markdown code."""

    def _replace(match: re.Match[str]) -> str:
        target = match.group("target")
        display = target.rsplit(".", 1)[-1] if match.group("short") else target
        if match.group("role") in ("meth", "func") and not display.endswith("()"):
            display += "()"
        return f"`{display}`"

    return _SPHINX_ROLE_RE.sub(_replace, text)


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
            desc = _normalize_sphinx_roles(" ".join(part for part in current_item_lines if part).strip())
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
            text = _normalize_sphinx_roles(textwrap.dedent("\n".join(section_lines)).strip())
            if section == "summary":
                result.summary = text
            elif section == "returns":
                result.returns = text
            elif section == "notes" and text:
                result.notes.append(text)
        section_lines.clear()

    section_headers = {"Args:", "Returns:", "Raises:", "Example:", "Note:", "Notes:"}
    section_map = {
        "Args:": "args",
        "Returns:": "returns",
        "Raises:": "raises",
        "Example:": "example",
        "Note:": "notes",
        "Notes:": "notes",
    }

    for line in lines:
        stripped = line.strip()

        # Check for section header
        # Google-style section headers are top-level after dedenting. An
        # indented ``Note:`` can still be ordinary parameter prose.
        if not line[:1].isspace() and stripped in section_headers:
            # Flush previous state
            _flush_item()
            _flush_section()
            section = section_map[stripped]
            continue

        if section in ("args", "raises"):
            # Check for new item: "name: description" or "Name: description"
            # Requiring whitespace (or EOL) after the colon prevents Markdown
            # labels such as ``**Note:**`` from becoming fake parameters.
            m = re.match(r"^\s{4,8}([*]{0,2}\w+):(?:\s+(.*)|\s*$)", line)
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

    def _format_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
        rendered = arg.arg
        if default is not None:
            rendered += f"={ast.unparse(default)}"
        return rendered

    # Defaults align to the right across positional-only and positional args.
    positional_args = [*args.posonlyargs, *args.args]
    default_offset = len(positional_args) - len(args.defaults)
    for index, arg in enumerate(positional_args):
        if arg.arg == "self":
            continue
        default = args.defaults[index - default_offset] if index >= default_offset else None
        parts.append(_format_arg(arg, default))
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            parts.append("/")

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parts.append(_format_arg(arg, default))

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

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


def _render_notes(notes: list[str]) -> list[str]:
    """Render parsed Note/Notes sections as Docusaurus admonitions."""
    lines: list[str] = []
    for note in notes:
        lines.append(":::note\n")
        lines.append(f"{note}\n")
        lines.append(":::\n")
    return lines


def _render_method_section(
    sync_method: MethodInfo | None,
    async_method: MethodInfo | None,
    *,
    sync_label: str = "Sync Client",
    async_label: str = "Async Client",
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
    summary = ds.summary or METHOD_FALLBACK_SUMMARIES.get(name, "")
    if summary:
        lines.append(summary)
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

    lines.extend(_render_notes(ds.notes))

    # Examples with tabs
    if sync_method and async_method and sync_method.docstring.example and async_method.docstring.example:
        lines.append("<Tabs>")
        lines.append(f'  <TabItem value="sync" label="{sync_label}" default>\n')
        lines.append(sync_method.docstring.example)
        lines.append("")
        lines.append("  </TabItem>")
        lines.append(f'  <TabItem value="async" label="{async_label}">\n')
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

    if ds.raises:
        for exc_name, desc in ds.raises:
            lines.append(":::note\n")
            lines.append(f"Raises `{exc_name}` {desc}\n")
            lines.append(":::\n")

    lines.extend(_render_notes(ds.notes))

    if ds.example:
        lines.append(ds.example)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------


# Methods to include in the generated client doc, grouped by section
CLIENT_METHOD_SECTIONS = [
    ("Connection", ["connect", "is_connected", "ping", "close", "get_node_names"]),
    ("Info", ["info_all", "info_random_node"]),
    ("CRUD Operations", ["put", "get", "select", "exists", "remove", "touch"]),
    ("String / Numeric Operations", ["append", "prepend", "increment", "remove_bin"]),
    ("Multi-Operation", ["operate", "operate_ordered"]),
    (
        "Batch Operations",
        ["batch_read", "batch_write", "batch_write_numpy", "batch_operate", "batch_remove", "batch_apply"],
    ),
    ("Query", ["query"]),
    ("Index Management", ["index_integer_create", "index_string_create", "index_geo2dsphere_create", "index_remove"]),
    ("Truncate", ["truncate"]),
    ("UDF", ["udf_put", "udf_remove", "apply"]),
    (
        "User Administration",
        [
            "admin_create_user",
            "admin_drop_user",
            "admin_change_password",
            "admin_grant_roles",
            "admin_revoke_roles",
            "admin_query_user_info",
            "admin_query_users_info",
        ],
    ),
    (
        "Role Administration",
        [
            "admin_create_role",
            "admin_drop_role",
            "admin_grant_privileges",
            "admin_revoke_privileges",
            "admin_query_role",
            "admin_query_roles",
            "admin_set_whitelist",
            "admin_set_quotas",
        ],
    ),
]


MODULE_FUNCTION_SECTIONS = [
    ("Factory Functions", ["client", "async_client"]),
    (
        "Partition Filter Helpers",
        ["partition_filter_all", "partition_filter_by_id", "partition_filter_by_range"],
    ),
    ("Logging", ["set_log_level", "dropped_log_count"]),
    (
        "Metrics",
        [
            "get_metrics",
            "set_metrics_enabled",
            "is_metrics_enabled",
            "set_internal_stage_metrics_enabled",
            "is_internal_stage_metrics_enabled",
            "internal_stage_profiling",
            "start_metrics_server",
            "stop_metrics_server",
        ],
    ),
    ("Tracing", ["init_tracing", "shutdown_tracing"]),
]


# The admin methods currently have signatures but no docstrings in the public
# stub. Keep their generated reference useful until those docstrings are added.
METHOD_FALLBACK_SUMMARIES = {
    "admin_create_user": "Create a user with the supplied password and roles.",
    "admin_drop_user": "Delete a user.",
    "admin_change_password": "Change a user's password.",
    "admin_grant_roles": "Grant roles to a user.",
    "admin_revoke_roles": "Revoke roles from a user.",
    "admin_query_user_info": "Return information about one user.",
    "admin_query_users_info": "Return information about all users.",
    "admin_create_role": "Create a role with privileges and optional access limits.",
    "admin_drop_role": "Delete a role.",
    "admin_grant_privileges": "Grant privileges to a role.",
    "admin_revoke_privileges": "Revoke privileges from a role.",
    "admin_query_role": "Return information about one role.",
    "admin_query_roles": "Return information about all roles.",
    "admin_set_whitelist": "Set the network allowlist for a role.",
    "admin_set_quotas": "Set read and write quotas for a role.",
}


def _ordered_method_names(*method_lists: list[MethodInfo]) -> list[str]:
    """Return the public method-name union while preserving stub order."""
    names: list[str] = []
    for methods in method_lists:
        for method in methods:
            if method.name not in names:
                names.append(method.name)
    return names


def _append_grouped_methods(
    lines: list[str],
    sections: list[tuple[str, list[str]]],
    sync_methods: dict[str, MethodInfo],
    async_methods: dict[str, MethodInfo],
    ordered_names: list[str],
) -> set[str]:
    """Render configured sections and a fallback section for new stub methods."""
    rendered: set[str] = set()
    for section_title, method_names in sections:
        available = [name for name in method_names if name in sync_methods or name in async_methods]
        if not available:
            continue
        lines.append(f"## {section_title}\n")
        for name in available:
            lines.append(_render_method_section(sync_methods.get(name), async_methods.get(name)))
            rendered.add(name)

    # A new public method must never disappear merely because the curated
    # section list has not been updated yet.
    ungrouped = [name for name in ordered_names if name not in rendered]
    if ungrouped:
        lines.append("## Other Client Methods\n")
        for name in ungrouped:
            lines.append(_render_method_section(sync_methods.get(name), async_methods.get(name)))
            rendered.add(name)

    return rendered


def _append_grouped_functions(
    lines: list[str],
    functions: list[MethodInfo],
    sections: list[tuple[str, list[str]]],
) -> set[str]:
    """Render every public module function, grouped for navigation."""
    functions_by_name = {function.name: function for function in functions}
    rendered: set[str] = set()
    for section_title, function_names in sections:
        available = [name for name in function_names if name in functions_by_name]
        if not available:
            continue
        lines.append(f"## {section_title}\n")
        for name in available:
            lines.append(_render_standalone_section(functions_by_name[name]))
            rendered.add(name)

    ungrouped = [function for function in functions if function.name not in rendered]
    if ungrouped:
        lines.append("## Other Module Helpers\n")
        for function in ungrouped:
            lines.append(_render_standalone_section(function))
            rendered.add(function.name)

    return rendered


def _validate_inventory(category: str, expected: set[str], rendered: set[str]) -> None:
    """Fail generation rather than silently dropping a public API symbol."""
    missing = expected - rendered
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise RuntimeError(f"Generated {category} reference is missing: {missing_names}")


def generate_client_doc(tree: ast.Module) -> str:
    """Generate the client.md API documentation."""
    # Types and exceptions have dedicated API pages and are intentionally
    # outside this generator's inventory.
    classes: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in ("Client", "AsyncClient", "Query", "AsyncQuery"):
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

    query_cls = classes.get("Query")
    async_query_cls = classes.get("AsyncQuery")
    query_methods_list = _extract_methods(query_cls) if query_cls else []
    async_query_methods_list = _extract_methods(async_query_cls) if async_query_cls else []
    query_methods = {m.name: m for m in query_methods_list}
    async_query_methods = {m.name: m for m in async_query_methods_list}

    # Extract every public module function. Curated groups control placement;
    # the fallback group keeps future stub additions visible.
    module_functions = _extract_functions(tree)
    factory_names = set(MODULE_FUNCTION_SECTIONS[0][1])
    factory_functions = [function for function in module_functions if function.name in factory_names]
    helper_functions = [function for function in module_functions if function.name not in factory_names]

    # Build document
    lines: list[str] = [
        "---",
        "title: Client",
        "sidebar_label: Client (Sync & Async)",
        "sidebar_position: 1",
        "description: Complete API reference for the synchronous Client and asynchronous AsyncClient classes.",
        "---\n",
        AUTO_HEADER,
        "import Tabs from '@theme/Tabs';",
        "import TabItem from '@theme/TabItem';\n",
        "aerospike-py provides both synchronous (`Client`) and asynchronous (`AsyncClient`) APIs with identical functionality.\n",
    ]

    rendered_functions = _append_grouped_functions(lines, factory_functions, MODULE_FUNCTION_SECTIONS[:1])

    # Client methods grouped by section
    rendered_client_methods = _append_grouped_methods(
        lines,
        CLIENT_METHOD_SECTIONS,
        sync_methods,
        async_methods,
        _ordered_method_names(sync_methods_list, async_methods_list),
    )

    # Pair Query and AsyncQuery so shared semantics stay together while their
    # sync/await examples remain explicit.
    rendered_query_methods: set[str] = set()
    if query_cls or async_query_cls:
        lines.append("## Query and AsyncQuery Objects\n")
        primary_query_cls = query_cls or async_query_cls
        assert primary_query_cls is not None
        parsed_class_doc = _parse_google_docstring(ast.get_docstring(primary_query_cls))
        if parsed_class_doc.summary:
            lines.append(parsed_class_doc.summary)
            lines.append("")

        sync_class_doc = _parse_google_docstring(ast.get_docstring(query_cls)) if query_cls else ParsedDocstring()
        async_class_doc = (
            _parse_google_docstring(ast.get_docstring(async_query_cls)) if async_query_cls else ParsedDocstring()
        )
        if sync_class_doc.example and async_class_doc.example:
            lines.append("<Tabs>")
            lines.append('  <TabItem value="query" label="Query" default>\n')
            lines.append(sync_class_doc.example)
            lines.append("")
            lines.append("  </TabItem>")
            lines.append('  <TabItem value="async-query" label="AsyncQuery">\n')
            lines.append(async_class_doc.example)
            lines.append("")
            lines.append("  </TabItem>")
            lines.append("</Tabs>\n")
        elif parsed_class_doc.example:
            lines.append(parsed_class_doc.example)
            lines.append("")

        for name in _ordered_method_names(query_methods_list, async_query_methods_list):
            lines.append(
                _render_method_section(
                    query_methods.get(name),
                    async_query_methods.get(name),
                    sync_label="Query",
                    async_label="AsyncQuery",
                )
            )
            rendered_query_methods.add(name)

    rendered_functions.update(_append_grouped_functions(lines, helper_functions, MODULE_FUNCTION_SECTIONS[1:]))

    _validate_inventory(
        "module function",
        {function.name for function in module_functions},
        rendered_functions,
    )
    _validate_inventory(
        "Client/AsyncClient method",
        set(sync_methods) | set(async_methods),
        rendered_client_methods,
    )
    _validate_inventory(
        "Query/AsyncQuery method",
        set(query_methods) | set(async_query_methods),
        rendered_query_methods,
    )

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
