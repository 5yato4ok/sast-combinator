from __future__ import annotations

from pathlib import Path

import tree_sitter_bash as bash_lang
import tree_sitter_c_sharp as csharp_lang
import tree_sitter_cpp as cpp_lang
import tree_sitter_dockerfile as dockerfile_lang
import tree_sitter_go as go_lang
import tree_sitter_hcl as hcl_lang
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

# tree-sitter-dockerfile v0.2.0 has a broken binding (no language() export).
# Load it gracefully — if unavailable, Dockerfiles fall back to text analysis.
try:
    DOCKERFILE_LANGUAGE = _resolve_language(dockerfile_lang, "language", "language_dockerfile")
except AttributeError:
    DOCKERFILE_LANGUAGE = None

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
}
if DOCKERFILE_LANGUAGE:
    _LANG_KEY_MAP[DOCKERFILE_LANGUAGE] = "dockerfile"

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
}

# Files matched by full name (no extension-based matching)
_FILENAME_LANGUAGES: dict[str, Language] = {}
if DOCKERFILE_LANGUAGE:
    _FILENAME_LANGUAGES["dockerfile"] = DOCKERFILE_LANGUAGE
    _FILENAME_LANGUAGES["Dockerfile"] = DOCKERFILE_LANGUAGE


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
    # Use the environment's working constructor (user wants Parser(lang))
    return Parser(lang)


def node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace")


def line_range(node: Node) -> tuple[int, int]:
    return node.start_point[0], node.end_point[0]
