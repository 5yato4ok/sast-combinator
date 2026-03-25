import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import trace_identifier_backward


def test_trace_identifier_backward_should_not_self_reference_cpp_constructor_allocation():
    source = """\
void DragProcessingInstrument::initialize()
{
    DragProcessor *processor = new DragProcessor(this);
    processor->setHandler(this);
}
"""

    chain = trace_identifier_backward(source, Path("drag_processing_instrument.cpp"), 4, "processor")

    assert chain
    assert "processor" not in chain[0]["reads"]
    assert "this" in chain[0]["reads"]


def test_trace_identifier_backward_should_keep_normal_typescript_dependency_chain():
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
