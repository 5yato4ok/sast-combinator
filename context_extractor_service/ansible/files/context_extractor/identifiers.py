from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

from tree_sitter import Node

from .config import LANG_NODESETS
from .shell_wrappers import (
    find_shell_wrapper_command_text,
    is_bash_redirect_operator,
    is_input_redirect_operator,
    is_output_redirect_operator,
    normalize_shell_word_text,
)
from .ts_utils import BASH_LANGUAGE, create_parser, node_text, promote_single_statement_control_body

def is_identifier(n: Node, nodeset) -> bool:    return n.type in nodeset["ident"]
def is_runtime_identifier(n: Node, nodeset) -> bool: return n.type in nodeset.get("runtime_ident", nodeset["ident"])
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
        if is_runtime_identifier(n, nodeset) or n.type in _VALUE_KEYWORDS:
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

    if not out:
        stack: List[Node] = list(n.children)
        while stack:
            current = stack.pop()
            if current.type in {"variable_declarator", "init_declarator", "public_field_definition"}:
                name_node = current.child_by_field_name("name")
                if name_node is None:
                    name_node = current.child_by_field_name("declarator")
                if name_node is not None:
                    out |= _collect_leaf_idents(name_node, source_bytes, nodeset)
                    continue
            # Go: var_spec holds the binding name(s)
            if current.type == "var_spec":
                handled = False
                name_node = current.child_by_field_name("name")
                if name_node is not None:
                    out |= _collect_leaf_idents(name_node, source_bytes, nodeset)
                    handled = True
                else:
                    # identifier_list or bare identifier
                    for ch in current.children:
                        if is_identifier(ch, nodeset) or ch.type == "identifier_list":
                            out |= _collect_leaf_idents(ch, source_bytes, nodeset)
                            handled = True
                            break
                if handled:
                    continue
            # Kotlin: multi_variable_declaration wraps individual variable_declaration nodes
            if current.type in {"multi_variable_declaration", "variable_declaration"}:
                handled = False
                inner = current.child_by_field_name("name")
                if inner is not None:
                    text = node_text(inner, source_bytes).strip()
                    if text:
                        out.add(text)
                        handled = True
                if not handled:
                    for ch in current.children:
                        if is_identifier(ch, nodeset) or ch.type == "simple_identifier":
                            out.add(node_text(ch, source_bytes))
                            handled = True
                            break
                if handled:
                    continue
            stack.extend(current.children)

    # TypeScript class field: public_field_definition with property_identifier name
    if not out and n.type == "public_field_definition":
        name_node = n.child_by_field_name("name")
        if name_node is not None:
            name_text = node_text(name_node, source_bytes).strip()
            if name_text:
                out.add(name_text)

    # Fallback for simpler grammars that surface the binding as a direct child.
    if not out:
        for child in n.children:
            if is_identifier(child, nodeset) or child.type in {"simple_identifier", "property_identifier"}:
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
    "csharp": frozenset({"identifier"}),
    "php": frozenset({"variable_name", "name"}),
    "typescript": frozenset({"identifier", "lexical_declaration", "variable_declarator"}),
    "kotlin": frozenset({"variable_declaration", "multi_variable_declaration"}),
}

_BINDING_DECLARATOR_TYPES = frozenset({"variable_declarator", "init_declarator", "public_field_definition"})


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
    left = loop_node.child_by_field_name("left")
    if left is not None:
        return collect_idents_in_node(left, source_bytes, nodeset)
    # For C++ for_range_loop (and similar): the declarator field holds the binding
    # variable(s) while the right/range field is the iterable — not a write target.
    declarator = loop_node.child_by_field_name("declarator")
    if declarator is not None:
        return collect_idents_in_node(declarator, source_bytes, nodeset)
    write_child_types = _LOOP_WRITE_CHILD_TYPES.get(lang_key, frozenset())
    if not write_child_types:
        return writes
    for child in loop_node.children:
        if child.type in write_child_types:
            writes |= collect_idents_in_node(child, source_bytes, nodeset)
    return writes


def _collect_callable_binding_writes(node: Node, source_bytes: bytes, nodeset) -> Set[str]:
    writes: Set[str] = set()
    stack: List[Node] = [node]
    while stack:
        current = stack.pop()
        if current.type in _BINDING_DECLARATOR_TYPES:
            value = current.child_by_field_name("value")
            if value is not None and is_function_like(value, nodeset):
                writes |= _collect_function_like_writes(value, source_bytes, nodeset)
                continue
        stack.extend(current.children)
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


