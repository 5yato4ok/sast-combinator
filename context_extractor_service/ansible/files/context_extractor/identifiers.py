from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

from tree_sitter import Node

from .ts_utils import node_text, promote_single_statement_control_body

def is_identifier(n: Node, nodeset) -> bool:    return n.type in nodeset["ident"]
def is_member_like(n: Node, nodeset) -> bool:   return n.type in nodeset["member_like"]
def is_assign(n: Node, nodeset) -> bool:        return n.type in nodeset["assign"]
def is_declaration(n: Node, nodeset) -> bool:   return n.type in nodeset["declaration"]
def is_call(n: Node, nodeset) -> bool:          return n.type in nodeset["call"]
def is_function_like(n: Node, nodeset) -> bool: return n.type in nodeset["function"]
def is_block_like(n: Node, nodeset) -> bool:    return n.type in nodeset["block"]
def is_key_stmt(n: Node, nodeset) -> bool:      return n.type in nodeset["key"]
def is_loop(n: Node, nodeset) -> bool:          return n.type in nodeset.get("loop", set())

# Runtime-value keywords that should be treated like ordinary reads.
_VALUE_KEYWORDS = frozenset({"this", "self"})


def collect_idents_in_node(root: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Collect runtime-value identifiers in a subtree.

    Includes value-like variables, fields, property accesses, and ``this``/``self``.
    Excludes type-only syntax such as ``type_identifier``.
    """
    ids: Set[str] = set()
    stack: List[Node] = [root]
    while stack:
        n = stack.pop()
        if is_identifier(n, nodeset) or n.type in _VALUE_KEYWORDS:
            ids.add(node_text(n, source_bytes))
        elif is_member_like(n, nodeset):
            for ch in n.children:
                if is_identifier(ch, nodeset) or ch.type in {"property_identifier", "field_identifier"}:
                    ids.add(node_text(ch, source_bytes))
        stack.extend(n.children)
    return ids


CollectIds = Callable[[Node], Set[str]]
NodeHandler = Callable[[Node, bytes, CollectIds, str, object], "NodeEffect"]
NodePredicate = Callable[[Node, str, object], bool]


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
    """Collect declared binding names from a declaration-like node."""
    out: Set[str] = set()

    # Go exposes declared bindings under the ``left`` field.
    left = n.child_by_field_name("left")
    if left is not None:
        return _collect_leaf_idents(left, source_bytes, nodeset)

    # JS/TS/Java/C++ declarations usually wrap names in declarator children.
    for child in n.children:
        if child.type in {"variable_declarator", "init_declarator"}:
            name_node = child.child_by_field_name("name")
            if name_node is None:
                # C++ uses the ``declarator`` field instead of ``name`` here.
                name_node = child.child_by_field_name("declarator")
            if name_node is not None:
                out |= _collect_leaf_idents(name_node, source_bytes, nodeset)

    # Fallback for simpler grammars that surface the binding as a direct child.
    if not out:
        for child in n.children:
            if is_identifier(child, nodeset):
                out.add(node_text(child, source_bytes))
                break
    return out

# Node types that can represent parameter bindings inside nested patterns.
_PARAM_NAME_TYPES = frozenset({
    "identifier", "shorthand_property_identifier_pattern",
    "shorthand_property_identifier", "property_identifier",
    "field_identifier", "simple_identifier", "name", "variable_name",
})

_LOOP_WRITE_CHILD_TYPES = {
    "python": frozenset({"identifier", "pattern", "tuple"}),
    "javascript": frozenset({"variable_declaration", "lexical_declaration", "identifier"}),
    "java": frozenset({"local_variable_declaration", "variable_declarator", "identifier"}),
    "cpp": frozenset({"declaration", "init_declarator", "identifier"}),
    "php": frozenset({"variable_name", "name"}),
}


def _collect_param_names(root: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Collect parameter bindings from parameter-list subtrees.

    Handles destructuring, rest patterns, and typed parameters while skipping type syntax.
    """
    out: Set[str] = set()
    stack: List[Node] = [root]
    # Skip type-only subtrees; parameter defaults are still value reads elsewhere.
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


def _collect_loop_writes(loop_node: Node, source_bytes: bytes, lang_key: str, nodeset) -> Set[str]:
    writes: Set[str] = set()
    write_child_types = _LOOP_WRITE_CHILD_TYPES.get(lang_key, frozenset())
    if not write_child_types:
        return writes
    for child in loop_node.children:
        if child.type in write_child_types:
            writes |= collect_idents_in_node(child, source_bytes, nodeset)
    return writes


def _make_collect_ids(source_bytes: bytes, nodeset) -> CollectIds:
    cache: dict[tuple[int, int, str], Set[str]] = {}

    def _collect(node: Node) -> Set[str]:
        key = (node.start_byte, node.end_byte, node.type)
        ids = cache.get(key)
        if ids is None:
            ids = collect_idents_in_node(node, source_bytes, nodeset)
            cache[key] = ids
        return ids

    return _collect


def _iter_children_of_type(root: Node, node_type: str) -> List[Node]:
    return [child for child in root.children if child.type == node_type]


def _normalize_function_definition_raw_root(root: Node) -> Node:
    if root.type != "function_definition":
        return root
    declarator = root.child_by_field_name("declarator")
    if declarator is None:
        return root
    qualified = declarator.child_by_field_name("declarator")
    if qualified is not None and qualified.type == "qualified_identifier":
        return declarator
    return root


def _augment_function_declarator_raw_ids(
    raw_root: Node,
    raw_ids: Set[str],
    source_bytes: bytes,
) -> Set[str]:
    if raw_root.type != "function_declarator":
        return raw_ids
    qualified = raw_root.child_by_field_name("declarator")
    if qualified is not None and qualified.type == "qualified_identifier":
        for child in qualified.children:
            if child.type in {"namespace_identifier", "identifier", "destructor_name"}:
                raw_ids.add(node_text(child, source_bytes).lstrip("~"))
    return raw_ids


def _collect_with_item_reads_writes(
    item: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    nodeset,
) -> Tuple[Set[str], Set[str]]:
    reads: Set[str] = set()
    writes: Set[str] = set()
    for part in item.children:
        if part.type == "as_pattern":
            alias = part.child_by_field_name("alias")
            if alias:
                writes |= _collect_leaf_idents(alias, source_bytes, nodeset)
            value = part.child_by_field_name("value")
            if value:
                reads |= collect_ids(value)
            continue
        if part.type not in {"as", ","}:
            reads |= collect_ids(part)
    return reads, writes


def _collect_with_statement_reads_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    nodeset,
) -> Tuple[Set[str], Set[str]]:
    reads: Set[str] = set()
    writes: Set[str] = set()
    for clause in _iter_children_of_type(node, "with_clause"):
        for item in _iter_children_of_type(clause, "with_item"):
            item_reads, item_writes = _collect_with_item_reads_writes(item, source_bytes, collect_ids, nodeset)
            reads |= item_reads
            writes |= item_writes
    return reads, writes


