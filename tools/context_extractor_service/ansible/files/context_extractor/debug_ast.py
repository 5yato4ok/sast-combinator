from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import sys

# --- Prefer your helpers; fall back to local init if absent ---
try:
    from .ts_utils import detect_language, create_parser
    HAVE_TS_UTILS = True
except Exception:
    HAVE_TS_UTILS = False
    import tree_sitter_cpp as cpp_lang
    import tree_sitter_python as py_lang
    import tree_sitter_javascript as js_lang
    import tree_sitter_java as java_lang
    from tree_sitter import Language, Parser as TSParser

    CPP_LANGUAGE = Language(cpp_lang.language())
    PY_LANGUAGE = Language(py_lang.language())
    JS_LANGUAGE = Language(js_lang.language())
    JAVA_LANGUAGE = Language(java_lang.language())

    _SUPPORTED = {
        ".h": CPP_LANGUAGE, ".hpp": CPP_LANGUAGE, ".cpp": CPP_LANGUAGE,
        ".c": CPP_LANGUAGE, ".cc": CPP_LANGUAGE, ".cxx": CPP_LANGUAGE,
        ".py": PY_LANGUAGE,
        ".js": JS_LANGUAGE, ".mjs": JS_LANGUAGE, ".cjs": JS_LANGUAGE,
        ".java": JAVA_LANGUAGE,
    }

    def detect_language(path: Path):
        ext = path.suffix.lower()
        if ext not in _SUPPORTED:
            raise ValueError(f"Unsupported extension: {ext}")
        lang = _SUPPORTED[ext]
        if lang is CPP_LANGUAGE:
            key = "cpp"
        elif lang is PY_LANGUAGE:
            key = "python"
        elif lang is JS_LANGUAGE:
            key = "javascript"
        elif lang is JAVA_LANGUAGE:
            key = "java"
        else:
            key = "cpp"
        return lang, key

    def create_parser(lang):
        # критично: инициализация именно так
        return TSParser(lang)

from tree_sitter import Node, TreeCursor


@dataclass
class DumpOpts:
    show_text: bool = True
    text_limit: int = 60
    max_nodes: int = 10000
    show_bytes: bool = False
    include_unnamed: bool = True
    indent: str = "  "
    one_line_text: bool = True


def _node_span_str(n: Node) -> str:
    sL, sC = n.start_point
    eL, eC = n.end_point
    return f"{sL+1}:{sC}-{eL+1}:{eC}"


def _node_text_snippet(n: Node, src: bytes, limit: int, one_line: bool) -> str:
    s = src[n.start_byte:n.end_byte].decode("utf-8", errors="replace")
    if one_line:
        s = s.replace("\r", "").replace("\n", " ")
    if len(s) > limit:
        s = s[:limit] + "…"
    return s


def _cursor_field_name(cur: TreeCursor) -> Optional[str]:
    """
    Cross-version accessor:
      - newer bindings: `field_name` (property, may be bytes/str/None)
      - older bindings: `current_field_name()` (method)
    """
    name = None
    if hasattr(cur, "field_name"):
        name = cur.field_name
    elif hasattr(cur, "current_field_name"):
        try:
            name = cur.current_field_name()
        except TypeError:
            # some builds expose it as property without parens
            name = getattr(cur, "current_field_name", None)
    if isinstance(name, bytes):
        try:
            name = name.decode("utf-8", errors="replace")
        except Exception:
            name = str(name)
    if name is not None and not isinstance(name, str):
        name = str(name)
    return name


def _dump_subtree_with_fields(root: Node, src: bytes, opts: DumpOpts) -> List[str]:
    """
    Walk subtree using TreeCursor to capture each child's field name.
    """
    cur = root.walk()
    lines: List[str] = []
    count = 0

    def emit(n: Node, depth: int, field_name: Optional[str]):
        nonlocal count
        if count >= opts.max_nodes:
            return
        pieces = [opts.indent * depth]
        if field_name:
            pieces += [f"{field_name}: "]
        pieces += [n.type, f" [{_node_span_str(n)}]"]
        if opts.show_bytes:
            pieces += [f" <{n.start_byte}-{n.end_byte}>"]
        if opts.show_text:
            pieces += [" :: ", _node_text_snippet(n, src, opts.text_limit, opts.one_line_text)]
        lines.append("".join(pieces))
        count += 1

    def walk(depth: int):
        if count >= opts.max_nodes:
            return
        # emit current node
        emit(cur.node, depth, _cursor_field_name(cur))
        # descend into children
        if cur.goto_first_child():
            try:
                while True:
                    # even if unnamed nodes are not included, we still traverse through them,
                    # otherwise we'd miss named grandchildren.
                    walk(depth + 1)
                    if not cur.goto_next_sibling():
                        break
            finally:
                cur.goto_parent()

    walk(0)
    if count >= opts.max_nodes:
        lines.append(f"{opts.indent}… (truncated at {opts.max_nodes} nodes)")
    return lines