def _parse_nested_bash_reads_writes(source: str) -> Tuple[Set[str], Set[str]]:
    parser = create_parser(BASH_LANGUAGE)
    source_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)
    root = tree.root_node
    if root.child_count == 1:
        root = root.children[0]
    return split_reads_writes(root, source_bytes, "bash", LANG_NODESETS["bash"])


def _collect_redirect_target_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
) -> Tuple[Set[str], Set[str]]:
    reads: Set[str] = set()
    writes: Set[str] = set()
    for redirect in _iter_children_of_type(node, "file_redirect"):
        operator = next((child.type for child in redirect.children if is_bash_redirect_operator(child.type)), None)
        target = next(
            (
                child for child in reversed(redirect.children)
                if not is_bash_redirect_operator(child.type)
            ),
            None,
        )
        if target is None:
            continue
        target_reads = collect_ids(target)
        target_text = normalize_shell_word_text(node_text(target, source_bytes))
        reads |= target_reads
        if is_input_redirect_operator(operator) and target_text:
            reads.add(target_text)
        if is_output_redirect_operator(operator) and target_text:
            writes.add(target_text)
    return reads, writes


def _collect_redirected_statement_reads_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    _nodeset,
) -> Tuple[Set[str], Set[str]]:
    reads: Set[str] = set()
    writes: Set[str] = set()
    command = next((child for child in node.children if child.type == "command"), None)
    if command is not None:
        reads |= collect_ids(command)
    redirect_reads, redirect_writes = _collect_redirect_target_writes(node, source_bytes, collect_ids)
    reads |= redirect_reads
    writes |= redirect_writes
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
    if not params:
        params = next(
            (
                child for child in node.children
                if child.type in {"implicit_parameter", "parameter", "parameter_list", "formal_parameters"}
            ),
            None,
        )
    if params:
        if params.type == "implicit_parameter":
            writes.add(node_text(params, source_bytes))
        else:
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


def _collect_case_pattern_captures(root: Node, source_bytes: bytes) -> Set[str]:
    """Collect capture-variable identifiers from a match/case pattern subtree.

    A capture is a simple (single-segment, no dots) name inside a ``case_pattern``
    node.  Dotted names with dots are value patterns, not captures.

    Also handles keyword patterns: ``case Point(x=px, y=py)`` produces
    ``keyword_pattern`` nodes of the form ``identifier = dotted_name``.  The
    right-hand ``dotted_name`` (when single-segment) is the capture variable.
    """
    captures: Set[str] = set()
    stack: List[Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == "case_pattern":
            for child in node.children:
                if child.type == "dotted_name":
                    text = node_text(child, source_bytes)
                    if "." not in text:
                        for sub in child.children:
                            if sub.type == "identifier":
                                captures.add(node_text(sub, source_bytes))
        # keyword_pattern: key = capture_variable  (e.g. x=px inside a class pattern)
        if node.type == "keyword_pattern":
            found_eq = False
            for child in node.children:
                if child.type == "=":
                    found_eq = True
                    continue
                if found_eq:
                    if child.type == "dotted_name":
                        text = node_text(child, source_bytes)
                        if "." not in text:
                            for sub in child.children:
                                if sub.type == "identifier":
                                    captures.add(node_text(sub, source_bytes))
                    elif child.type == "identifier":
                        captures.add(node_text(child, source_bytes))
                    break
        stack.extend(c for c in node.children if c.type != "if_clause")
    return captures


def _collect_case_clause_reads_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    nodeset,
) -> Tuple[Set[str], Set[str]]:
    """Classify a Python ``case_clause`` node.

    Pattern-binding identifiers (captures) are writes; the body block identifiers
    are reads.
    """
    reads: Set[str] = set()
    writes: Set[str] = set()
    for child in node.children:
        if child.type in {"case_pattern", "list_pattern", "dict_pattern",
                          "class_pattern", "as_pattern"}:
            writes |= _collect_case_pattern_captures(child, source_bytes)
        elif child.type == "block":
            reads |= collect_ids(child)
        elif child.type not in {"case", ":"}:
            reads |= collect_ids(child)
    return reads, writes