def _collect_function_like_writes(
    node: Node,
    source_bytes: bytes,
    nodeset,
) -> Set[str]:
    writes: Set[str] = set()
    name_node = node.child_by_field_name("name")
    if name_node:
        writes |= _collect_leaf_idents(name_node, source_bytes, nodeset)
    params = node.child_by_field_name("parameters")
    declarator = node.child_by_field_name("declarator")
    if declarator and declarator.type == "function_declarator":
        if not name_node:
            inner_name = declarator.child_by_field_name("declarator")
            if inner_name:
                writes |= _collect_leaf_idents(inner_name, source_bytes, nodeset)
        if not params:
            params = declarator.child_by_field_name("parameters")
    if params:
        writes |= _collect_param_names(params, source_bytes, nodeset)
    return writes


@dataclass(frozen=True)
class NodeEffect:
    """Classification result for one AST node.

    ``descend`` indicates whether the generic tree walk should keep exploring the node.
    Nodes handled as complete semantic units return ``descend=False``.
    """
    reads: Set[str]
    writes: Set[str]
    descend: bool = False


@dataclass(frozen=True)
class ClassificationRule:
    predicate: NodePredicate
    handler: NodeHandler


_RAW_ROOT_NORMALIZERS = {
    "function_definition": _normalize_function_definition_raw_root,
}

_RAW_ID_AUGMENTERS = {
    "function_declarator": _augment_function_declarator_raw_ids,
}

_WRITE_AS_READ_RAW_ROOT_TYPES = frozenset({
    "function_declarator",
})

