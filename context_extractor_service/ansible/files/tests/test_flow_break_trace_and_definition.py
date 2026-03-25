import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_definition, trace_identifier_backward


def test_trace_identifier_backward_should_keep_template_literal_dependency_chain():
    source = """\
class UriService {
  changePort(newPort: string): void {
    const url = `${newPort}`;
    window.location.replace(url);
  }
}
"""

    chain = trace_identifier_backward(source, Path("uri.service.ts"), 4, "url")

    assert chain
    assert "newPort" in chain[0]["reads"]


def test_trace_identifier_backward_should_keep_normal_two_step_typescript_chain():
    source = """\
export function handleOAuthCodeInUrl(): boolean {
  const code = urlParams.get('code');
  const oauthUrl = `/auth/oauth?code=${encodeURIComponent(code)}&returnUrl=${encodeURIComponent(returnUrl)}`;
  window.location.href = oauthUrl;
  return true;
}
"""

    chain = trace_identifier_backward(source, Path("oauth-handler.ts"), 4, "oauthUrl")

    assert chain == [
        {
            "line": 3,
            "code": "const oauthUrl = `/auth/oauth?code=${encodeURIComponent(code)}&returnUrl=${encodeURIComponent(returnUrl)}`;",
            "writes": ["oauthUrl"],
            "reads": ["code", "encodeURIComponent", "returnUrl"],
        },
        {
            "line": 2,
            "code": "const code = urlParams.get('code');",
            "writes": ["code"],
            "reads": ["get", "urlParams"],
        },
    ]


def test_find_definition_should_keep_real_exported_typescript_symbol():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(
            "export default function OAuthDebugPage() {\n"
            "  return null;\n"
            "}\n",
        )

        defs = find_definition(root, "OAuthDebugPage")

    assert defs
    assert defs[0]["kind"] == "function"
    assert defs[0]["file"] == "page.tsx"


def test_find_definition_should_keep_real_python_function_symbol():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "views.py").write_text(
            "def login_view(request):\n"
            "    return True\n",
        )

        defs = find_definition(root, "login_view")

    assert defs
    assert defs[0]["kind"] == "function"
    assert defs[0]["file"] == "views.py"
