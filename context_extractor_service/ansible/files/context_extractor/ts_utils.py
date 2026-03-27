from __future__ import annotations

from pathlib import Path

import tree_sitter_bash as bash_lang
import tree_sitter_c_sharp as csharp_lang
import tree_sitter_cpp as cpp_lang
import tree_sitter_go as go_lang
import tree_sitter_hcl as hcl_lang
import tree_sitter_html as html_lang
import tree_sitter_java as java_lang
import tree_sitter_javascript as js_lang
import tree_sitter_json as json_lang
import tree_sitter_kotlin as kotlin_lang
import tree_sitter_php as php_lang
import tree_sitter_python as py_lang
import tree_sitter_ruby as ruby_lang
import tree_sitter_toml as toml_lang
import tree_sitter_typescript as ts_lang

# Config language grammars
import tree_sitter_yaml as yaml_lang
from tree_sitter import Language, Node, Parser
from tree_sitter_language_pack import get_language as _lp_get_language


def _resolve_language(mod, *candidate_funcs: str) -> Language:
    """
    Return a tree_sitter.Language by trying a list of possible factory names
    exported by the grammar module (language(), language_typescript(), etc).
    """
    for name in candidate_funcs:
        fn = getattr(mod, name, None)
        if callable(fn):
            return Language(fn())
    msg = f"{mod.__name__} has none of {candidate_funcs}"
    raise AttributeError(msg)


# Load compiled languages once — source code languages
CPP_LANGUAGE = _resolve_language(cpp_lang, "language", "language_cpp")
PY_LANGUAGE = _resolve_language(py_lang, "language", "language_python")
JS_LANGUAGE = _resolve_language(js_lang, "language", "language_javascript")
TYPESCRIPT_LANGUAGE = _resolve_language(ts_lang, "language", "language_typescript")
TSX_LANGUAGE = _resolve_language(ts_lang, "language_tsx")
JAVA_LANGUAGE = _resolve_language(java_lang, "language", "language_java")
CSHARP_LANGUAGE = _resolve_language(csharp_lang, "language", "language_c_sharp")
KOTLIN_LANGUAGE = _resolve_language(kotlin_lang, "language", "language_kotlin")
GO_LANGUAGE = _resolve_language(go_lang, "language", "language_go")
RUBY_LANGUAGE = _resolve_language(ruby_lang, "language", "language_ruby")
PHP_LANGUAGE = _resolve_language(php_lang, "language", "language_php")

# Load compiled languages once — config languages
YAML_LANGUAGE = _resolve_language(yaml_lang, "language", "language_yaml")
HCL_LANGUAGE = _resolve_language(hcl_lang, "language", "language_hcl")
TOML_LANGUAGE = _resolve_language(toml_lang, "language", "language_toml")
JSON_LANGUAGE = _resolve_language(json_lang, "language", "language_json")
BASH_LANGUAGE = _resolve_language(bash_lang, "language", "language_bash")
HTML_LANGUAGE = _resolve_language(html_lang, "language", "language_html")

# Dockerfile grammar via tree-sitter-language-pack (cross-platform, aarch64+x86_64).
# tree-sitter-dockerfile has no Linux aarch64 wheel; language-pack provides it.
DOCKERFILE_LANGUAGE: Language = _lp_get_language("dockerfile")

# Extension → (Language, lang_key) mapping.
# _LANG_KEY_MAP is used by detect_language to return a human-readable key.
_LANG_KEY_MAP: dict[Language, str] = {
    CPP_LANGUAGE: "cpp",
    PY_LANGUAGE: "python",
    JS_LANGUAGE: "javascript",
    JAVA_LANGUAGE: "java",
    CSHARP_LANGUAGE: "csharp",
    TYPESCRIPT_LANGUAGE: "typescript",
    TSX_LANGUAGE: "typescript",
    GO_LANGUAGE: "go",
    RUBY_LANGUAGE: "ruby",
    KOTLIN_LANGUAGE: "kotlin",
    PHP_LANGUAGE: "php",
    YAML_LANGUAGE: "yaml",
    HCL_LANGUAGE: "hcl",
    TOML_LANGUAGE: "toml",
    JSON_LANGUAGE: "json",
    BASH_LANGUAGE: "bash",
    HTML_LANGUAGE: "html",
    DOCKERFILE_LANGUAGE: "dockerfile",
}