_NODE_READ_WRITE_HANDLERS = {
    "with_statement": _collect_with_statement_reads_writes,
}


def _normalize_raw_root(root: Node) -> Node:
    return _RAW_ROOT_NORMALIZERS.get(root.type, lambda current_root: current_root)(root)


def _augment_raw_ids(raw_root: Node, raw_ids: Set[str], source_bytes: bytes) -> Set[str]:
    return _RAW_ID_AUGMENTERS.get(
        raw_root.type,
        lambda current_root, current_ids, _source_bytes: current_ids,
    )(raw_root, raw_ids, source_bytes)


def _should_preserve_write_as_read(raw_root: Node) -> bool:
    return raw_root.type in _WRITE_AS_READ_RAW_ROOT_TYPES


def _promote_single_body_control_root(root: Node) -> Node:
    """Treat a single-statement control body as the analysis root when safe."""
    if root.type not in {"if_statement", "while_statement", "do_statement"}:
        return root
    return promote_single_statement_control_body(
        root,
        {"call_expression", "method_invocation", "call"},
        {"comment", "{", "}", ";", "if", "for", "while"},
    )


def _effect(reads: Set[str] | None = None, writes: Set[str] | None = None, descend: bool = False) -> NodeEffect:
    return NodeEffect(reads or set(), writes or set(), descend)


def _classify_assign_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, nodeset) -> NodeEffect:
    if n.child_count < 3:
        return _effect(reads=collect_ids(n))

    reads: Set[str] = set()
    writes: Set[str] = set()
    lhs = n.children[0]
    rhs = n.children[-1]
    if is_member_like(lhs, nodeset):
        all_lhs = collect_ids(lhs)
        last_child = lhs.children[-1] if lhs.children else None
        leaf_types = nodeset["ident"] | {"property_identifier", "field_identifier"}
        if last_child and last_child.type in leaf_types:
            # For member writes like ``window.location.href = ...``, only the leaf is
            # the write target; the receiver chain remains a read dependency.
            leaf = node_text(last_child, source_bytes)
            writes.add(leaf)
            reads |= (all_lhs - {leaf})
        else:
            # If the grammar does not expose a stable leaf, keep the conservative
            # behaviour and treat the whole chain as written.
            writes |= all_lhs
    else:
        writes |= collect_ids(lhs)
    reads |= collect_ids(rhs)
    return _effect(reads=reads, writes=writes)


def _handle_assign_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    return _classify_assign_node(n, source_bytes, collect_ids, nodeset)


def _classify_declaration_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, nodeset) -> NodeEffect:
    reads: Set[str] = set()
    writes = _collect_decl_names(n, source_bytes, nodeset)
    for ch in n.children:
        reads |= (collect_ids(ch) - writes)
    return _effect(reads=reads, writes=writes)


def _handle_declaration_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    return _classify_declaration_node(n, source_bytes, collect_ids, nodeset)


def _classify_call_node(n: Node, collect_ids: CollectIds) -> NodeEffect:
    return _effect(reads=collect_ids(n))


def _handle_call_node(n: Node, _source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, _nodeset) -> NodeEffect:
    return _classify_call_node(n, collect_ids)


def _classify_function_like_node(n: Node, source_bytes: bytes, nodeset) -> NodeEffect:
    return _effect(writes=_collect_function_like_writes(n, source_bytes, nodeset))


