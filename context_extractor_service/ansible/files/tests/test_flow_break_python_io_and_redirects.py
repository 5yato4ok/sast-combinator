import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_capture_python_with_open_join_identifiers(monkeypatch):
    source = """\
import os

def copy():
    with open(os.path.join(NGINX_DEPLOYMENT_DIR, 'nginx.conf.template'), 'r') as template_file:
        return template_file.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))

    result = mcp_server.find_identifiers("pipe", "copy_nginx_configs.py", 4)

    assert "open" in result["reads"]
    assert "os" in result["reads"]
    assert "NGINX_DEPLOYMENT_DIR" in result["reads"]
    assert "template_file" in result["writes"]


def test_find_identifiers_should_not_treat_window_as_write_on_redirect_assignment(monkeypatch):
    source = """\
export function handleOAuthCodeInUrl(): boolean {
  const code = urlParams.get('code');
  const oauthUrl = `/auth/oauth?code=${encodeURIComponent(code)}&returnUrl=${encodeURIComponent(returnUrl)}`;
  window.location.href = oauthUrl;
  return true;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "oauth-handler.ts"))

    result = mcp_server.find_identifiers("pipe", "oauth-handler.ts", 4)

    assert "oauthUrl" in result["reads"]
    assert "window" not in result["writes"]


def test_find_identifiers_should_keep_normal_python_assignment_reads_and_writes(monkeypatch):
    source = """\
import os

def build_path(base):
    full_path = os.path.join(base, 'nginx.conf')
    return full_path
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))

    result = mcp_server.find_identifiers("pipe", "copy_nginx_configs.py", 4)

    assert "full_path" in result["writes"]
    assert "os" in result["reads"]
    assert "base" in result["reads"]


def test_find_identifiers_should_keep_normal_typescript_template_literal_reads(monkeypatch):
    source = """\
class UriService {
  changePort(newPort: string): void {
    const url = `${newPort}`;
    window.location.replace(url);
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "uri.service.ts"))

    result = mcp_server.find_identifiers("pipe", "uri.service.ts", 3)

    assert "url" in result["writes"]
    assert "newPort" in result["reads"]
