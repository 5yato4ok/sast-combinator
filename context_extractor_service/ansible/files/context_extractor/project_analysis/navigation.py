from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LANG_NODESETS
from .classification import classify_file
from .shared import (
    _find_func_node,
    _iter_source_files,
    _parse_required,
    _snippet,
    _MAX_RESULTS,
)
from .symbols import _definition_names, _get_node_name, _is_callable_binding_node, _symbol_variants
from ..ts_utils import line_range, node_text

_CLASS_DEFINITION_TYPES = frozenset({
    "class_definition", "class_declaration", "class", "class_specifier",
    "interface_declaration", "struct_specifier", "enum_declaration",
})
_TYPE_DEFINITION_TYPES = frozenset({
    "type_alias_declaration", "interface_declaration", "enum_declaration",
})
_VARIABLE_DEFINITION_TYPES = frozenset({
    "variable_declarator", "init_declarator", "public_field_definition",
    "ui_property", "ui_binding",
})


def find_imports(source_dir: Path, file_path: str) -> list[str]:
    full = source_dir / file_path
    source = full.read_text(encoding="utf-8", errors="replace")
    tree, lang_key, src_bytes = _parse_required(source, full)
    return _imports_from_ast(tree.root_node, lang_key, src_bytes)


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

def find_decorators(source: str, filepath: Path, line_number: int) -> list[str]:
    tree, lang_key, src_bytes = _parse_required(source, filepath)
    return _decorators_from_ast(tree.root_node, lang_key, src_bytes, line_number)


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

def get_file_structure(source: str, filepath: Path) -> dict[str, Any]:
    tree, lang_key, src_bytes = _parse_required(source, filepath)
    return _structure_from_ast(tree.root_node, lang_key, src_bytes)


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

def find_definition(source_dir: Path, symbol_name: str) -> list[dict[str, Any]]:
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
        if not _text_may_contain_symbol(text, qualified, leaf):
            continue
        tree, lang_key, src_bytes = _parse_required(text, full)
        ast_results = _find_ast_definitions(rel, tree, lang_key, src_bytes, qualified, leaf)
        if ast_results:
            results.extend(ast_results)
        if len(results) >= _MAX_RESULTS:
            break

    if not results:
        return []

    prefer_class = bool(leaf and leaf[:1].isupper() and "::" not in qualified)
    results = _dedupe_definition_results(results)
    results.sort(key=lambda item: _rank_definition_result(item, prefer_class))
    return [_public_definition_result(results[0])]


def _find_ast_definitions(rel: Path, tree, lang_key: str | None, src_bytes: bytes | None, qualified: str, leaf: str):
    if not tree or not lang_key or not src_bytes:
        return []

    results: list[dict[str, Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if _is_ast_definition_candidate(node, lang_key):
            names = _definition_names(node, src_bytes)
            if qualified in names or leaf in names:
                exact_match = int(qualified in names)
                results.append({
                    "file": str(rel),
                    "line": _definition_line(node),
                    "kind": _definition_kind(node, lang_key, src_bytes),
                    "_exact_match": exact_match,
                    "_definition_priority": _definition_priority(node),
                })
        stack.extend(reversed(node.children))
    return results


def _is_ast_definition_candidate(node, lang_key: str) -> bool:
    nodeset = LANG_NODESETS.get(lang_key, {})
    return bool(
        node.type in nodeset.get("function", set())
        or node.type in nodeset.get("declaration", set())
        or node.type in _CLASS_DEFINITION_TYPES
        or node.type in _TYPE_DEFINITION_TYPES
        or node.type in _VARIABLE_DEFINITION_TYPES
    )


def _definition_kind(node, lang_key: str, src_bytes: bytes) -> str:
    if node.type in _CLASS_DEFINITION_TYPES:
        return "class"
    if node.type in _TYPE_DEFINITION_TYPES:
        return "type"
    if _is_callable_definition_node(node, lang_key, src_bytes):
        return "function"
    return "variable"


def _is_callable_definition_node(node, lang_key: str, src_bytes: bytes) -> bool:
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())
    if node.type in func_types:
        return True
    if _is_callable_binding_node(node, lang_key, src_bytes):
        return True
    value = node.child_by_field_name("value")
    if value is None and node.type == "variable_declarator" and node.children:
        value = node.children[-1]
    return value is not None and value.type in func_types


def _definition_line(node) -> int:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node.start_point[0] + 1
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        inner = declarator.child_by_field_name("declarator")
        if inner is not None:
            return inner.start_point[0] + 1
        return declarator.start_point[0] + 1
    return node.start_point[0] + 1


def _definition_priority(node) -> int:
    if node.type in {"function_definition", "function_declaration", "method_declaration"}:
        return 0
    if node.type == "function_signature":
        return 2
    return 1


def _dedupe_definition_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, int, str], dict[str, Any]] = {}
    for item in results:
        key = (item["file"], item["line"], item["kind"])
        existing = deduped.get(key)
        if existing is None or item.get("_exact_match", 0) > existing.get("_exact_match", 0):
            deduped[key] = item
    return list(deduped.values())


