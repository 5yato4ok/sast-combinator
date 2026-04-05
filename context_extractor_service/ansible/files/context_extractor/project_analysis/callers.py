from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LANG_NODESETS
from ..ts_utils import node_text
from .classification import classify_file
from .shared import (
    _find_enclosing_function_name,
    _iter_source_files,
    _parse_required,
    _snippet,
    _MAX_RESULTS,
)
from .symbols import _definition_names, _get_node_name, _is_definition_site_for_symbol, _symbol_variants

_CALL_NAME_TYPES = frozenset({
    "identifier", "name", "simple_identifier", "property_identifier",
    "field_identifier", "destructor_name", "operator_name",
})


def find_callers(source_dir: Path, file_path: str, function_name: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    treat_as_class_like = bool(function_name[:1].isupper())
    callable_owner_types = _target_symbol_callable_owner_types(source_dir, file_path, function_name)
    require_member_call = bool(
        not callable_owner_types
        and _target_symbol_requires_member_call(source_dir, file_path, function_name)
    )

    for rel in _iter_source_files(source_dir):
        if _should_skip_caller_file(rel):
            continue
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _file_can_contain_caller(text, function_name, callable_owner_types):
            continue
        lines = text.splitlines()
        cached_tree, cached_lang_key, cached_src_bytes = _parse_required(text, full)
        ast_results = _find_ast_callers(
            rel,
            lines,
            cached_tree,
            cached_lang_key,
            cached_src_bytes,
            function_name,
            treat_as_class_like,
            require_member_call,
            callable_owner_types,
        )
        if ast_results:
            results.extend(ast_results)
            if len(results) >= _MAX_RESULTS:
                return results[:_MAX_RESULTS]
    results.sort(key=lambda item: (item["file"], item["line"]))
    return results


def _find_ast_callers(
    rel: Path,
    lines: list[str],
    cached_tree,
    cached_lang_key: str | None,
    cached_src_bytes: bytes | None,
    function_name: str,
    treat_as_class_like: bool,
    require_member_call: bool,
    callable_owner_types: set[str],
) -> list[dict[str, Any]]:
    if not cached_tree or not cached_lang_key or not cached_src_bytes:
        return []
    nodeset = LANG_NODESETS.get(cached_lang_key, {})
    call_types = nodeset.get("call", set())
    if not call_types:
        return []

    results: list[dict[str, Any]] = []
    declared_types = _collect_declared_types(cached_tree.root_node, cached_lang_key, cached_src_bytes)
    stack = [cached_tree.root_node]
    seen_lines: set[int] = set()
    while stack:
        node = stack.pop()
        if node.type in call_types:
            line_number = node.start_point[0] + 1
            if line_number not in seen_lines and _call_matches_symbol(
                node,
                cached_src_bytes,
                function_name,
                callable_owner_types,
                declared_types,
            ):
                if require_member_call and not _call_uses_member_target(node):
                    stack.extend(reversed(node.children))
                    continue
                if not _is_ast_definition_site(
                    cached_tree,
                    cached_lang_key,
                    cached_src_bytes,
                    line_number,
                    function_name,
                    treat_as_class_like,
                ):
                    seen_lines.add(line_number)
                    results.append(_build_caller_result(rel, lines, line_number - 1, cached_tree, cached_lang_key))
        stack.extend(reversed(node.children))
    return results


def _call_matches_symbol(
    node,
    src_bytes: bytes,
    function_name: str,
    callable_owner_types: set[str],
    declared_types: dict[str, set[str]],
) -> bool:
    names = _extract_call_target_names(node, src_bytes)
    if function_name in names:
        return True
    # Also check if the function name appears as an identifier argument
    # (e.g. callbacks like raw.map(processUser) or grpc.UnaryInterceptor(AuthInterceptor))
    if _call_has_identifier_argument(node, src_bytes, function_name):
        return True
    if not callable_owner_types:
        return False
    target_types = _extract_call_target_declared_types(node, src_bytes, declared_types)
    return bool(target_types & callable_owner_types)


def _call_has_identifier_argument(node, src_bytes: bytes, function_name: str) -> bool:
    """Check if function_name appears as a bare identifier in the call's argument list.

    For languages with structured argument lists (JS, Go, Java…) this scans the
    arguments/argument_list child.  For bash commands all arguments are direct
    ``word`` children of the command node, so we also check those.
    """
    for child in node.children:
        if child.type in {"arguments", "argument_list"}:
            for arg in child.children:
                if arg.is_named and arg.type in _CALL_NAME_TYPES and node_text(arg, src_bytes) == function_name:
                    return True
            break
    # Bash: direct word children carry argument values
    for child in node.children:
        if child.type == "word" and node_text(child, src_bytes) == function_name:
            return True
    return False


def _extract_call_target_names(node, src_bytes: bytes) -> set[str]:
    target = node.child_by_field_name("function")
    if target is None:
        target = node.child_by_field_name("type")
    # Java method_invocation and PHP method_call_expression expose the method name via 'name'
    if target is None:
        target = node.child_by_field_name("name")
    # Ruby call exposes the method name via 'method'
    if target is None:
        target = node.child_by_field_name("method")
    if target is None:
        for child in node.children:
            if child.type in {"arguments", "argument_list"}:
                break
            if child.is_named and child.type not in {"(", ")", ".", "::", "?.", "optional_chain", "new"}:
                target = child
                break
    if target is None:
        return set()

    names: list[str] = []
    stack = [target]
    while stack:
        current = stack.pop()
        if current.type in _CALL_NAME_TYPES:
            names.append(node_text(current, src_bytes).lstrip("~"))
        stack.extend(reversed(current.children))

    if names:
        # For method_reference nodes (Java: DataProcessor::sanitize, C++: Obj::method),
        # also include the method name — the last identifier after '::'.
        if node.type == "method_reference":
            for child in reversed(node.children):
                if child.is_named and child.type in _CALL_NAME_TYPES:
                    names.append(node_text(child, src_bytes).lstrip("~"))
                    break
        return set(names)

    raw = node_text(target, src_bytes).strip()
    if not raw:
        return set()
    leaf = raw.split("::")[-1].split(".")[-1].split("?.")[-1].lstrip("~")
    return {raw, leaf}


def _call_uses_member_target(node) -> bool:
    # Java/C++ method_reference (e.g. DataProcessor::sanitize) always has an owner
    if node.type == "method_reference":
        return True
    # Java method_invocation has 'object' field; Ruby call has 'receiver' field
    if node.child_by_field_name("object") is not None:
        return True
    if node.child_by_field_name("receiver") is not None:
        return True
    target = node.child_by_field_name("function")
    if target is None:
        for child in node.children:
            if child.type in {"arguments", "argument_list"}:
                break
            if child.type not in {"(", ")", ".", "::", "?.", "optional_chain"}:
                target = child
                break
    return bool(target and target.type in {
        "member_expression", "member_access_expression", "field_expression", "attribute",
        "navigation_expression",
    })


def _file_can_contain_caller(text: str, function_name: str, callable_owner_types: set[str]) -> bool:
    if function_name in text:
        return True
    return bool(callable_owner_types and any(owner_type in text for owner_type in callable_owner_types))


def _target_symbol_callable_owner_types(source_dir: Path, file_path: str, function_name: str) -> set[str]:
    if function_name != "operator()":
        return set()
    full = source_dir / file_path
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    tree, lang_key, src_bytes = _parse_required(text, full)
    func_types = LANG_NODESETS.get(lang_key, {}).get("function", set())
    owner_types: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in func_types and function_name in _definition_names(node, src_bytes):
            owner_types |= _definition_owner_types(node, src_bytes)
        stack.extend(reversed(node.children))
    return owner_types


def _definition_owner_types(node, src_bytes: bytes) -> set[str]:
    owner_types: set[str] = set()
    current = node.parent
    while current is not None:
        if current.type in {"class_specifier", "class_declaration", "class_definition", "struct_specifier"}:
            raw_name = _get_node_name(current, src_bytes)
            if raw_name:
                owner_types.add(_symbol_variants(raw_name)[1])
        current = current.parent
    for raw_name in _definition_names(node, src_bytes):
        if "::" not in raw_name:
            continue
        owner = raw_name.rsplit("::", 1)[0]
        if owner:
            owner_types.add(_symbol_variants(owner)[1])
    return owner_types


def _collect_declared_types(root, lang_key: str, src_bytes: bytes) -> dict[str, set[str]]:
    if lang_key != "cpp":
        return {}
    declared_types: dict[str, set[str]] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "declaration":
            type_names = _extract_cpp_declaration_type_names(node, src_bytes)
            if type_names:
                for binding in _extract_cpp_declaration_binding_names(node, src_bytes):
                    declared_types.setdefault(binding, set()).update(type_names)
        stack.extend(reversed(node.children))
    return declared_types


def _extract_cpp_declaration_type_names(node, src_bytes: bytes) -> set[str]:
    type_names: set[str] = set()
    for child in node.children:
        if child.type in {"type_identifier", "qualified_identifier"}:
            raw_name = node_text(child, src_bytes)
            if raw_name:
                type_names.add(_symbol_variants(raw_name)[1])
        if child.type in {"primitive_type", "sized_type_specifier"}:
            break
    return type_names


def _extract_cpp_declaration_binding_names(node, src_bytes: bytes) -> set[str]:
    binding_names: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "identifier":
            parent = current.parent
            if parent is not None and parent.type in {
                "function_declarator", "field_expression", "qualified_identifier",
            }:
                continue
            binding_names.add(node_text(current, src_bytes))
        stack.extend(reversed(current.children))
    return binding_names


def _extract_call_target_declared_types(node, src_bytes: bytes, declared_types: dict[str, set[str]]) -> set[str]:
    target_types: set[str] = set()
    for name in _extract_call_target_names(node, src_bytes):
        target_types.update(declared_types.get(name, set()))
    return target_types


def _target_symbol_requires_member_call(source_dir: Path, file_path: str, function_name: str) -> bool:
    full = source_dir / file_path
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    tree, lang_key, src_bytes = _parse_required(text, full)
    func_types = LANG_NODESETS.get(lang_key, {}).get("function", set())
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in func_types and function_name in _definition_names(node, src_bytes):
            if node.type == "constructor_declaration":
                return False
            if _has_class_like_ancestor(node):
                return True
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                # Check only the inner name part (not parameter types) to avoid
                # false positives from qualified types in parameter lists like
                # transform_all(std::vector<int>& v) where std::vector contains ::
                inner_decl = declarator.child_by_field_name("declarator")
                name_text = node_text(inner_decl, src_bytes) if inner_decl else node_text(declarator, src_bytes)
                if "::" in name_text:
                    return True
        stack.extend(reversed(node.children))
    return False


def _has_class_like_ancestor(node) -> bool:
    current = node.parent
    while current is not None:
        if current.type in {"class_specifier", "class_declaration", "class_definition", "declaration_list"}:
            return True
        current = current.parent
    return False


def _should_skip_caller_file(rel: Path) -> bool:
    file_class = classify_file(str(rel))
    return file_class["type"] in {"vendored", "generated"}

def _is_ast_definition_site(
    cached_tree,
    cached_lang_key: str | None,
    cached_src_bytes: bytes | None,
    line_number: int,
    function_name: str,
    treat_as_class_like: bool,
) -> bool:
    return bool(
        cached_tree
        and cached_lang_key
        and cached_src_bytes
        and not treat_as_class_like
        and _is_definition_site_for_symbol(
            cached_tree.root_node,
            cached_src_bytes,
            cached_lang_key,
            line_number,
            function_name,
        )
    )


def _build_caller_result(
    rel: Path,
    lines: list[str],
    line_index: int,
    cached_tree,
    cached_lang_key: str | None,
) -> dict[str, Any]:
    caller = None
    if cached_tree and cached_lang_key:
        caller = _find_enclosing_function_name(
            cached_tree.root_node,
            line_index + 1,
            cached_lang_key,
        )
    return {
        "file": str(rel),
        "line": line_index + 1,
        "caller_function": caller,
        "snippet": _snippet(lines, line_index, ctx=1),
    }
