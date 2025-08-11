from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
import tree_sitter_java as java_lang

# Load compiled languages once
CPP_LANGUAGE = Language(cpp_lang.language())
PY_LANGUAGE = Language(py_lang.language())
JS_LANGUAGE = Language(js_lang.language())
JAVA_LANGUAGE = Language(java_lang.language())

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
    return lang, "cpp"

def create_parser(lang: Language) -> Parser:
    # Use the environment's working constructor (user wants Parser(lang))
    return Parser(lang)

def node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

def line_range(node: Node) -> tuple[int, int]:
    return node.start_point[0], node.end_point[0]
