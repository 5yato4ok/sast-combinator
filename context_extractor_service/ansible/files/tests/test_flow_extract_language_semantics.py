import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


def test_extract_function_should_keep_go_assignment_line():
    source = """\
package fetcher

func f(data []byte) {
    hash := md5.Sum(data)
    _ = hash
}
"""

    result = extract_function_from_source(source, "site_info_reader.go", 4, 200)

    assert result["meta"]["code_on_line"] == "    hash := md5.Sum(data)"


def test_extract_function_should_keep_cpp_call_expression_line():
    source = """\
void run(Object* object, Get get, Set set, const char* backupId)
{
    consume(object, get, set, backupId);
}
"""

    result = extract_function_from_source(source, "property_backup.cpp", 3, 200)

    assert result["meta"]["code_on_line"] == "    consume(object, get, set, backupId);"


def test_extract_function_should_keep_javascript_assignment_line():
    source = """\
function fetch(url) {
  const protocol = url.startsWith('https') ? https : require('http');
  return protocol;
}
"""

    result = extract_function_from_source(source, "generate-customization.js", 2, 200)

    assert result["meta"]["code_on_line"] == (
        "  const protocol = url.startsWith('https') ? https : require('http');"
    )


def test_extract_function_should_keep_typescript_template_literal_line():
    source = """\
class UriService {
  changePort(newPort: string): void {
    const url = `${newPort}`;
    window.location.replace(url);
  }
}
"""

    result = extract_function_from_source(source, "uri.service.ts", 3, 200)

    assert result["meta"]["code_on_line"] == "    const url = `${newPort}`;"
