import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.extract import extract_function_from_source
from context_extractor.project_analysis import trace_identifier_backward


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_extract_function_should_keep_python_function_signature_line():
    source = """\
def change_view(self, request, object_id, form_url='', extra_context=None):
    return True
"""

    result = extract_function_from_source(source, "admin.py", 1, 200)

    assert result["meta"]["code_on_line"] == (
        "def change_view(self, request, object_id, form_url='', extra_context=None):"
    )


def test_extract_function_should_keep_python_with_open_line_context():
    source = """\
def load_template(scss_file):
    with open(scss_file) as f:
        return f.read()
"""

    result = extract_function_from_source(source, "extract_brand_core_values.py", 2, 200)

    assert result["meta"]["code_on_line"] == "    with open(scss_file) as f:"


def test_find_identifiers_should_keep_normal_python_assignment_shape(monkeypatch):
    source = """\
def build_url(return_url):
    oauth_url = create_oauth_url(return_url)
    return oauth_url
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "oauth_handler.py"))

    result = mcp_server.find_identifiers("pipe", "oauth_handler.py", 2)

    assert result["writes"] == ["oauth_url"]
    assert "create_oauth_url" in result["reads"]
    assert "return_url" in result["reads"]


def test_trace_identifier_backward_should_keep_normal_python_assignment_chain():
    source = """\
def build_url(return_url):
    oauth_url = create_oauth_url(return_url)
    return oauth_url
"""

    chain = trace_identifier_backward(source, Path("oauth_handler.py"), 3, "oauth_url")

    assert chain == [
        {
            "line": 2,
            "code": "oauth_url = create_oauth_url(return_url)",
            "writes": ["oauth_url"],
            "reads": ["create_oauth_url", "return_url"],
        }
    ]
