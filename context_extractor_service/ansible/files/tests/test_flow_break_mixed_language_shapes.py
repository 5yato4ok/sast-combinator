from pathlib import Path

import pytest

import mcp_server
from conftest import _stub_read_source
from context_extractor.project_analysis import trace_identifier_backward


def test_find_identifiers_should_capture_html_template_literal_identifiers(monkeypatch):
    source = 'const stateLabel = `<a href="${reviewUrl}">${state}</a>`;\n'
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 1)

    assert "stateLabel" in result["writes"]
    assert "reviewUrl" in result["reads"]
    assert "state" in result["reads"]


def test_find_identifiers_should_keep_go_assignment_reads_and_writes(monkeypatch):
    source = """\
func f(data []byte) {
    hash := md5.Sum(data)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "site_info_reader.go"))

    result = mcp_server.find_identifiers("pipe", "site_info_reader.go", 2)

    assert "hash" in result["writes"]
    assert "md5" in result["reads"]
    assert "data" in result["reads"]


def test_trace_identifier_backward_should_keep_go_assignment_chain():
    source = """\
package fetcher

func f(data []byte) {
    hash := md5.Sum(data)
    _ = hash
}
"""
    chain = trace_identifier_backward(source, Path("site_info_reader.go"), 5, "hash")

    assert chain
    assert chain[0]["writes"] == ["hash"]
    assert "md5" in chain[0]["reads"]
    assert "data" in chain[0]["reads"]


def test_find_identifiers_should_keep_javascript_assignment_reads_and_writes(monkeypatch):
    source = """\
function fetch(url) {
  const protocol = url.startsWith('https') ? https : require('http');
  return protocol;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))

    result = mcp_server.find_identifiers("pipe", "generate-customization.js", 2)

    assert result["writes"] == ["protocol"]
    assert "url" in result["reads"]
    assert "https" in result["reads"]
    assert "require" in result["reads"]
