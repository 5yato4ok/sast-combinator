"""
Project-wide code analysis utilities for MCP tools.

All functions here operate on the filesystem directly (no network calls).
They accept a ``source_dir`` (Path) that points to the project root and
work with any language — using tree-sitter AST when a grammar is available,
falling back to text/regex heuristics otherwise.
"""
from __future__ import annotations

import fnmatch
import operator
import os
import re
from pathlib import Path
from typing import Any

from .config import LANG_NODESETS
from .identifiers import (
    is_key_stmt,
    split_reads_writes,
)
from .ts_utils import create_parser, detect_language, line_range, node_text

# ── Shared helpers ───────────────────────────────────────────────

# Directories to always skip when walking a project tree.
_SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg", ".idea", ".vscode",
    "node_modules", "__pycache__", ".tox", ".mypy_cache",
    "vendor", "third_party", "build", "dist", ".next",
    "target", "bin", "obj", ".gradle",
})

# Extensions considered "source code" (broad — intentionally inclusive).
_SOURCE_EXTS = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".scala",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".go", ".rs", ".rb",
    ".php", ".swift", ".m", ".mm",
    ".lua", ".pl", ".pm", ".r", ".R",
    ".dart", ".ex", ".exs", ".erl", ".hrl",
    ".zig", ".nim", ".v", ".vala",
})

_MAX_RESULTS = 50
_SNIPPET_CONTEXT = 2  # lines of context around a match


def _iter_source_files(source_dir: Path):
    """Yield relative Path objects for source files under *source_dir*."""
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in _SOURCE_EXTS:
                yield fpath.relative_to(source_dir)


def _snippet(lines: list[str], line_0: int, ctx: int = _SNIPPET_CONTEXT) -> str:
    """Return a small snippet around *line_0* (0-based) with line numbers."""
    start = max(0, line_0 - ctx)
    end = min(len(lines), line_0 + ctx + 1)
    parts: list[str] = []
    for i in range(start, end):
        marker = ">>>" if i == line_0 else "   "
        parts.append(f"{marker} {i + 1:>5}| {lines[i]}")
    return "\n".join(parts)


def _try_parse(source: str, filepath: Path):
    """Parse with tree-sitter if language is supported, else return None."""
    try:
        lang, lang_key = detect_language(filepath)
    except ValueError:
        return None, None, None
    parser = create_parser(lang)
    source_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)
    return tree, lang_key, source_bytes


def _find_enclosing_function_name(
    root, line_number: int, lang_key: str,
) -> str | None:
    """Return the name of the function enclosing *line_number* (1-based)."""
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())

    def _walk(node):
        s, e = line_range(node)
        if not (s + 1 <= line_number <= e + 1):
            return None
        if node.type in func_types:
            # Try to find the name child
            for ch in node.children:
                if ch.type in {"identifier", "name", "simple_identifier",
                               "property_identifier"}:
                    return node_text(ch, root.text)
            return None
        for ch in node.children:
            hit = _walk(ch)
            if hit:
                return hit
        return None

    return _walk(root)


# ── Tool implementations ─────────────────────────────────────────


def find_callers(
    source_dir: Path, file_path: str, function_name: str,
) -> list[dict[str, Any]]:
    """
    Search the entire project for call sites of *function_name*.

    Uses text search (works for any language), then refines with AST
    when a tree-sitter grammar is available.
    """
    pattern = re.compile(
        r"(?<![A-Za-z0-9_.])"
        + re.escape(function_name)
        + r"\s*\(",
    )
    results: list[dict[str, Any]] = []

    for rel in _iter_source_files(source_dir):
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if pattern.search(line):
                # Skip the definition itself
                stripped = line.lstrip()
                if stripped.startswith(("def ", "func ", "function ", "fn ")):
                    continue
                caller = None
                tree, lang_key, _src_bytes = _try_parse(text, full)
                if tree and lang_key:
                    caller = _find_enclosing_function_name(
                        tree.root_node, i + 1, lang_key,
                    )
                results.append({
                    "file": str(rel),
                    "line": i + 1,
                    "caller_function": caller,
                    "snippet": _snippet(lines, i, ctx=1),
                })
                if len(results) >= _MAX_RESULTS:
                    return results
    return results


