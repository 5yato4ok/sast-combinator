import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_capture_alert_call_on_typescript_line(monkeypatch):
    source = """\
function saveCalibration() {
  alert('Failed to save calibration. Please try again.');
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))

    result = mcp_server.find_identifiers("pipe", "AdvancedFOVDialog.tsx", 2)

    assert "alert" in result["reads"]


def test_find_identifiers_should_capture_simple_jsx_prop_expression(monkeypatch):
    source = """\
function DialogActions() {
  return <Box onClick={onClose} sx={{ width: '83px' }} />;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))

    result = mcp_server.find_identifiers("pipe", "AdvancedFOVDialog.tsx", 2)

    assert "onClose" in result["reads"]


def test_find_identifiers_should_capture_ternary_jsx_prop_expression(monkeypatch):
    source = """\
function DialogActions() {
  return <Box onClick={isCalibrated ? handleEdit : (pointPairs.length > 0 ? handleClearAll : undefined)} />;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))

    result = mcp_server.find_identifiers("pipe", "AdvancedFOVDialog.tsx", 2)

    assert "isCalibrated" in result["reads"]
    assert "handleEdit" in result["reads"]
    assert "pointPairs" in result["reads"]
    assert "handleClearAll" in result["reads"]


def test_find_identifiers_should_keep_normal_javascript_call_expression(monkeypatch):
    source = """\
function closeDialog() {
  onClose();
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "DialogActions.tsx"))

    result = mcp_server.find_identifiers("pipe", "DialogActions.tsx", 2)

    assert "onClose" in result["reads"]
