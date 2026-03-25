import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.extract import extract_function_from_source


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_extract_function_should_not_collapse_cpp_body_line_to_opening_brace():
    source = """\
void ItemGrabber::grabToImage(QQuickItem* item, const QJSValue& callback)
{
    new ItemGrabberWorker(item, callback);
}
"""

    result = extract_function_from_source(source, "item_grabber.cpp", 2, 200)

    assert result["meta"]["code_on_line"] == "{"


def test_find_identifiers_should_capture_cpp_static_helper_signature_and_call_identifiers(monkeypatch):
    source = """\
template<class Get, class Set>
static void backup(Object* object, Get get, Set set, const char* backupId)
{
    new QnTypedPropertyBackup(object, get, set, backupId);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "property_backup.h"))

    signature_result = mcp_server.find_identifiers("pipe", "property_backup.h", 2)
    body_result = mcp_server.find_identifiers("pipe", "property_backup.h", 4)

    assert "backup" in signature_result["writes"]
    assert "object" in signature_result["writes"]
    assert "get" in signature_result["writes"]
    assert "set" in signature_result["writes"]
    assert "backupId" in signature_result["writes"]
    assert "QnTypedPropertyBackup" in body_result["reads"]
    assert "object" in body_result["reads"]
    assert "get" in body_result["reads"]
    assert "set" in body_result["reads"]
    assert "backupId" in body_result["reads"]


def test_extract_function_should_keep_normal_cpp_statement_line():
    source = """\
void ItemGrabber::grabToImage(QQuickItem* item, const QJSValue& callback)
{
    int count = 1;
    new ItemGrabberWorker(item, callback);
}
"""

    result = extract_function_from_source(source, "item_grabber.cpp", 3, 200)

    assert result["meta"]["code_on_line"] == "    int count = 1;"


def test_find_identifiers_should_keep_normal_cpp_call_expression_reads(monkeypatch):
    source = """\
void run(Object* object, Get get, Set set, const char* backupId)
{
    consume(object, get, set, backupId);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "property_backup.cpp"))

    result = mcp_server.find_identifiers("pipe", "property_backup.cpp", 3)

    assert "consume" in result["reads"]
    assert "object" in result["reads"]
    assert "get" in result["reads"]
    assert "set" in result["reads"]
    assert "backupId" in result["reads"]
