from pathlib import Path
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
from tree_sitter import Language, Parser

CPP_LANGUAGE = Language(cpp_lang.language())
PY_LANGUAGE = Language(py_lang.language())
JS_LANGUAGE = Language(js_lang.language())

# Supported file extensions mapped to tree-sitter language names
SUPPORTED_LANGUAGES = {
    '.py': PY_LANGUAGE,
    '.h': CPP_LANGUAGE,
    '.hpp': CPP_LANGUAGE,
    '.cpp': CPP_LANGUAGE,
    '.cc': CPP_LANGUAGE,
    '.cxx': CPP_LANGUAGE,
    '.js': JS_LANGUAGE,
}


def _detect_language_name(filepath: Path):
    """
    Detect the tree-sitter language name from the file extension.
    """
    ext = filepath.suffix
    if ext not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported file extension: {ext}")
    return SUPPORTED_LANGUAGES[ext]



def extract_function(filename: str, line_number: int) -> str | None:
    """
    Return the full source code of the function that contains the given line number.

    :param filename: Path or name of the file (used to detect language)
    :param line_number: Line number (1-based) to locate the enclosing function
    :return: Function body as string or None if not found
    """

    source_path = Path(filename)
    source_code = source_path.read_text()
    lang = _detect_language_name(source_path)
    parser = Parser(lang)

    tree = parser.parse(source_code.encode("utf-8"))

    def find_enclosing_function(node):
        # Check if the node is a function or method definition and contains the given line
        if node.type in (
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


# Example usage:
if __name__ == "__main__":
    source_path = "example.cpp"
    line = 39

    function_body = extract_function(source_path, line)
    if function_body:
        print(function_body)
    else:
        print("No function found at the given line.")
