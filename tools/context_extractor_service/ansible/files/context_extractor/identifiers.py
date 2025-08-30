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
                if is_identifier(ch, nodeset):
                    ids.add(node_text(ch, source_bytes))
        stack.extend(n.children)
    return ids

def _collect_decl_names(n: Node, source_bytes: bytes, nodeset) -> Set[str]:
    """Грубовато: под декларацией пробегаемся вглубь и всё, что похоже на идентификатор, считаем 'write'."""
    out: Set[str] = set()
    stack: List[Node] = [n]
    while stack:
        x = stack.pop()
        if is_identifier(x, nodeset):
            out.add(node_text(x, source_bytes))
        else:
            stack.extend(x.children)
    return out

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
            # Обычно у TS присваивание: <lhs> '=' <rhs> или compound-assign с такой же структурой.
            if n.child_count >= 3:
                lhs = n.children[0]
                rhs = n.children[-1]
                writes |= collect_idents_in_node(lhs, source_bytes, nodeset)
                reads  |= collect_idents_in_node(rhs, source_bytes, nodeset)
            else:
                reads |= collect_idents_in_node(n, source_bytes, nodeset)

        elif is_declaration(n, nodeset):
            # Имя(ена) переменных считаем write, часть-инициализатор — read
            # Перебираем потомков, ищем идентификаторы глубоко.
            decl_names = _collect_decl_names(n, source_bytes, nodeset)
            writes |= decl_names
            # Всё остальное внутри считаем как reads (грубо, но практично)
            for ch in n.children:
                reads |= (collect_idents_in_node(ch, source_bytes, nodeset) - decl_names)

        elif is_call(n, nodeset):
            reads |= collect_idents_in_node(n, source_bytes, nodeset)

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
            continue

        # продолжаем обход вниз
        stack.extend(n.children)

    # Базовая подстраховка: всё, что не классифицировали как write, считаем read
    raw_ids = collect_idents_in_node(root, source_bytes, nodeset)
    reads |= (raw_ids - writes)
    return reads, writes
