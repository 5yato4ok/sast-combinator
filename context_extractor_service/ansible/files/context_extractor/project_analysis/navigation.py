from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import LANG_NODESETS
from .classification import classify_file
from .shared import (
    _find_func_node,
    _iter_source_files,
    _snippet,
    _try_parse,
    _MAX_RESULTS,
)
from .symbols import _get_node_name, _symbol_variants
from ..ts_utils import line_range, node_text


def find_imports(source_dir: Path, file_path: str) -> list[str]:
    full = source_dir / file_path
    source = full.read_text(encoding="utf-8", errors="replace")
    tree, lang_key, src_bytes = _try_parse(source, full)

    if tree and lang_key and src_bytes:
        return _imports_from_ast(tree.root_node, lang_key, src_bytes)
    return _imports_from_regex(source)


def _imports_from_ast(root, lang_key: str, src_bytes: bytes) -> list[str]:
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
        "ruby": {"call"},
    }
    types = import_types.get(lang_key, set())
    results: list[str] = []

    for child in root.children:
        if child.type in types:
            text = node_text(child, src_bytes).strip()
            if lang_key == "ruby" and "require" not in text:
                continue
            results.append(text)
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
    r"import\s+.+|from\s+\S+\s+import\s.+"
    r"|require\s*\(.+\)|require_relative\s*\(.+\)"
    r"|#include\s+[<\"].+[>\"]"
    r"|using\s+.+;"
    r"|use\s+.+;"
    r"|import\s+.+"
    r")",
    re.MULTILINE,
)


def _imports_from_regex(source: str) -> list[str]:
    return [m.group(0).strip() for m in _IMPORT_RE.finditer(source)]


def find_decorators(source: str, filepath: Path, line_number: int) -> list[str]:
    tree, lang_key, src_bytes = _try_parse(source, filepath)
    if tree and lang_key and src_bytes:
        return _decorators_from_ast(tree.root_node, lang_key, src_bytes, line_number)
    return _decorators_from_regex(source, line_number)


def _decorators_from_ast(root, lang_key: str, src_bytes: bytes, line_number: int) -> list[str]:
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())
    decorator_types = {
        "decorator", "annotation", "marker_annotation",
        "attribute", "attribute_list",
    }

    func_node = _find_func_node(root, line_number, func_types)
    if not func_node:
        return []

    decorators: list[str] = []
    seen: set[int] = set()

    def _add(ch):
        if ch.id not in seen:
            seen.add(ch.id)
            decorators.append(node_text(ch, src_bytes).strip())

    for ch in func_node.children:
        if ch.type in decorator_types:
            _add(ch)
    if func_node.parent:
        for ch in func_node.parent.children:
            if ch == func_node:
                break
            if ch.type in decorator_types:
                _add(ch)
    if func_node.parent and func_node.parent.type == "decorated_definition":
        for ch in func_node.parent.children:
            if ch.type in decorator_types:
                _add(ch)
    return decorators


def _decorators_from_regex(source: str, line_number: int) -> list[str]:
    lines = source.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return []
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


def get_file_structure(source: str, filepath: Path) -> dict[str, Any]:
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
        actual = child
        if child.type == "decorated_definition":
            for sub in child.children:
                if sub.type in func_types or sub.type in class_types:
                    actual = sub
                    break

        if actual.type in class_types:
            classes.append(_extract_class_info(actual, src_bytes, func_types))
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


def _extract_class_info(node, src_bytes: bytes, func_types: set) -> dict:
    name = _get_node_name(node, src_bytes)
    s, e = line_range(node)
    methods: list[dict] = []
    for child in node.children:
        _find_methods(child, src_bytes, func_types, methods)
    return {"name": name, "line": s + 1, "end_line": e + 1, "methods": methods}


def _find_methods(node, src_bytes: bytes, func_types: set, out: list):
    stack = list(node.children)
    while stack:
        current = stack.pop()
        if current.type in func_types:
            name = _get_node_name(current, src_bytes)
            s, e = line_range(current)
            out.append({"name": name, "line": s + 1, "end_line": e + 1})
        else:
            stack.extend(current.children)


_STRUCT_RE = re.compile(
    r"^\s*(?:(?:export\s+)?(?:default\s+)?)"
    r"(?:(?:public|private|protected|static|abstract|final|async)\s+)*"
    r"(class|interface|struct|enum|def|func|function|fn)\s+"
    r"([A-Za-z_]\w*)",
    re.MULTILINE,
)


def _structure_from_regex(source: str) -> dict[str, Any]:
    classes: list[dict] = []
    functions: list[dict] = []
    for match in _STRUCT_RE.finditer(source):
        kind = match.group(1)
        name = match.group(2)
        line = source[:match.start()].count("\n") + 1
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