def _find_enclosing_function(root: Node, line_1based: int, lang_key: str) -> Optional[Node]:
    # lazy import of config to keep this file standalone-friendly
    try:
        from .config import LANG_NODESETS
    except Exception:
        LANG_NODESETS = {
            "cpp": {"function": {"function_definition", "function_declaration", "lambda_expression"}},
            "java": {"function": {"method_declaration", "constructor_declaration", "lambda_expression"}},
            "javascript": {"function": {"function_declaration", "function", "method_definition", "arrow_function"}},
            "python": {"function": {"function_definition", "lambda"}},
        }
    func_types = LANG_NODESETS.get(lang_key, {}).get("function", set())

    def is_func(n: Node) -> bool:
        return n.type in func_types

    def dfs(n: Node) -> Optional[Node]:
        sL, eL = n.start_point[0] + 1, n.end_point[0] + 1
        if not (sL <= line_1based <= eL):
            return None
        if is_func(n):
            return n
        for ch in n.children:
            hit = dfs(ch)
            if hit:
                return hit
        return None

    return dfs(root)


def function_ast_to_string(
    source_code: str,
    filename: str,
    line_number: int,
    opts: Optional[DumpOpts] = None,
) -> str:
    if opts is None:
        opts = DumpOpts()

    if line_number <= 0:
        return "// invalid line number"

    src_bytes = source_code.encode("utf-8", errors="replace")
    try:
        lang, lang_key = detect_language(Path(filename))
    except Exception as e:
        return f"// detect_language failed: {e}"

    parser = create_parser(lang)
    tree = parser.parse(src_bytes)

    func = _find_enclosing_function(tree.root_node, line_number, lang_key)
    if not func:
        return "// function not found"

    lines = _dump_subtree_with_fields(func, src_bytes, opts)
    header = [
        f"// lang={lang_key}, file={filename}",
        f"// function span: {func.start_point[0]+1}:{func.start_point[1]} - {func.end_point[0]+1}:{func.end_point[1]}",
        "",
    ]
    return "\n".join(header + lines)


def print_function_ast(
    source_code: str,
    filename: str,
    line_number: int,
    **kwargs,
) -> None:
    opts = DumpOpts(**kwargs)
    print(function_ast_to_string(source_code, filename, line_number, opts))


# --- CLI для быстрого дебага: python -m context_extractor.debug_ast file.cpp:LINE ---
if __name__ == "__main__":
    # if not sys.argv[1:]:
    #     print("usage: python -m context_extractor.debug_ast <path or file://url>:<line> [text_limit]")
    #     sys.exit(2)
    #
    # target = sys.argv[1]
    # tl = int(sys.argv[2]) if len(sys.argv) > 2 else 80

    # # простая загрузка файла с диска/URL
    # if "://" in target:
    #     from urllib.parse import urlparse, unquote
    #     import requests
    #     u, ln = target.rsplit(":", 1)
    #     ln = int(ln)
    #     parsed = urlparse(u)
    #     if parsed.scheme == "file":
    #         p = Path(unquote(parsed.path))
    #         text = p.read_text(encoding="utf-8", errors="replace")
    #         fname = p.name
    #     else:
    #         r = requests.get(u, timeout=15)
    #         r.raise_for_status()
    #         text = r.text
    #         fname = Path(parsed.path).name
    # else:
    #     p, ln = target.rsplit(":", 1)
    ln = 243
    path = Path("/Users/butkevichveronika/develop/nx_copy/open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/lookup_lists/lookup_list_action_handler.cpp")
    text = path.read_text(encoding="utf-8", errors="replace")
    fname = path.name

    print(function_ast_to_string(text, fname, ln))