def find_imports(source_dir: Path, file_path: str) -> list[str]:
    """
    Collect all import / require / using / include statements from a file.

    AST-based for supported languages, regex-based for everything else.
    """
    full = source_dir / file_path
    source = full.read_text(encoding="utf-8", errors="replace")
    tree, lang_key, src_bytes = _try_parse(source, full)

    if tree and lang_key and src_bytes:
        return _imports_from_ast(tree.root_node, lang_key, src_bytes)
    return _imports_from_regex(source)


def _imports_from_ast(root, lang_key: str, src_bytes: bytes) -> list[str]:
    """Extract imports via AST node types."""
    # Map language → set of import-like node types
    import_types: dict[str, set[str]] = {
        "python": {"import_statement", "import_from_statement"},
        "javascript": {"import_statement", "import_declaration"},
        "typescript": {"import_statement", "import_declaration"},
        "java": {"import_declaration"},
        "kotlin": {"import_header", "import_list"},
        "go": {"import_declaration", "import_spec"},
        "csharp": {"using_directive"},
        "cpp": {"preproc_include"},
        "php": {"namespace_use_declaration"},
        "ruby": {"call"},  # require/require_relative are calls in Ruby
    }
    types = import_types.get(lang_key, set())
    results: list[str] = []

    for child in root.children:
        if child.type in types:
            text = node_text(child, src_bytes).strip()
            if lang_key == "ruby" and "require" not in text:
                continue
            results.append(text)
        # Go groups imports inside import_declaration
        if lang_key == "go" and child.type == "import_declaration":
            for sub in child.children:
                if sub.type == "import_spec_list":
                    results.extend(
                        node_text(spec, src_bytes).strip()
                        for spec in sub.children
                        if spec.type == "import_spec"
                    )
                elif sub.type == "import_spec":
                    results.append(node_text(sub, src_bytes).strip())
    return results


_IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"import\s+.+|from\s+\S+\s+import\s+.+"  # Python
    r"|require\s*\(.+\)|require_relative\s*\(.+\)"  # Ruby / Node
    r"|#include\s+[<\"].+[>\"]"  # C/C++
    r"|using\s+.+;"  # C#
    r"|use\s+.+;"  # PHP / Rust
    r"|import\s+.+"  # Java / Kotlin / Go / TS / Dart
    r")",
    re.MULTILINE,
)


def _imports_from_regex(source: str) -> list[str]:
    """Fallback: extract import-like lines via regex for any language."""
    return [m.group(0).strip() for m in _IMPORT_RE.finditer(source)]