def _rank_definition_result(item: dict[str, Any], prefer_class: bool) -> tuple[int, int, str, int]:
    exact_rank = 0 if item.get("_exact_match", 0) else 1
    kind_rank = 0 if prefer_class and item["kind"] == "class" else 1
    function_rank = 0 if item["kind"] == "function" else 1
    definition_priority = item.get("_definition_priority", 1)
    return (
        exact_rank,
        kind_rank,
        function_rank,
        definition_priority,
        item["file"].count("/"),
        item["file"],
        item["line"],
    )


def _public_definition_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": item["file"],
        "line": item["line"],
        "kind": item["kind"],
    }


def _text_may_contain_symbol(text: str, qualified: str, leaf: str) -> bool:
    if leaf in text or qualified in text:
        return True
    compact_text = "".join(text.split())
    return leaf in compact_text or qualified in compact_text

def find_route_to_function(source_dir: Path, function_name: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for rel in _iter_source_files(source_dir):
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        file_class = classify_file(str(rel))
        if file_class["type"] in {"vendored", "generated"}:
            continue

        if function_name not in text:
            continue

        tree, lang_key, src_bytes = _parse_required(text, full)
        lines = text.splitlines()
        results.extend(_find_ast_routes(rel, lines, tree.root_node, lang_key, src_bytes, function_name))
        if len(results) >= _MAX_RESULTS:
            return results[:_MAX_RESULTS]
    return results


def _find_ast_routes(
    rel: Path,
    lines: list[str],
    root,
    lang_key: str,
    src_bytes: bytes,
    function_name: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    stack = [root]
    while stack:
        node = stack.pop()
        for line_number, pattern in _route_entries_for_node(node, lang_key, src_bytes, function_name):
            key = (line_number, pattern)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "file": str(rel),
                "line": line_number,
                "pattern": pattern,
                "snippet": _snippet(lines, line_number - 1, ctx=1),
            })
        stack.extend(reversed(node.children))
    return results


def _route_entries_for_node(node, lang_key: str, src_bytes: bytes, function_name: str) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []

    call_entry = _extract_route_entry_from_call(node, lang_key, src_bytes, function_name)
    if call_entry is not None:
        results.append(call_entry)

    for entry in _extract_route_entries_from_annotations(node, lang_key, src_bytes, function_name):
        results.append(entry)

    return results


def _extract_route_entry_from_call(node, lang_key: str, src_bytes: bytes, function_name: str) -> tuple[int, str] | None:
    call_types = LANG_NODESETS.get(lang_key, {}).get("call", set())
    if node.type not in call_types:
        return None

    target_names = _extract_call_target_names(node, src_bytes)
    route_target_names = _ROUTE_CALL_TARGETS.get(lang_key, set())
    if not (target_names & route_target_names):
        return None

    arguments = node.child_by_field_name("arguments")
    if arguments is None:
        for child in node.children:
            if child.type in {"arguments", "argument_list"}:
                arguments = child
                break
    if arguments is None:
        return None

    arg_identifiers = _extract_identifier_names(arguments, src_bytes)
    if function_name not in arg_identifiers:
        return None

    path = _extract_first_route_string(arguments, src_bytes)
    if not path:
        return None
    return node.start_point[0] + 1, path


