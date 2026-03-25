import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


def test_extract_function_should_not_expand_python_import_line_to_file_preamble():
    source = """\
import os
import json

def build_config():
    return {"ok": True}
"""

    result = extract_function_from_source(source, "settings.py", 1, 200)

    assert result["meta"]["code_on_line"] == "import os"


def test_extract_function_should_keep_exact_line_for_multiline_jsx_opening_tag():
    source = """\
export default function Alert() {
  return (
    <div
      className={styles.alert}
      role=\"status\"
    >
      Hello
    </div>
  );
}
"""

    result = extract_function_from_source(source, "Alert.tsx", 4, 200)

    assert result["meta"]["code_on_line"] == "      className={styles.alert}"


def test_extract_function_should_keep_exact_line_for_normal_python_return():
    source = """\
def build_config():
    return {"ok": True}
"""

    result = extract_function_from_source(source, "settings.py", 2, 200)

    assert result["meta"]["code_on_line"] == "    return {\"ok\": True}"


def test_extract_function_should_keep_exact_line_for_normal_jsx_return():
    source = """\
export default function OAuthDebugPage() {
  return <a href={nextUrl}>Continue</a>;
}
"""

    result = extract_function_from_source(source, "page.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == "  return <a href={nextUrl}>Continue</a>;"