SUPPORTED_LANGUAGES = {
    # Source code
    ".py": PY_LANGUAGE,
    ".h": CPP_LANGUAGE,
    ".hpp": CPP_LANGUAGE,
    ".cpp": CPP_LANGUAGE,
    ".c": CPP_LANGUAGE,
    ".cc": CPP_LANGUAGE,
    ".cxx": CPP_LANGUAGE,
    ".js": JS_LANGUAGE,
    ".mjs": JS_LANGUAGE,
    ".cjs": JS_LANGUAGE,
    ".java": JAVA_LANGUAGE,
    ".cs": CSHARP_LANGUAGE,
    ".ts": TYPESCRIPT_LANGUAGE,
    ".tsx": TSX_LANGUAGE,
    ".jsx": JS_LANGUAGE,
    ".go": GO_LANGUAGE,
    ".rb": RUBY_LANGUAGE,
    ".kt": KOTLIN_LANGUAGE,
    ".php": PHP_LANGUAGE,
    # Config languages
    ".yaml": YAML_LANGUAGE,
    ".yml": YAML_LANGUAGE,
    ".json": JSON_LANGUAGE,
    ".toml": TOML_LANGUAGE,
    ".tf": HCL_LANGUAGE,
    ".tfvars": HCL_LANGUAGE,
    ".hcl": HCL_LANGUAGE,
    ".sh": BASH_LANGUAGE,
    ".bash": BASH_LANGUAGE,
    # HTML
    ".html": HTML_LANGUAGE,
    ".htm": HTML_LANGUAGE,
}

# Files matched by full name (no extension-based matching)
_FILENAME_LANGUAGES: dict[str, Language] = {
    "dockerfile": DOCKERFILE_LANGUAGE,
    "Dockerfile": DOCKERFILE_LANGUAGE,
}


def detect_language(filepath: Path) -> tuple[Language, str]:
    # Try exact filename first (e.g. "Dockerfile" has no extension)
    lang = _FILENAME_LANGUAGES.get(filepath.name)
    if lang is None:
        ext = filepath.suffix.lower()
        lang = SUPPORTED_LANGUAGES.get(ext)
    if lang is None:
        msg = f"Unsupported file extension: {filepath.suffix}"
        raise ValueError(msg)
    key = _LANG_KEY_MAP.get(lang, "unknown")
    return lang, key


def create_parser(lang: Language) -> Parser:
    return Parser(lang)


def node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace")


def line_range(node: Node) -> tuple[int, int]:
    return node.start_point[0], node.end_point[0]


def find_enclosing_function(
    root: Node,
    line_number: int,
    func_types: set[str],
) -> Node | None:
    """Find the outermost function node enclosing *line_number* (1-based).

    Returns the first (topmost) function node that contains the target line,
    consistent with the original recursive implementations.  Nested functions
    (e.g. arrow callbacks inside a method) are NOT returned — the enclosing
    named function is.

    Iterative DFS to avoid RecursionError on deeply nested code.
    """
    stack: list[Node] = [root]
    while stack:
        n = stack.pop()
        s, e = n.start_point[0], n.end_point[0]
        if not (s + 1 <= line_number <= e + 1):
            continue
        if n.type in func_types:
            return n  # Outermost match — stop; don't recurse into nested functions
        stack.extend(n.children)
    return None


def find_deepest_node_at_line(
    root: Node,
    line_number: int,
) -> Node | None:
    """Find the deepest (smallest) AST node that covers *line_number* (1-based).

    Iterative implementation to avoid RecursionError.
    """
    target_0 = line_number - 1  # convert to 0-based
    current = root
    if not (current.start_point[0] <= target_0 <= current.end_point[0]):
        return None
    while True:
        went_deeper = False
        for ch in current.children:
            if ch.start_point[0] <= target_0 <= ch.end_point[0]:
                current = ch
                went_deeper = True
                break
        if not went_deeper:
            return current


def promote_single_statement_control_body(
    root: Node,
    call_node_types: set[str],
    excluded_body_types: set[str],
) -> Node:
    """Promote a control node to its single body statement when the header is simple."""
    header_line = root.start_point[0]
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.start_point[0] == header_line and node.type in call_node_types:
            return root
        stack.extend(node.children)

    body_children = [
        child for child in root.children
        if child.start_point[0] > header_line and child.type not in excluded_body_types
    ]
    if len(body_children) == 1:
        return body_children[0]
    return root


def inject_html_script_source(
    source_code: str,
    line_number: int,
    lang: Language,
    lang_key: str,
) -> tuple[Language, str, str, int]:
    """Re-parse inline ``<script>`` content as JavaScript when a line hits HTML raw_text."""
    if lang_key != "html":
        return lang, lang_key, source_code, line_number

    parser = create_parser(lang)
    source_bytes = source_code.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)

    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "script_element":
            raw_text = next((child for child in node.children if child.type == "raw_text"), None)
            if raw_text is not None:
                start_line = raw_text.start_point[0] + 1
                end_line = raw_text.end_point[0] + 1
                if start_line <= line_number <= end_line:
                    script_source = source_bytes[raw_text.start_byte:raw_text.end_byte].decode(
                        "utf-8",
                        errors="replace",
                    )
                    adjusted_line = line_number - start_line + 1
                    if script_source.startswith("\n"):
                        adjusted_line += 1
                    return JS_LANGUAGE, "javascript", script_source, adjusted_line
        stack.extend(reversed(node.children))

    return lang, lang_key, source_code, line_number
