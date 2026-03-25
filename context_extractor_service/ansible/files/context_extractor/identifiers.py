from __future__ import annotations
from typing import Set, Tuple, Optional, List
from tree_sitter import Node
from .ts_utils import node_text

def is_function_like(n: Node, nodeset) -> bool: return n.type in nodeset["function"]
def is_block_like(n: Node, nodeset) -> bool:    return n.type in nodeset["block"]
def is_key_stmt(n: Node, nodeset) -> bool:      return n.type in nodeset["key"]
def is_identifier(n: Node, nodeset) -> bool:    return n.type in nodeset["ident"]
def is_member_like(n: Node, nodeset) -> bool:   return n.type in nodeset["member_like"]
def is_assign(n: Node, nodeset) -> bool:        return n.type in nodeset["assign"]
def is_declaration(n: Node, nodeset) -> bool:   return n.type in nodeset["declaration"]
def is_call(n: Node, nodeset) -> bool:          return n.type in nodeset["call"]
def is_loop(n: Node, nodeset) -> bool:          return n.type in nodeset.get("loop", set())

def collect_idents_in_node(root: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """
    Собираем все идентификаторы в поддереве. Для member/field-узлов (obj.field)
    дополнительно собираем составляющие идентификаторы.
    """
    ids: Set[str] = set()
    stack: List[Node] = [root]
    while stack:
        n = stack.pop()
        if is_identifier(n, nodeset):
            ids.add(node_text(n, source_bytes))
        elif is_member_like(n, nodeset):
            for ch in n.children:
                if is_identifier(ch, nodeset) or ch.type in {"property_identifier", "field_identifier"}:
                    ids.add(node_text(ch, source_bytes))
        stack.extend(n.children)
    return ids

def _collect_leaf_idents(n: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Collect all identifier leaf nodes in a subtree."""
    out: Set[str] = set()
    stack: List[Node] = [n]
    while stack:
        x = stack.pop()
        if is_identifier(x, nodeset):
            out.add(node_text(x, source_bytes))
        else:
            stack.extend(x.children)
    return out


def _collect_decl_names(n: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Collect only the declared variable name(s) from a declaration node (LHS only)."""
    out: Set[str] = set()

    # Go: short_var_declaration has a "left" field with the declared names
    left = n.child_by_field_name("left")
    if left is not None:
        return _collect_leaf_idents(left, source_bytes, nodeset)

    # JS/TS/Java/C++: declarations contain variable_declarator or init_declarator children
    for child in n.children:
        if child.type in {"variable_declarator", "init_declarator"}:
            name_node = child.child_by_field_name("name")
            if name_node is None:
                # C++ init_declarator uses "declarator" field
                name_node = child.child_by_field_name("declarator")
            if name_node is not None:
                out |= _collect_leaf_idents(name_node, source_bytes, nodeset)

    # Fallback: take only the first direct identifier child (the variable name)
    if not out:
        for child in n.children:
            if is_identifier(child, nodeset):
                out.add(node_text(child, source_bytes))
                break
    return out

_EXTRA_READ_TYPES = frozenset({"type_identifier", "this", "self"})

# Node types that represent parameter names in destructuring patterns
_PARAM_NAME_TYPES = frozenset({
    "identifier", "shorthand_property_identifier_pattern",
    "shorthand_property_identifier", "property_identifier",
    "field_identifier", "simple_identifier", "name", "variable_name",
})


def _collect_param_names(root: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Collect parameter names from formal_parameters / required_parameter nodes.

    Handles destructured patterns, rest patterns, typed parameters, etc.
    """
    out: Set[str] = set()
    stack: List[Node] = [root]
    # Skip type annotations and default values
    skip_types = {"type_annotation", "type_identifier", "predefined_type",
                  "literal_type", "union_type", "intersection_type",
                  "generic_type", "object_type", "array_type", "parenthesized_type"}
    while stack:
        n = stack.pop()
        if n.type in skip_types:
            continue
        if n.type in _PARAM_NAME_TYPES:
            out.add(node_text(n, source_bytes))
        elif is_identifier(n, nodeset):
            out.add(node_text(n, source_bytes))
        else:
            stack.extend(n.children)
    return out


def _collect_extra_reads(root: Node, source_bytes: bytes, reads: Set[str], exclude: Set[str]):
    """Collect type_identifier and this/self nodes as reads (not in standard ident sets)."""
    stack: List[Node] = [root]
    while stack:
        n = stack.pop()
        if n.type in _EXTRA_READ_TYPES:
            text = node_text(n, source_bytes)
            if text not in exclude:
                reads.add(text)
        stack.extend(n.children)


def split_reads_writes(root: Node, source_bytes: bytes, lang_key: str, nodeset) -> Tuple[Set[str], Set[str]]:
    """
    Делим идентификаторы на 'reads' и 'writes':
      - LHS присваивания -> writes, RHS -> reads (включая +=, -= и т.п.)
      - Декларации -> имя(ена) в writes, инициализаторы -> reads
      - Вызовы -> callee+аргументы в reads
      - Циклы -> переменная(ые) итерации в writes, остальное в reads
    Всегда добавляем «сырае» идентификаторы как reads, если мы не распознали конкретную роль.
    """
    reads: Set[str] = set()
    writes: Set[str] = set()
    stack: List[Node] = [root]

    while stack:
        n = stack.pop()

        if is_assign(n, nodeset):
            if n.child_count >= 3:
                lhs = n.children[0]
                rhs = n.children[-1]
                # For member expression LHS (e.g., window.location.href = ...),
                # only the leaf property is the write target; object parts are reads.
                if is_member_like(lhs, nodeset):
                    all_lhs = collect_idents_in_node(lhs, source_bytes, nodeset)
                    # The rightmost child (property) is the write target;
                    # the rest of the chain (object parts) are reads.
                    last_child = lhs.children[-1] if lhs.children else None
                    leaf_types = nodeset["ident"] | {"property_identifier", "field_identifier"}
                    if last_child and last_child.type in leaf_types:
                        leaf = node_text(last_child, source_bytes)
                        writes.add(leaf)
                        reads |= (all_lhs - {leaf})
                    else:
                        # Can't determine leaf, treat whole chain as writes
                        writes |= all_lhs
                else:
                    writes |= collect_idents_in_node(lhs, source_bytes, nodeset)
                reads |= collect_idents_in_node(rhs, source_bytes, nodeset)
            else:
                reads |= collect_idents_in_node(n, source_bytes, nodeset)

        elif is_declaration(n, nodeset):
            decl_names = _collect_decl_names(n, source_bytes, nodeset)
            writes |= decl_names
            # Collect reads from all children (excluding declared names)
            for ch in n.children:
                reads |= (collect_idents_in_node(ch, source_bytes, nodeset) - decl_names)
            # Also collect type_identifier and this/self keywords as reads
            _collect_extra_reads(n, source_bytes, reads, decl_names)

        elif is_call(n, nodeset):
            reads |= collect_idents_in_node(n, source_bytes, nodeset)
            _collect_extra_reads(n, source_bytes, reads, set())

        elif n.type == "with_statement":
            # Python: with open(x) as f: ... → open, x are reads; f is write
            for ch in n.children:
                if ch.type == "with_clause":
                    for item in ch.children:
                        if item.type == "with_item":
                            for sub in item.children:
                                if sub.type == "as_pattern":
                                    # Pattern: <expr> as <alias>
                                    alias = sub.child_by_field_name("alias")
                                    if alias:
                                        writes |= _collect_leaf_idents(alias, source_bytes, nodeset)
                                    val = sub.child_by_field_name("value")
                                    if val:
                                        reads |= collect_idents_in_node(val, source_bytes, nodeset)
                                elif sub.type not in {"as", ","}:
                                    reads |= collect_idents_in_node(sub, source_bytes, nodeset)

        elif n.type in {"function_definition", "function_declaration", "method_declaration"}:
            # Extract function name as write, parameters as writes
            name_node = n.child_by_field_name("name")
            if name_node:
                writes |= _collect_leaf_idents(name_node, source_bytes, nodeset)
            params = n.child_by_field_name("parameters")
            # C++: name and params are inside function_declarator
            declarator = n.child_by_field_name("declarator")
            if declarator and declarator.type == "function_declarator":
                if not name_node:
                    inner_name = declarator.child_by_field_name("declarator")
                    if inner_name:
                        writes |= _collect_leaf_idents(inner_name, source_bytes, nodeset)
                if not params:
                    params = declarator.child_by_field_name("parameters")
            if params:
                writes |= _collect_param_names(params, source_bytes, nodeset)

        elif n.type == "field_declaration":
            # C++ struct member: type* name = initializer;
            all_ids = collect_idents_in_node(n, source_bytes, nodeset)
            # Also collect type_identifier nodes (not in standard ident set)
            for ch in n.children:
                if ch.type == "type_identifier":
                    all_ids.add(node_text(ch, source_bytes))
                if ch.type == "new_expression":
                    for sub in ch.children:
                        if sub.type == "type_identifier":
                            all_ids.add(node_text(sub, source_bytes))
            # The field identifier is the write, rest are reads
            for ch in n.children:
                if ch.type == "field_identifier":
                    writes.add(node_text(ch, source_bytes))
                if ch.type == "pointer_declarator":
                    for sub in ch.children:
                        if sub.type == "field_identifier":
                            writes.add(node_text(sub, source_bytes))
            reads |= (all_ids - writes)

        elif n.type == "formal_parameters":
            # Parameter lists — all identifiers inside are writes (parameter names)
            # Include pattern types (destructuring) and rest patterns
            writes |= _collect_param_names(n, source_bytes, nodeset)

        elif is_loop(n, nodeset):
            # Языко-специфичные эвристики для «левых» переменных цикла
            for ch in n.children:
                t = ch.type
                if lang_key == "python" and t in {"identifier", "pattern", "tuple"}:
                    writes |= collect_idents_in_node(ch, source_bytes, nodeset)
                if lang_key == "javascript" and t in {"variable_declaration", "lexical_declaration", "identifier"}:
                    writes |= collect_idents_in_node(ch, source_bytes, nodeset)
                if lang_key == "java" and t in {"local_variable_declaration", "variable_declarator", "identifier"}:
                    writes |= collect_idents_in_node(ch, source_bytes, nodeset)
                if lang_key == "cpp" and t in {"declaration", "init_declarator", "identifier"}:
                    writes |= collect_idents_in_node(ch, source_bytes, nodeset)
                if lang_key == "php" and t in {"variable_name", "name"}:
                # In PHP, the loop variable in foreach/for statements should be treated as a write.
                    writes |= collect_idents_in_node(ch, source_bytes, nodeset)

            all_ids = collect_idents_in_node(n, source_bytes, nodeset)
            reads |= (all_ids - writes)

        else:
            stack.extend(n.children)

    # Базовая подстраховка: всё, что не классифицировали как write, считаем read
    raw_ids = collect_idents_in_node(root, source_bytes, nodeset)
    reads |= (raw_ids - writes)
    # Also collect type_identifier and this/self as reads from the whole tree
    _collect_extra_reads(root, source_bytes, reads, writes)
    return reads, writes
