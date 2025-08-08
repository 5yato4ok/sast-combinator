from pathlib import Path
from urllib.parse import urlparse, unquote

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

def load_source_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == 'file':
        # Convert to local file path
        path = Path(unquote(parsed.path))
        return path.read_text(encoding='utf-8')
    else:
        # Use requests for http/https
        import requests
        response = requests.get(url)
        response.raise_for_status()
        return response.text

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

def compress_function_from_source(source_code: str, filename: str, line_number: int) -> str:
    lang = _detect_language_name(Path(filename))
    parser = Parser(lang)
    tree = parser.parse(source_code.encode("utf-8"))
    lines = source_code.splitlines()
    relevant_lines = set()

    def find_function_node(node):
        if node.type in (
            'function_definition', 'function_declaration',
            'method_definition', 'function', 'lambda_expression'
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
        ids = set()
        def visit(n):
            if n.type == 'identifier':
                ids.add(n.text.decode())
            for c in n.children:
                visit(c)
        visit(node)
        return ids

    def node_contains_identifier(node, identifiers):
        matched = set()
        def visit(n):
            if n.type == 'identifier':
                value = n.text.decode()
                if value in identifiers:
                    matched.add(value)
            for c in n.children:
                visit(c)
        visit(node)
        return matched

    def collect_lines_with_identifiers(node, identifiers):
        new_ids = set()
        def visit(n):
            if n.type in (
                'assignment_expression', 'declaration',
                'call_expression', 'if_statement', 'return_statement'
            ):
                matched = node_contains_identifier(n, identifiers)
                if matched:
                    for i in range(n.start_point[0], n.end_point[0] + 1):
                        relevant_lines.add(i)
                    new_ids.update(collect_identifiers(n))
            for c in n.children:
                visit(c)
        visit(node)
        return new_ids

    func_node = find_function_node(tree.root_node)
    if not func_node:
        return "// Function not found"

    target_node = find_target_node(func_node)
    if not target_node:
        return "// Target line not found in function"

    identifiers = collect_identifiers(target_node)
    for i in range(target_node.start_point[0], target_node.end_point[0] + 1):
        relevant_lines.add(i)

    # ONLY walk parent blocks that contain the target
    nodes_to_visit = []
    def collect_parent_blocks(node):
        while node is not None:
            if node.type in ('compound_statement', 'lambda_expression', 'function_definition'):
                nodes_to_visit.append(node)
            node = getattr(node, "parent", None)
    collect_parent_blocks(target_node)

    seen_ids = set()
    depth = 0
    MAX_DEPTH = 2
    while identifiers - seen_ids and depth < MAX_DEPTH:
        current = identifiers - seen_ids
        for node in nodes_to_visit:
            new_ids = collect_lines_with_identifiers(node, current)
            identifiers.update(new_ids)
        seen_ids.update(current)
        depth += 1

    # merge continuous relevant lines into blocks
    relevant_lines = sorted(relevant_lines)
    blocks = []
    if relevant_lines:
        start = prev = relevant_lines[0]
        for i in relevant_lines[1:]:
            if i == prev + 1:
                prev = i
            else:
                blocks.append((start, prev))
                start = prev = i
        blocks.append((start, prev))

    # build output
    output = [lines[func_node.start_point[0]]]  # function signature
    cursor = func_node.start_point[0] + 1

    # preserve standalone `{` if present
    if cursor < len(lines) and lines[cursor].strip() == '{':
        output.append(lines[cursor])
        cursor += 1

    for start, end in blocks:
        # only insert omitted marker if there was skipped non-empty content
        skipped_lines = lines[cursor:start]
        if any(line.strip() for line in skipped_lines):
            output.append("    // ...")

        output.extend(lines[i] for i in range(start, end + 1) if lines[i].strip() != "")
        cursor = end + 1

    # final omitted block (if needed)
    skipped_lines = lines[cursor:func_node.end_point[0]]
    if any(line.strip() for line in skipped_lines):
        output.append("    // ...")

    output.append(lines[func_node.end_point[0]])  # final }
    return "\n".join(output)

def extract_function(file_url: str, line_number: int) -> str | None:
    """Download the file and extract the function containing the given line number."""
    source_code = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return extract_function_from_source(source_code, filename, line_number)


def compress_function(file_url: str, line_number: int) -> str | None:
    """Download the file and compress the function to contain only important information, related to the given line number."""
    source_code = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return compress_function_from_source(source_code, filename, line_number)


if __name__ == "__main__":
    print (compress_function(
        "file:///Users/butkevichveronika/develop/nx_copy/open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/lookup_lists/lookup_list_action_handler.cpp",
        257))
