from pathlib import Path
from urllib.parse import urlparse
import requests
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
import tree_sitter_java as java_lang
from tree_sitter import Language, Parser

CPP_LANGUAGE = Language(cpp_lang.language())
PY_LANGUAGE = Language(py_lang.language())
JS_LANGUAGE = Language(js_lang.language())
JAVA_LANGUAGE = Language(java_lang.language())

# Supported file extensions mapped to tree-sitter language names
SUPPORTED_LANGUAGES = {
    '.py': PY_LANGUAGE,
    '.h': CPP_LANGUAGE,
    '.hpp': CPP_LANGUAGE,
    '.cpp': CPP_LANGUAGE,
    '.c': CPP_LANGUAGE,
    '.cc': CPP_LANGUAGE,
    '.cxx': CPP_LANGUAGE,
    '.js': JS_LANGUAGE,
    '.java': JAVA_LANGUAGE
}

def _detect_language_name(filepath: Path):
    ext = filepath.suffix
    if ext not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported file extension: {ext}")
    return SUPPORTED_LANGUAGES[ext]

def extract_function_from_source(source_code: str, filename: str, line_number: int) -> str | None:
    lang = _detect_language_name(Path(filename))
    parser = Parser(lang)

    tree = parser.parse(source_code.encode("utf-8"))

    def find_enclosing_function(node):
        # Check if the node is a function or method definition and contains the given line
        if node.type in (
            'method_declaration',                           # Java
            'function_definition', 'function_declaration',  # C/C++
            'function', 'method_definition',                # JS/TS
            'function_definition', 'decorated_definition'   # Python
        ):
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            if start_line <= line_number <= end_line:
                return source_code[node.start_byte:node.end_byte]

        # Recursively search in child nodes
        for child in node.children:
            result = find_enclosing_function(child)
            if result:
                return result
        return None

    return find_enclosing_function(tree.root_node)

def extract_function(file_url: str, line_number: int) -> str | None:
    response = requests.get(file_url)
    response.raise_for_status()
    source_code = response.text
    filename = Path(urlparse(file_url).path).name
    return extract_function_from_source(source_code, filename, line_number)
