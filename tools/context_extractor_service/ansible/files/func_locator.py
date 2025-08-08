from pathlib import Path
from urllib.parse import urlparse
import requests
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
import tree_sitter_java as java_lang
from tree_sitter import Language, Parser

# Load the compiled tree-sitter languages
CPP_LANGUAGE = Language(cpp_lang.language())
PY_LANGUAGE = Language(py_lang.language())
JS_LANGUAGE = Language(js_lang.language())
JAVA_LANGUAGE = Language(java_lang.language())

# Mapping file extensions to language objects
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
    """Detect tree-sitter language based on file extension."""
    ext = filepath.suffix
    if ext not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported file extension: {ext}")
    return SUPPORTED_LANGUAGES[ext]

def extract_function_from_source(source_code: str, filename: str, line_number: int) -> str | None:
    """Find and return the full function definition surrounding the given line number."""
    lang = _detect_language_name(Path(filename))
    parser = Parser(lang)
    tree = parser.parse(source_code.encode("utf-8"))

    def find_enclosing_function(node):
        # Check if the node is a function or method definition and contains the given line
        if node.type in (
            'method_declaration',                           # Java
            'function_definition', 'function_declaration',  # C/C++
            'function', 'method_definition',                # JS/TS
            'decorated_definition',                         # Python
        ):
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            if start_line <= line_number <= end_line:
                return source_code[node.start_byte:node.end_byte]

        for child in node.children:
            result = find_enclosing_function(child)
            if result:
                return result
        return None

    return find_enclosing_function(tree.root_node)

def extract_function(file_url: str, line_number: int) -> str | None:
    """Download the file and extract the function containing the given line number."""
    response = requests.get(file_url)
    response.raise_for_status()
    source_code = response.text
    filename = Path(urlparse(file_url).path).name
    return extract_function_from_source(source_code, filename, line_number)

def compress_function(source_code: str, filename: str, line_number: int) -> str:
    """
    Compress a function by keeping only the function signature, and lines related
    to the identifiers in the target line. All unrelated code blocks are replaced
    with summary comments.
    """
    lang = _detect_language_name(Path(filename))
    parser = Parser(lang)
    tree = parser.parse(source_code.encode("utf-8"))
    lines = source_code.splitlines()

    def find_function_node(node):
        if node.type in (
            'method_declaration',
            'function_definition', 'function_declaration',
            'function', 'method_definition',
            'decorated_definition',
        ):
            if node.start_point[0] + 1 <= line_number <= node.end_point[0] + 1:
                return node
        for child in node.children:
            res = find_function_node(child)
            if res:
                return res
        return None

    def find_target_node(node):
        if node.start_point[0] <= line_number - 1 <= node.end_point[0]:
            for child in node.children:
                result = find_target_node(child)
                if result:
                    return result
            return node
        return None

    def collect_identifiers(node):
        identifiers = set()
        def visit(n):
            if n.type == 'identifier':
                identifiers.add(n.text.decode())
            for c in n.children:
                visit(c)
        visit(node)
        return identifiers

    func_node = find_function_node(tree.root_node)
    if not func_node:
        return "// Function not found"

    target_node = find_target_node(func_node)
    if not target_node:
        return "// Target line not found in function"

    identifiers = collect_identifiers(target_node)
    relevant_lines = set()

    # Mark lines containing important identifiers
    for i in range(func_node.start_point[0], func_node.end_point[0] + 1):
        if any(identifier in lines[i] for identifier in identifiers):
            relevant_lines.add(i)

    # Always include the function header and footer
    output = [lines[func_node.start_point[0]]]

    skipped = False
    for i in range(func_node.start_point[0] + 1, func_node.end_point[0]):
        if i in relevant_lines:
            if skipped:
                output.append("    // [omitted logic]")
                skipped = False
            output.append(lines[i])
        else:
            skipped = True
    if skipped:
        output.append("    // [omitted logic]")

    output.append(lines[func_node.end_point[0]])
    return "\n".join(output)