def _handle_node_type_reads_writes(n: Node, source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    node_reads, node_writes = _NODE_READ_WRITE_HANDLERS[n.type](n, source_bytes, collect_ids, nodeset)
    return _effect(reads=node_reads, writes=node_writes)


def _handle_function_like_node(n: Node, source_bytes: bytes, _collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    return _classify_function_like_node(n, source_bytes, nodeset)


def _classify_field_declaration_node(n: Node, source_bytes: bytes, collect_ids: CollectIds) -> NodeEffect:
    writes: Set[str] = set()
    all_ids = collect_ids(n)
    for ch in n.children:
        if ch.type == "field_identifier":
            writes.add(node_text(ch, source_bytes))
        if ch.type == "pointer_declarator":
            for sub in ch.children:
                if sub.type == "field_identifier":
                    writes.add(node_text(sub, source_bytes))
    return _effect(reads=(all_ids - writes), writes=writes)


def _handle_field_declaration_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, _nodeset) -> NodeEffect:
    return _classify_field_declaration_node(n, source_bytes, collect_ids)


def _classify_formal_parameters_node(n: Node, source_bytes: bytes, nodeset) -> NodeEffect:
    return _effect(writes=_collect_param_names(n, source_bytes, nodeset))


def _handle_formal_parameters_node(n: Node, source_bytes: bytes, _collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    return _classify_formal_parameters_node(n, source_bytes, nodeset)


def _classify_loop_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, lang_key: str, nodeset) -> NodeEffect:
    writes = _collect_loop_writes(n, source_bytes, lang_key, nodeset)
    all_ids = collect_ids(n)
    return _effect(reads=(all_ids - writes), writes=writes)


def _handle_loop_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, lang_key: str, nodeset) -> NodeEffect:
    return _classify_loop_node(n, source_bytes, collect_ids, lang_key, nodeset)


def _is_assign_node(n: Node, _lang_key: str, nodeset) -> bool:
    return is_assign(n, nodeset)


def _is_declaration_node(n: Node, _lang_key: str, nodeset) -> bool:
    return is_declaration(n, nodeset)


def _is_call_node(n: Node, _lang_key: str, nodeset) -> bool:
    return is_call(n, nodeset)


def _has_node_type_handler(n: Node, _lang_key: str, _nodeset) -> bool:
    return n.type in _NODE_READ_WRITE_HANDLERS


def _is_function_like_node(n: Node, _lang_key: str, _nodeset) -> bool:
    return n.type in {"function_definition", "function_declaration", "method_declaration"}


def _is_field_declaration_node(n: Node, _lang_key: str, _nodeset) -> bool:
    return n.type == "field_declaration"


def _is_formal_parameters_node(n: Node, _lang_key: str, _nodeset) -> bool:
    return n.type == "formal_parameters"


def _is_loop_node(n: Node, _lang_key: str, nodeset) -> bool:
    return is_loop(n, nodeset)


_CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(_is_assign_node, _handle_assign_node),
    ClassificationRule(_is_declaration_node, _handle_declaration_node),
    ClassificationRule(_is_call_node, _handle_call_node),
    ClassificationRule(_has_node_type_handler, _handle_node_type_reads_writes),
    ClassificationRule(_is_function_like_node, _handle_function_like_node),
    ClassificationRule(_is_field_declaration_node, _handle_field_declaration_node),
    ClassificationRule(_is_formal_parameters_node, _handle_formal_parameters_node),
    ClassificationRule(_is_loop_node, _handle_loop_node),
)


def _classify_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, lang_key: str, nodeset) -> NodeEffect:
    """Classify one node by the first matching rule and decide whether to descend."""
    for rule in _CLASSIFICATION_RULES:
        if rule.predicate(n, lang_key, nodeset):
            return rule.handler(n, source_bytes, collect_ids, lang_key, nodeset)
    return _effect(descend=True)


def split_reads_writes(root: Node, source_bytes: bytes, lang_key: str, nodeset) -> Tuple[Set[str], Set[str]]:
    """
    Split identifiers in a subtree into value reads and writes.

    The walker classifies whole semantic nodes such as assignments, declarations,
    calls, loops, and parameter lists. Anything not claimed as a write by those
    handlers is added back through the raw-identifier fallback below.
    """
    root = _promote_single_body_control_root(root)
    collect_ids = _make_collect_ids(source_bytes, nodeset)

    reads: Set[str] = set()
    writes: Set[str] = set()
    stack: List[Node] = [root]

    while stack:
        n = stack.pop()
        effect = _classify_node(n, source_bytes, collect_ids, lang_key, nodeset)
        reads |= effect.reads
        writes |= effect.writes
        if effect.descend:
            stack.extend(n.children)

    # Final safety net: any value-like identifier we did not classify as a write is
    # still considered a read dependency of this subtree.
    raw_root = _normalize_raw_root(root)
    raw_ids = collect_ids(raw_root)
    raw_ids = _augment_raw_ids(raw_root, raw_ids, source_bytes)
    reads |= (raw_ids - writes)
    if _should_preserve_write_as_read(raw_root):
        reads |= (raw_ids & writes)
    return reads, writes