def _extract_route_entries_from_annotations(
    node,
    lang_key: str,
    src_bytes: bytes,
    function_name: str,
) -> list[tuple[int, str]]:
    if function_name not in _definition_names(node, src_bytes):
        return []

    decorator_nodes = _route_decorator_nodes_for_function(node)
    results: list[tuple[int, str]] = []
    for decorator in decorator_nodes:
        decorator_text = node_text(decorator, src_bytes)
        if not any(marker in decorator_text for marker in _ROUTE_DECORATOR_MARKERS.get(lang_key, set())):
            continue
        path = _extract_first_route_string(decorator, src_bytes)
        if path:
            results.append((decorator.start_point[0] + 1, path))
    return results


def _route_decorator_nodes_for_function(node) -> list:
    decorator_types = {
        "decorator", "annotation", "marker_annotation",
        "attribute", "attribute_list",
    }
    decorators: list = []
    seen: set[int] = set()

    def add(candidate):
        if candidate is not None and candidate.type in decorator_types and candidate.id not in seen:
            seen.add(candidate.id)
            decorators.append(candidate)

    def add_nested(root_node):
        stack = [root_node]
        while stack:
            current = stack.pop()
            add(current)
            stack.extend(reversed(current.children))

    for child in node.children:
        add_nested(child)
    parent = node.parent
    if parent is not None:
        for child in parent.children:
            if child == node:
                break
            add_nested(child)
        if parent.type == "decorated_definition":
            add_nested(parent)
            for child in parent.children:
                add_nested(child)
    return decorators


def _extract_call_target_names(node, src_bytes: bytes) -> set[str]:
    target = node.child_by_field_name("function")
    if target is None:
        for child in node.children:
            if child.type in {"arguments", "argument_list"}:
                break
            if child.type not in {"(", ")", ".", "::", "?.", "optional_chain"}:
                target = child
                break
    if target is None:
        return set()
    return _extract_identifier_names(target, src_bytes)


def _extract_identifier_names(node, src_bytes: bytes) -> set[str]:
    names: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in {
            "identifier", "name", "simple_identifier", "property_identifier",
            "field_identifier", "destructor_name", "operator_name",
        }:
            names.add(node_text(current, src_bytes).lstrip("~"))
        stack.extend(reversed(current.children))
    return names


def _extract_first_route_string(node, src_bytes: bytes) -> str:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in {
            "string", "string_literal", "interpreted_string_literal",
            "raw_string_literal", "literal_value",
        }:
            text = node_text(current, src_bytes).strip()
            if len(text) >= 2 and text[:1] in {"'", '"'} and text[-1:] == text[:1]:
                return text[1:-1]
        stack.extend(reversed(current.children))
    return ""


_ROUTE_CALL_TARGETS = {
    "python": {"path", "re_path", "url"},
    "javascript": {"get", "post", "put", "patch", "delete", "all", "use"},
    "typescript": {"get", "post", "put", "patch", "delete", "all", "use"},
    "csharp": {"MapGet", "MapPost", "MapPut", "MapDelete", "MapPatch", "MapMethods"},
    "go": {"HandleFunc", "Handle", "Get", "Post", "Put", "Delete"},
    "php": {"get", "post", "put", "patch", "delete", "any"},
}


_ROUTE_DECORATOR_MARKERS = {
    "python": {"route", ".route", ".get", ".post", ".put", ".patch", ".delete", ".options", ".head"},
    "java": {"RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"},
    "csharp": {"Route", "HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch"},
}