def classify_file(file_path: str) -> dict[str, Any]:
    """
    Classify a file by its path as test/migration/generated/vendored/config/production.

    Returns ``{type, confidence, reason}``.
    """
    parts = Path(file_path).parts
    name = Path(file_path).name.lower()
    path_lower = file_path.lower()

    # Test
    test_dir_patterns = {"test", "tests", "spec", "specs", "__tests__",
                         "test_utils", "testing", "testdata"}
    if any(p.lower() in test_dir_patterns for p in parts):
        return {"type": "test", "confidence": 0.95,
                "reason": "directory name indicates test code"}
    test_file_patterns = [
        "test_*", "*_test.*", "*_spec.*", "*.test.*", "*.spec.*",
        "conftest.py", "fixtures.*",
    ]
    if any(fnmatch.fnmatch(name, pat) for pat in test_file_patterns):
        return {"type": "test", "confidence": 0.95,
                "reason": "filename indicates test code"}

    # Migration
    migration_markers = {"migrations", "alembic", "db/migrate", "flyway",
                         "liquibase", "knex/migrations"}
    if any(m in path_lower for m in migration_markers):
        return {"type": "migration", "confidence": 0.9,
                "reason": "path contains migration directory"}

    # Generated / vendored
    vendored = {"vendor", "third_party", "node_modules", "packages",
                "bower_components", "external", "deps"}
    if any(p.lower() in vendored for p in parts):
        return {"type": "vendored", "confidence": 0.95,
                "reason": "path indicates vendored/third-party code"}
    generated_markers = {"generated", "autogen", "proto", ".gen."}
    if any(m in path_lower for m in generated_markers):
        return {"type": "generated", "confidence": 0.8,
                "reason": "path or name suggests generated code"}

    # Config
    config_names = {
        "settings.py", "config.py", "config.yaml", "config.yml",
        "config.json", "config.toml", ".env", ".env.example",
        "webpack.config.js", "tsconfig.json", "pyproject.toml",
        "setup.cfg", "setup.py", "package.json", "pom.xml",
        "build.gradle", "build.gradle.kts", "makefile", "dockerfile",
        "docker-compose.yml", "docker-compose.yaml",
    }
    if name in config_names:
        return {"type": "config", "confidence": 0.9,
                "reason": "filename is a known configuration file"}

    return {"type": "production", "confidence": 0.7,
            "reason": "no test/migration/vendor/config indicators found"}


def find_decorators(
    source: str, filepath: Path, line_number: int,
) -> list[str]:
    """
    Find decorators/annotations on the function containing *line_number*.

    AST-based for supported languages.  Regex fallback for ``@decorator``
    and Java-style ``@Annotation`` patterns.
    """
    tree, lang_key, src_bytes = _try_parse(source, filepath)
    if tree and lang_key and src_bytes:
        return _decorators_from_ast(tree.root_node, lang_key, src_bytes, line_number)
    return _decorators_from_regex(source, line_number)


def _decorators_from_ast(
    root, lang_key: str, src_bytes: bytes, line_number: int,
) -> list[str]:
    """Walk AST to find the function, then collect its decorator children."""
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())
    # node types that represent decorators / annotations
    decorator_types = {
        "decorator", "annotation", "marker_annotation",
        "attribute", "attribute_list",
    }

    func_node = _find_func_node(root, line_number, func_types)
    if not func_node:
        return []

    decorators: list[str] = [
        node_text(ch, src_bytes).strip()
        for ch in func_node.children
        if ch.type in decorator_types
    ]
    # Also check previous siblings (Python puts decorators before the function node)
    if func_node.parent:
        for ch in func_node.parent.children:
            if ch == func_node:
                break
            if ch.type in decorator_types:
                decorators.append(node_text(ch, src_bytes).strip())
    # Check decorated_definition wrapper (Python tree-sitter)
    if func_node.parent and func_node.parent.type == "decorated_definition":
        decorators.extend(
            node_text(ch, src_bytes).strip()
            for ch in func_node.parent.children
            if ch.type in decorator_types
        )
    return decorators


def _decorators_from_regex(source: str, line_number: int) -> list[str]:
    """Fallback: scan lines above *line_number* for @decorator patterns."""
    lines = source.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return []
    # Walk upward from line_number collecting @... lines
    decorators: list[str] = []
    i = idx - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith("@"):
            decorators.append(stripped)
            i -= 1
        elif not stripped or stripped.startswith(("#", "//")):
            i -= 1
        else:
            break
    decorators.reverse()
    return decorators


def _find_func_node(root, line_number: int, func_types: set):
    """Find the AST function node enclosing *line_number*."""
    s, e = line_range(root)
    if not (s + 1 <= line_number <= e + 1):
        return None
    if root.type in func_types:
        return root
    for ch in root.children:
        hit = _find_func_node(ch, line_number, func_types)
        if hit:
            return hit
    return None