def find_definition(source_dir: Path, symbol_name: str) -> list[dict[str, Any]]:
    def_patterns = [
        (re.compile(
            r"^\s*(?:(?:public|private|protected|static|async|export|default)\s+)*"
            r"(?:def|func|function|fn)\s+"
            + re.escape(symbol_name) + r"\b",
        ), "function"),
        (re.compile(
            r"^\s*(?:(?:public|private|protected|abstract|final|export)\s+)*"
            r"(?:class|struct|interface|enum)\s+"
            + re.escape(symbol_name) + r"\b",
        ), "class"),
        (re.compile(
            r"^\s*(?:(?:export|const|let|var|val|static)\s+)"
            + re.escape(symbol_name) + r"\b",
        ), "variable"),
        (re.compile(
            r"^\s*type\s+" + re.escape(symbol_name) + r"\s+",
        ), "type"),
        (re.compile(
            r"^\s*(?:\w+\s+)+" + re.escape(symbol_name) + r"\b\s*\(",
        ), "function"),
    ]

    results: list[dict[str, Any]] = []
    qualified, leaf = _symbol_variants(symbol_name)

    for rel in _iter_source_files(source_dir):
        file_class = classify_file(str(rel))
        if file_class["type"] in {"vendored", "generated"}:
            continue
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if leaf not in text and qualified not in text:
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            previous = lines[index - 1].strip() if index > 0 else ""
            next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""

            if _is_cpp_qualified_definition(stripped, qualified):
                results.append({"file": str(rel), "line": index + 1, "kind": "function"})
                break

            if _is_split_signature_definition(stripped, previous, next_line, leaf):
                results.append({"file": str(rel), "line": index + 1, "kind": "function"})
                break

            if _is_return_type_signature_definition(line, stripped, qualified, leaf):
                results.append({"file": str(rel), "line": index + 1, "kind": "function"})
                break

            for pattern, kind in def_patterns:
                if not pattern.match(line):
                    continue
                if kind == "function" and re.match(r"^\s*(?:return|new|throw|delete)\b", line):
                    continue
                if kind == "function" and stripped.endswith(";"):
                    continue
                results.append({"file": str(rel), "line": index + 1, "kind": kind})
                break
            if len(results) >= _MAX_RESULTS:
                break

    if not results:
        return []

    prefer_class = bool(leaf and leaf[:1].isupper() and "::" not in qualified)
    results.sort(key=lambda item: _rank_definition_result(item, prefer_class))
    return [results[0]]


def _is_cpp_qualified_definition(stripped: str, qualified: str) -> bool:
    return "::" in qualified and bool(
        re.search(re.escape(qualified) + r"\s*\(", stripped)
    ) and not stripped.endswith(";")


def _is_split_signature_definition(stripped: str, previous: str, next_line: str, leaf: str) -> bool:
    return bool(
        stripped.startswith(f"{leaf}(")
        and next_line.startswith("{")
        and previous
        and not previous.endswith(("{", "}", ";"))
        and not re.match(r"^(?:return|new|throw|delete)\b", previous)
    )


def _is_return_type_signature_definition(line: str, stripped: str, qualified: str, leaf: str) -> bool:
    return bool(
        "::" not in qualified
        and re.search(
            r"^(?!\s*(?:return|new|throw|delete)\b)"
            r".*?(?:^|[\s*&])(?:\w+(?:::\w+)*::)?"
            + re.escape(leaf)
            + r"\b\s*\(",
            line,
        )
        and not stripped.endswith(";")
    )


def _rank_definition_result(item: dict[str, Any], prefer_class: bool) -> tuple[int, int, str, int]:
    kind_rank = 0 if prefer_class and item["kind"] == "class" else 1
    return (kind_rank, item["file"].count("/"), item["file"], item["line"])


_ROUTE_PATTERNS = [
    re.compile(r"""(?:path|re_path|url)\s*\(\s*['"r].*?["']\s*,\s*(\w[\w.]*)\b"""),
    re.compile(r"""@\w+\.(?:route|get|post|put|patch|delete|options|head)\s*\(\s*['"](.*?)['"]"""),
    re.compile(r"""\.(?:get|post|put|patch|delete|all|use)\s*\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""@(?:Request|Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?['"]([^'"]+)['"]"""),
    re.compile(r"""\.(?:HandleFunc|Handle|Get|Post|Put|Delete)\s*\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""\[(?:Route|Http(?:Get|Post|Put|Delete|Patch))\s*\(\s*['"]([^'"]+)['"]"""),
    re.compile(r"""(?:get|post|put|patch|delete|resources?|match)\s+['"](/[^'"]*?)['"]"""),
    re.compile(r"""Route::(?:get|post|put|patch|delete|any)\s*\(\s*['"]([^'"]+)['"]"""),
]


def find_route_to_function(source_dir: Path, function_name: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    name_re = re.compile(r"\b" + re.escape(function_name) + r"\b")

    for rel in _iter_source_files(source_dir):
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        file_class = classify_file(str(rel))
        if file_class["type"] in {"vendored", "generated"}:
            continue

        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not name_re.search(line):
                continue
            match = _match_route_pattern(line, name_re)
            if match is None:
                continue
            results.append({
                "file": str(rel),
                "line": index + 1,
                "pattern": match.group(1) if match.lastindex else "",
                "snippet": _snippet(lines, index, ctx=1),
            })
            if len(results) >= _MAX_RESULTS:
                return results
    return results


def _match_route_pattern(line: str, name_re: re.Pattern[str]):
    for pattern in _ROUTE_PATTERNS:
        match = pattern.search(line)
        if match and not _has_separate_reference_before_route(line, match, name_re):
            return match
    return None


def _has_separate_reference_before_route(line: str, match, name_re: re.Pattern[str]) -> bool:
    name_match = name_re.search(line)
    if not name_match or match.end() <= 0:
        return False
    name_start = name_match.start()
    between = line[match.end():name_start] if name_start > match.end() else ""
    return ";" in between or (")," in between and "(" not in between)
