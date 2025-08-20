from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
import tree_sitter_typescript as ts_lang
import tree_sitter_java as java_lang
import tree_sitter_c_sharp as csharp_lang
import tree_sitter_kotlin as kotlin_lang
import tree_sitter_go as go_lang
import tree_sitter_ruby as ruby_lang

def _resolve_language(mod, *candidate_funcs: str) -> Language:
    """
    Return a tree_sitter.Language by trying a list of possible factory names
    exported by the grammar module (language(), language_typescript(), etc).
    """
    for name in candidate_funcs:
        fn = getattr(mod, name, None)
        if callable(fn):
            return Language(fn())
    raise AttributeError(f"{mod.__name__} has none of {candidate_funcs}")

# Load compiled languages once
CPP_LANGUAGE     = _resolve_language(cpp_lang,     "language", "language_cpp")
PY_LANGUAGE      = _resolve_language(py_lang,      "language", "language_python")
JS_LANGUAGE      = _resolve_language(js_lang,      "language", "language_javascript")
TYPESCRIPT_LANGUAGE = _resolve_language(ts_lang,   "language", "language_typescript")
JAVA_LANGUAGE    = _resolve_language(java_lang,    "language", "language_java")
CSHARP_LANGUAGE  = _resolve_language(csharp_lang,  "language", "language_c_sharp")
KOTLIN_LANGUAGE  = _resolve_language(kotlin_lang,  "language", "language_kotlin")
GO_LANGUAGE      = _resolve_language(go_lang,      "language", "language_go")
RUBY_LANGUAGE    = _resolve_language(ruby_lang,    "language", "language_ruby")

SUPPORTED_LANGUAGES = {
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
    ".cs" : CSHARP_LANGUAGE,
    ".ts" : TYPESCRIPT_LANGUAGE,
    ".go" : GO_LANGUAGE,
    ".rb" : RUBY_LANGUAGE,
    ".kt" : KOTLIN_LANGUAGE
}

def detect_language(filepath: Path) -> tuple[Language, str]:
    ext = filepath.suffix.lower()
    if ext not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported file extension: {ext}")
    lang = SUPPORTED_LANGUAGES[ext]
    if lang is CPP_LANGUAGE:  return lang, "cpp"
    if lang is PY_LANGUAGE:   return lang, "python"
    if lang is JS_LANGUAGE:   return lang, "javascript"
    if lang is JAVA_LANGUAGE: return lang, "java"
    if lang is CSHARP_LANGUAGE: return lang, "csharp"
    if lang is TYPESCRIPT_LANGUAGE: return lang, "typescript"
    if lang is GO_LANGUAGE: return lang, "go"
    if lang is RUBY_LANGUAGE: return lang, "ruby"
    if lang is KOTLIN_LANGUAGE: return lang, "kotlin"
    return lang, "cpp"

def create_parser(lang: Language) -> Parser:
    # Use the environment's working constructor (user wants Parser(lang))
    return Parser(lang)

def node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

def line_range(node: Node) -> tuple[int, int]:
    return node.start_point[0], node.end_point[0]