def trace_identifier_backward(
    source: str,
    filepath: Path,
    line_number: int,
    identifier: str,
    max_depth: int = 3,
) -> list[dict[str, Any]]:
    """
    Trace where *identifier* gets its value within the enclosing function.

    Walks backward from *line_number* through assignments, collecting
    a chain of ``{line, code, reads, writes}`` entries up to *max_depth* hops.
    Works for any tree-sitter-supported language.
    For unsupported languages, does a simple regex-based backward scan.
    """
    tree, lang_key, src_bytes = _try_parse(source, filepath)
    if tree and lang_key and src_bytes:
        return _trace_ast(tree.root_node, lang_key, src_bytes, source,
                          line_number, identifier, max_depth)
    return _trace_regex(source, line_number, identifier, max_depth)


def _trace_ast(
    root, lang_key: str, src_bytes: bytes, source: str,
    line_number: int, identifier: str, max_depth: int,
) -> list[dict[str, Any]]:
    nodeset = LANG_NODESETS[lang_key]
    func_types = nodeset.get("function", set())
    func_node = _find_func_node(root, line_number, func_types)
    search_root = func_node or root

    # Collect all key statements inside the function, sorted by line
    stmts: list[tuple[int, Any]] = []
    _collect_key_stmts(search_root, nodeset, stmts)
    stmts.sort(key=operator.itemgetter(0))

    lines = source.splitlines()
    chain: list[dict[str, Any]] = []
    targets = {identifier}

    for _depth in range(max_depth):
        found = False
        # Walk backward from line_number looking for writes to any target
        for stmt_line, stmt_node in reversed(stmts):
            if stmt_line >= line_number:
                continue
            reads, writes = split_reads_writes(
                stmt_node, src_bytes, lang_key, nodeset,
            )
            overlap = writes & targets
            if overlap:
                code = lines[stmt_line] if stmt_line < len(lines) else ""
                chain.append({
                    "line": stmt_line + 1,
                    "code": code.strip(),
                    "writes": sorted(overlap),
                    "reads": sorted(reads),
                })
                # Next iteration traces the reads from this assignment
                targets = reads - writes
                line_number = stmt_line
                found = True
                break
        if not found or not targets:
            break

    return chain


def _trace_regex(
    source: str, line_number: int, identifier: str, max_depth: int,
) -> list[dict[str, Any]]:
    """Fallback: simple text-based backward scan for assignments to *identifier*."""
    lines = source.splitlines()
    assign_re = re.compile(
        r"\b" + re.escape(identifier) + r"\s*[=:]",
    )
    chain: list[dict[str, Any]] = []
    idx = line_number - 2  # 0-based, start one line above

    for _depth in range(max_depth):
        while idx >= 0:
            if assign_re.search(lines[idx]):
                chain.append({
                    "line": idx + 1,
                    "code": lines[idx].strip(),
                    "writes": [identifier],
                    "reads": [],
                })
                idx -= 1
                break
            idx -= 1
        else:
            break
    return chain


def _collect_key_stmts(node, nodeset: dict, out: list):
    """Recursively collect (0-based line, node) for key statements."""
    if is_key_stmt(node, nodeset):
        out.append((node.start_point[0], node))
    for ch in node.children:
        _collect_key_stmts(ch, nodeset, out)


def get_file_structure(
    source: str, filepath: Path,
) -> dict[str, Any]:
    """
    Parse top-level structure: classes, functions, methods, imports.

    Returns a dict of ``{language, classes, functions, imports}``.
    AST-based for supported languages, regex fallback otherwise.
    """
    tree, lang_key, src_bytes = _try_parse(source, filepath)
    if tree and lang_key and src_bytes:
        return _structure_from_ast(tree.root_node, lang_key, src_bytes)
    return _structure_from_regex(source)