def _collect_except_clause_reads_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    nodeset,
) -> Tuple[Set[str], Set[str]]:
    """Classify a Python ``except_clause`` (including ``except*``) node.

    The ``as``-bound variable is a write; everything else is a read.
    """
    reads: Set[str] = set()
    writes: Set[str] = set()
    for child in node.children:
        if child.type == "as_pattern":
            target_node = child.child_by_field_name("alias")
            # as_pattern_target is the alias in except ... as <alias>
            for sub in child.children:
                if sub.type == "as_pattern_target":
                    writes |= _collect_leaf_idents(sub, source_bytes, nodeset)
            # The exception type itself is a read
            value_node = child.child_by_field_name("value")
            if value_node:
                reads |= collect_ids(value_node)
            elif target_node:
                # If grammar uses alias field for the target, the non-alias part is a read
                for sub in child.children:
                    if sub.type not in {"as", "as_pattern_target"}:
                        reads |= collect_ids(sub)
        elif child.type not in {"except", ":", "*"}:
            reads |= collect_ids(child)
    return reads, writes


def _collect_declaration_pattern_reads_writes(
    node: Node,
    source_bytes: bytes,
    collect_ids: CollectIds,
    nodeset,
) -> Tuple[Set[str], Set[str]]:
    """Handle C# declaration_pattern: last identifier child is the binding variable (write).

    For ``Circle c`` → writes={'c'}, reads={'Circle'}
    For ``var len``   → writes={'len'}, reads={}  (implicit_type has no identifier)
    """
    ident_children = [ch for ch in node.children if ch.type == "identifier"]
    if not ident_children:
        return set(), set()
    write_name = node_text(ident_children[-1], source_bytes)
    read_names = {node_text(ch, source_bytes) for ch in ident_children[:-1]}
    return read_names, {write_name}


_NODE_READ_WRITE_HANDLERS: dict = {
    "redirected_statement": _collect_redirected_statement_reads_writes,
    "with_statement": _collect_with_statement_reads_writes,
    "declaration_pattern": _collect_declaration_pattern_reads_writes,
    "case_clause": _collect_case_clause_reads_writes,
    "except_clause": _collect_except_clause_reads_writes,
    # Python 3.11+ except* groups use the same binding semantics as except
    "except_group_clause": _collect_except_clause_reads_writes,
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

    # Handle TypeScript `using resource = ...` where tree-sitter emits an
    # assignment_expression with the `using` keyword as children[0] and the
    # actual write target as children[1].
    lhs_idx = 0
    if n.children[0].type == "using" and n.child_count >= 4:
        lhs_idx = 1

    reads: Set[str] = set()
    writes: Set[str] = set()
    lhs = n.children[lhs_idx]
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
    writes = _collect_decl_names(n, source_bytes, nodeset) | _collect_callable_binding_writes(
        n, source_bytes, nodeset,
    )
    for ch in n.children:
        reads |= (collect_ids(ch) - writes)
    return _effect(reads=reads, writes=writes)


def _handle_declaration_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, _lang_key: str, nodeset) -> NodeEffect:
    return _classify_declaration_node(n, source_bytes, collect_ids, nodeset)


def _classify_call_node(n: Node, collect_ids: CollectIds) -> NodeEffect:
    return _effect(reads=collect_ids(n))


def _handle_call_node(n: Node, source_bytes: bytes, collect_ids: CollectIds, lang_key: str, nodeset) -> NodeEffect:
    effect = _classify_call_node(n, collect_ids)
    if lang_key != "bash" or n.type != "command":
        return effect
    # Special case: `trap HANDLER SIGNAL` — the handler name is a function reference (read).
    trap_reads = _collect_bash_trap_handler_reads(n, source_bytes)
    if trap_reads:
        return _effect(reads=(effect.reads | trap_reads))
    inner_command = find_shell_wrapper_command_text(n, source_bytes)
    if not inner_command:
        return effect
    inner_reads, inner_writes = _parse_nested_bash_reads_writes(inner_command)
    return _effect(reads=(effect.reads | inner_reads), writes=inner_writes)


def _collect_bash_trap_handler_reads(node: Node, source_bytes: bytes) -> Set[str]:
    """Extract function-name references from bash ``trap HANDLER SIGNAL`` commands."""
    children = [c for c in node.children if c.is_named]
    # children[0] = command_name (trap), children[1] = handler, children[2] = signal
    if len(children) < 2:
        return set()
    cmd_name = children[0]
    if node_text(cmd_name, source_bytes) != "trap":
        return set()
    handler = children[1]
    handler_text = node_text(handler, source_bytes).strip("'\"")
    # Skip compound trap actions like 'echo interrupted' (contain spaces)
    if not handler_text or " " in handler_text or handler_text.startswith("-"):
        return set()
    return {handler_text}


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
    return is_function_like(n, _nodeset)


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
