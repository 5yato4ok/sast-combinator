from __future__ import annotations

from ..config import LANG_NODESETS
from ..ts_utils import node_text


_ANONYMOUS_NAME = "<anonymous>"
_PRIMARY_NAME_TYPES = frozenset({
    "identifier", "name", "simple_identifier", "property_identifier",
    "destructor_name", "operator_name",
})
_COMPOSITE_NAME_TYPES = frozenset({
    "nested_identifier", "qualified_identifier",
})
_DEFINITION_EXTRA_TYPES = frozenset({
    "class_definition", "class_declaration", "class",
    "interface_declaration", "struct_specifier", "enum_declaration",
    "function_declarator", "function_definition", "function_declaration",
})


def _normalize_symbol_leaf(name: str) -> str:
    return name.split("::")[-1].split(".")[-1].lstrip("~")


def _iter_node_name_candidates(node, src_bytes: bytes):
    # Python PEP 695: `type Vector[T] = list[T]` — the name is the first identifier
    # inside the second child (the type expression before `=`).
    if node.type == "type_alias_statement":
        for child in node.children:
            if child.type == "=":
                break
            if child.type in {"identifier", "name"}:
                yield node_text(child, src_bytes)
            elif child.type in {"type", "generic_type"}:
                # Descend one level to find the name identifier
                for sub in child.children:
                    if sub.type in {"identifier", "name", "type_identifier"}:
                        yield node_text(sub, src_bytes)
                        break
                    if sub.type == "generic_type":
                        for subsub in sub.children:
                            if subsub.type in {"identifier", "name", "type_identifier"}:
                                yield node_text(subsub, src_bytes)
                                break

    if node.type == "operator_declaration":
        saw_operator_keyword = False
        for child in node.children:
            if child.type == "operator":
                saw_operator_keyword = True
                continue
            if not saw_operator_keyword:
                continue
            if child.type in {"parameter_list", "arrow_expression_clause", "block", ";"}:
                break
            operator_text = node_text(child, src_bytes).strip()
            if operator_text:
                yield f"operator{operator_text}"
                break

    name_node = node.child_by_field_name("name")
    if name_node is not None:
        yield node_text(name_node, src_bytes)

    if node.type == "indexer_declaration":
        yield "this"

    declarator = node.child_by_field_name("declarator")
    if declarator is not None and declarator.type == "function_declarator":
        inner = declarator.child_by_field_name("declarator")
        if inner is not None and inner.type == "identifier":
            yield node_text(inner, src_bytes)
        for child in declarator.children:
            if child.type == "identifier":
                yield node_text(child, src_bytes)

    for child in node.children:
        if child.type in _PRIMARY_NAME_TYPES:
            yield node_text(child, src_bytes)

    for child in node.children:
        if child.type in _COMPOSITE_NAME_TYPES:
            yield node_text(child, src_bytes)

    for child in node.children:
        if child.type == "type_identifier":
            yield node_text(child, src_bytes)

    for raw_name in _iter_nested_declarator_names(node, src_bytes):
        yield raw_name


def _iter_nested_declarator_names(node, src_bytes: bytes):
    stack = []
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        stack.append(declarator)
    else:
        stack.extend(
            child for child in node.children
            if child.type in {"pointer_declarator", "reference_declarator", "function_declarator"}
        )

    while stack:
        current = stack.pop()
        if current.type == "function_declarator":
            inner = current.child_by_field_name("declarator")
            if inner is not None:
                yield node_text(inner, src_bytes)
            for child in current.children:
                if child.type in _PRIMARY_NAME_TYPES:
                    yield node_text(child, src_bytes)
        stack.extend(
            child for child in current.children
            if child.type in {"pointer_declarator", "reference_declarator", "function_declarator"}
        )


def _get_node_name(node, src_bytes: bytes) -> str:
    for candidate in _iter_node_name_candidates(node, src_bytes):
        if candidate:
            return candidate
    return _ANONYMOUS_NAME


def _symbol_variants(symbol_name: str) -> tuple[str, str]:
    qualified = symbol_name.strip()
    leaf = _normalize_symbol_leaf(qualified)
    return qualified, leaf


def _add_symbol_variants(names: set[str], raw_name: str) -> None:
    if raw_name:
        names.add(raw_name)
        names.add(_normalize_symbol_leaf(raw_name))


def _iter_definition_names(node, src_bytes: bytes):
    name = _get_node_name(node, src_bytes)
    if name and name != _ANONYMOUS_NAME:
        yield name

    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        inner = declarator.child_by_field_name("declarator")
        if inner is not None:
            full_name = node_text(inner, src_bytes).strip()
            if full_name:
                yield full_name


def _definition_names(node, src_bytes: bytes) -> set[str]:
    names: set[str] = set()
    for raw_name in _iter_definition_names(node, src_bytes):
        _add_symbol_variants(names, raw_name)
    return {name for name in names if name}


def _is_callable_binding_node(node, lang_key: str, src_bytes: bytes) -> bool:
    nodeset = LANG_NODESETS.get(lang_key, {})
    if node.type not in nodeset.get("callable_binding", set()):
        return False
    for raw_name in _definition_names(node, src_bytes):
        leaf = _normalize_symbol_leaf(raw_name)
        if len(leaf) > 2 and leaf.startswith("on") and leaf[2].isupper():
            return True
    return False


def _find_deepest_node_covering_line(root, line_number: int):
    stack = [root]
    deepest = None
    while stack:
        node = stack.pop()
        start = node.start_point[0] + 1
        end = node.end_point[0] + 1
        if not (start <= line_number <= end):
            continue
        deepest = node
        stack.extend(node.children)
    return deepest


def _definition_types_for_language(lang_key: str) -> set[str]:
    nodeset = LANG_NODESETS.get(lang_key, {})
    return nodeset.get("function", set()) | _DEFINITION_EXTRA_TYPES


def _is_definition_site_for_symbol(root, src_bytes: bytes, lang_key: str, line_number: int, symbol_name: str) -> bool:
    qualified, leaf = _symbol_variants(symbol_name)
    definition_types = _definition_types_for_language(lang_key)
    current = _find_deepest_node_covering_line(root, line_number)
    while current is not None:
        if current.type in definition_types:
            names = _definition_names(current, src_bytes)
            if qualified in names or leaf in names:
                return True
        current = current.parent
    return False