def _structure_from_ast(root, lang_key: str, src_bytes: bytes) -> dict[str, Any]:
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())
    class_types = {
        "class_definition", "class_declaration", "class",
        "interface_declaration", "struct_specifier", "enum_declaration",
    }
    classes: list[dict] = []
    functions: list[dict] = []

    for child in root.children:
        # Unwrap decorated_definition (Python)
        actual = child
        if child.type == "decorated_definition":
            for sub in child.children:
                if sub.type in func_types or sub.type in class_types:
                    actual = sub
                    break

        if actual.type in class_types:
            cls = _extract_class_info(actual, lang_key, src_bytes, func_types)
            classes.append(cls)
        elif actual.type in func_types:
            name = _get_node_name(actual, src_bytes)
            s, e = line_range(actual)
            functions.append({"name": name, "line": s + 1, "end_line": e + 1})

    imports = _imports_from_ast(root, lang_key, src_bytes)
    return {
        "language": lang_key,
        "classes": classes,
        "functions": functions,
        "imports": imports,
    }


def _extract_class_info(
    node, lang_key: str, src_bytes: bytes, func_types: set,
) -> dict:
    name = _get_node_name(node, src_bytes)
    s, e = line_range(node)
    methods: list[dict] = []
    for child in node.children:
        _find_methods(child, src_bytes, func_types, methods)
    return {"name": name, "line": s + 1, "end_line": e + 1, "methods": methods}


def _find_methods(node, src_bytes: bytes, func_types: set, out: list):
    """Recursively find method definitions inside a class body."""
    if node.type in func_types:
        name = _get_node_name(node, src_bytes)
        s, e = line_range(node)
        out.append({"name": name, "line": s + 1, "end_line": e + 1})
        return  # Don't recurse into nested functions
    for ch in node.children:
        _find_methods(ch, src_bytes, func_types, out)


def _get_node_name(node, src_bytes: bytes) -> str:
    """Extract the name identifier from a function/class node.

    Uses tree-sitter's named ``name`` field first (reliable for C#, Go, Kotlin,
    TypeScript, etc.), then falls back to scanning children for common name
    identifier types.  ``type_identifier`` is tried last because in Java/C# it
    is the return type, not the method name.
    """
    # Priority 0: named field "name" (tree-sitter field API — most precise)
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return node_text(name_node, src_bytes)
    # Priority 1: actual name identifiers
    primary = {"identifier", "name", "simple_identifier", "property_identifier"}
    for child in node.children:
        if child.type in primary:
            return node_text(child, src_bytes)
    # Priority 2: type_identifier (for class names in Java/C#)
    for child in node.children:
        if child.type == "type_identifier":
            return node_text(child, src_bytes)
    return "<anonymous>"


_STRUCT_RE = re.compile(
    r"^\s*(?:(?:export\s+)?(?:default\s+)?)"
    r"(?:(?:public|private|protected|static|abstract|final|async)\s+)*"
    r"(class|interface|struct|enum|def|func|function|fn)\s+"
    r"([A-Za-z_]\w*)",
    re.MULTILINE,
)


def _structure_from_regex(source: str) -> dict[str, Any]:
    """Fallback: extract top-level structure via regex."""
    classes: list[dict] = []
    functions: list[dict] = []
    for m in _STRUCT_RE.finditer(source):
        kind = m.group(1)
        name = m.group(2)
        line = source[:m.start()].count("\n") + 1
        if kind in {"class", "interface", "struct", "enum"}:
            classes.append({"name": name, "line": line, "methods": []})
        else:
            functions.append({"name": name, "line": line})
    imports = _imports_from_regex(source)
    return {
        "language": "unknown",
        "classes": classes,
        "functions": functions,
        "imports": imports,
    }


def find_definition(
    source_dir: Path, symbol_name: str,
) -> list[dict[str, Any]]:
    """
    Search the project for definitions of *symbol_name* (function/class/variable).

    Returns a list of ``{file, line, kind, snippet}`` dicts.
    """
    # Regex patterns for common definition forms across languages
    def_patterns = [
        # function/method: def foo, func foo, function foo, fn foo
        (re.compile(
            r"^\s*(?:(?:public|private|protected|static|async|export|default)\s+)*"
            r"(?:def|func|function|fn)\s+"
            + re.escape(symbol_name) + r"\b",
        ), "function"),
        # class/struct/interface/enum
        (re.compile(
            r"^\s*(?:(?:public|private|protected|abstract|final|export)\s+)*"
            r"(?:class|struct|interface|enum)\s+"
            + re.escape(symbol_name) + r"\b",
        ), "class"),
        # variable: const/let/var/val NAME or NAME = (top-level)
        (re.compile(
            r"^\s*(?:(?:export|const|let|var|val|static)\s+)"
            + re.escape(symbol_name) + r"\b",
        ), "variable"),
        # Go type definition: type Name struct/interface
        (re.compile(
            r"^\s*type\s+" + re.escape(symbol_name) + r"\s+",
        ), "type"),
        # C/C++/Java return-type based: ReturnType functionName(
        (re.compile(
            r"^\s*(?:\w+\s+)+" + re.escape(symbol_name) + r"\s*\(",
        ), "function"),
    ]

    results: list[dict[str, Any]] = []

    for rel in _iter_source_files(source_dir):
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pattern, kind in def_patterns:
                if pattern.match(line):
                    results.append({
                        "file": str(rel),
                        "line": i + 1,
                        "kind": kind,
                        "snippet": _snippet(lines, i),
                    })
                    break
            if len(results) >= _MAX_RESULTS:
                return results
    return results


# ── Route patterns per framework ─────────────────────────────────

_ROUTE_PATTERNS = [
    # Django: path("...", view_func, ...) or url(r"...", view_func)
    re.compile(
        r"""(?:path|re_path|url)\s*\(\s*['"r].*?["']\s*,\s*"""
        r"""(\w[\w.]*)\b""",
    ),
    # Flask / FastAPI: @app.route / @router.get / @app.post
    re.compile(
        r"""@\w+\.(?:route|get|post|put|patch|delete|options|head)\s*\(\s*['"](.*?)['"]""",
    ),
    # Express.js: app.get("/path", handler) or router.post(...)
    re.compile(
        r"""\.(?:get|post|put|patch|delete|all|use)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    # Spring: @RequestMapping / @GetMapping / @PostMapping
    re.compile(
        r"""@(?:Request|Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?['"]([^'"]+)['"]""",
    ),
    # Go net/http or gorilla/mux: HandleFunc("/path", handler)
    re.compile(
        r"""\.(?:HandleFunc|Handle|Get|Post|Put|Delete)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    # ASP.NET: [Route("...")] / [HttpGet("...")]
    re.compile(
        r"""\[(?:Route|Http(?:Get|Post|Put|Delete|Patch))\s*\(\s*['"]([^'"]+)['"]""",
    ),
    # Ruby on Rails: get "/path", to: "controller#action"
    re.compile(
        r"""(?:get|post|put|patch|delete|resources?|match)\s+['"](/[^'"]*?)['"]""",
    ),
    # PHP Laravel: Route::get("/path", [Controller::class, "method"])
    re.compile(
        r"""Route::(?:get|post|put|patch|delete|any)\s*\(\s*['"]([^'"]+)['"]""",
    ),
]


def find_route_to_function(
    source_dir: Path, function_name: str,
) -> list[dict[str, Any]]:
    """
    Search for URL/route mappings that reference *function_name*.

    Scans common routing patterns across Django, Flask, FastAPI, Express,
    Spring, ASP.NET, Rails, Laravel, Go net/http.
    """
    results: list[dict[str, Any]] = []
    name_re = re.compile(r"\b" + re.escape(function_name) + r"\b")

    for rel in _iter_source_files(source_dir):
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not name_re.search(line):
                continue
            for pat in _ROUTE_PATTERNS:
                m = pat.search(line)
                if m:
                    results.append({
                        "file": str(rel),
                        "line": i + 1,
                        "pattern": m.group(1) if m.lastindex else "",
                        "snippet": _snippet(lines, i, ctx=1),
                    })
                    break
            if len(results) >= _MAX_RESULTS:
                return results
    return results
