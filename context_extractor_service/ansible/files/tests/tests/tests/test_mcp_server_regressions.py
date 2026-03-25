import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.project_analysis import find_route_to_function, trace_identifier_backward


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_support_tsx_files(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
    const nextUrl = "/oauth/callback";

    return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "src/app/debug/oauth/page.tsx", 4)

    assert "nextUrl" in result["reads"]


def test_find_identifiers_should_capture_go_assignment_reads_and_writes(monkeypatch):
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


def test_find_identifiers_should_capture_typescript_template_literal_inputs(monkeypatch):
    source = """\
class UriService {
    changePort(newPort: string): void {
        window.location.replace(
            `${window.location.protocol}//${window.location.hostname}:${newPort}/${window.location.hash}`,
        );
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "uri.service.ts"))

    result = mcp_server.find_identifiers("pipe", "uri.service.ts", 3)

    assert "window" in result["reads"]
    assert "newPort" in result["reads"]


def test_find_identifiers_should_capture_typescript_declaration_reads_and_writes(monkeypatch):
    source = "const channel = new BroadcastChannel(COOKIE_POLICY_CHANNEL)\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.ts"))

    result = mcp_server.find_identifiers("pipe", "sample.ts", 1)

    assert "channel" in result["writes"]
    assert "BroadcastChannel" in result["reads"]
    assert "COOKIE_POLICY_CHANNEL" in result["reads"]


def test_find_identifiers_should_capture_javascript_template_literal_identifiers(monkeypatch):
    source = 'const stateLabel = `<a href="${reviewUrl}">${state}</a>`;\n'
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 1)

    assert "stateLabel" in result["writes"]
    assert "reviewUrl" in result["reads"]
    assert "state" in result["reads"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live audit on nx-connect-ui Alert.tsx: find_identifiers drops bindings "
        "from TypeScript/TSX function parameter destructuring lines."
    ),
)
def test_find_identifiers_should_capture_destructured_tsx_function_parameters(monkeypatch):
    source = """\
export default function Alert({ type, ...props }: AlertProps) {
    return props.children;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Alert.tsx"))

    result = mcp_server.find_identifiers("pipe", "Alert.tsx", 1)

    assert "Alert" in result["writes"]
    assert "type" in result["writes"]
    assert "props" in result["writes"]


def test_trace_identifier_backward_should_keep_template_literal_reads():
    source = """\
class UriService {
    changePort(newPort: string): void {
        const url = `${newPort}`
        window.location.replace(url)
    }
}
"""
    chain = trace_identifier_backward(source, Path("uri.service.ts"), 4, "url")

    assert chain
    assert "newPort" in chain[0]["reads"]

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed repeatedly in live nx-maps-ui findings: find_identifiers returns empty "
        "reads/writes on lines inside multiline destructured TypeScript parameter lists."
    ),
)
def test_find_identifiers_should_capture_bindings_inside_multiline_destructured_signature(monkeypatch):
    source = """\
const MapSearch = ({
  systems,
  getLoadedDevices,
  mapCenter,
  deviceCount = 0,
}) => {
  return systems.length
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "MapSearch.tsx"))

    result = mcp_server.find_identifiers("pipe", "MapSearch.tsx", 2)

    assert "systems" in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx-connect-ui findings: find_identifiers loses JSX expression reads "
        "on dangerouslySetInnerHTML lines."
    ),
)
def test_find_identifiers_should_capture_jsx_expression_identifiers(monkeypatch):
    source = """\
function GlobalSearchBar() {
  return <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "GlobalSearchBar.tsx"))

    result = mcp_server.find_identifiers("pipe", "GlobalSearchBar.tsx", 2)

    assert "styles" in result["reads"]
    assert "getCommandKeySymbol" in result["reads"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: find_identifiers returns empty reads/writes for C++ "
        "member initializer lines with constructor calls."
    ),
)
def test_find_identifiers_should_capture_cpp_member_initializer_identifiers(monkeypatch):
    source = """\
struct P {
    LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "live_preview.cpp"))

    result = mcp_server.find_identifiers("pipe", "live_preview.cpp", 2)

    assert "thumbnailSource" in result["writes"]
    assert "LivePreviewThumbnail" in result["reads"]
    assert "q" in result["reads"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: find_identifiers returns empty reads/writes "
        "for Python with-open statements."
    ),
)
def test_find_identifiers_should_capture_python_with_open_identifiers(monkeypatch):
    source = """\
def f(scss_file):
    with open(scss_file) as f:
        return f.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "extract_brand_core_values.py"))

    result = mcp_server.find_identifiers("pipe", "extract_brand_core_values.py", 2)

    assert "open" in result["reads"]
    assert "scss_file" in result["reads"]
    assert "f" in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: find_identifiers returns empty reads/writes "
        "for Python function signature lines."
    ),
)
def test_find_identifiers_should_capture_python_function_signature_parameters(monkeypatch):
    source = """\
def change_view(self, request, object_id, form_url='', extra_context=None):
    return True
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "admin.py"))

    result = mcp_server.find_identifiers("pipe", "admin.py", 1)

    assert "change_view" in result["writes"]
    assert "self" in result["writes"]
    assert "request" in result["writes"]
    assert "object_id" in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: find_identifiers returns empty reads/writes for C++ "
        "static helper signatures and constructor-call bodies."
    ),
)
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

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: find_identifiers returns empty reads/writes "
        "for Python with-open statements that wrap os.path.join path construction."
    ),
)
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

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: find_identifiers returns empty reads/writes "
        "for Python with-open statements in binary write mode."
    ),
)
def test_find_identifiers_should_capture_python_with_open_write_identifiers(monkeypatch):
    source = """\
def save(file_name, data):
    with open(file_name, 'wb') as f:
        f.write(data)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "filldata.py"))

    result = mcp_server.find_identifiers("pipe", "filldata.py", 2)

    assert "open" in result["reads"]
    assert "file_name" in result["reads"]
    assert "f" in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: find_identifiers returns empty reads/writes "
        "for Python with-open statements that combine os.path.join with write mode."
    ),
)
def test_find_identifiers_should_capture_python_with_open_join_write_identifiers(monkeypatch):
    source = """\
import os

def write_out(base):
    with open(os.path.join(base, 'nginx.test.conf'), 'w') as outfile:
        outfile.write('x')
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))

    result = mcp_server.find_identifiers("pipe", "copy_nginx_configs.py", 4)

    assert "open" in result["reads"]
    assert "os" in result["reads"]
    assert "base" in result["reads"]
    assert "outfile" in result["writes"]



@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in flow-aware live audit on nx C++ findings: trace_identifier_backward "
        "returns a self-referential chain for constructor-style allocations instead of "
        "tracking constructor inputs like this."
    ),
)
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in flow-aware live audit on cloud_portal and chatmodes modules: "
        "find_route_to_function returns vendor/minified app.use(...) hits for unrelated "
        "generic symbol names, which sends the triage flow into tinymce assets."
    ),
)
def test_find_route_to_function_should_ignore_vendor_use_calls_for_generic_symbol_names():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.js").write_text("async function main() { return true; }\n")
        (root / "vendor.js").write_text("app.use('/admin', middleware),main=1;\n")

        result = find_route_to_function(root, "main")

    assert result == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx-connect-ui mutations.ts findings: find_identifiers on typed arrow "
        "parameter lines misses parameter bindings and only returns a partial read set."
    ),
)
def test_find_identifiers_should_capture_typed_arrow_parameter_bindings(monkeypatch):
    source = """\
export const buildMutation = async (
  updateServiceUrl: string,
  services: Record<string, { price: number | null }>,
  entityType: 'channel_partners' | 'organization'
) => {
  const includeTier = entityType === 'channel_partners';
  return includeTier;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))

    result = mcp_server.find_identifiers("pipe", "mutations.ts", 3)

    assert "updateServiceUrl" in result["writes"]
    assert "services" in result["writes"]
    assert "entityType" in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live oauth redirect findings: find_identifiers marks 'window' as a write "
        "on browser redirect assignments instead of treating the sink variables as reads."
    ),
)
def test_find_identifiers_should_not_treat_window_as_write_on_redirect_assignment(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const buildOauthUrl = () => '/oauth';
  return () => {
    window.location.href = buildOauthUrl();
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 4)

    assert "buildOauthUrl" in result["reads"]
    assert "window" not in result["writes"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed on JSX callback lines like map/page.tsx: find_identifiers returns empty "
        "reads/writes even though router.push is clearly referenced inside the callback."
    ),
)
def test_find_identifiers_should_capture_inline_jsx_callback_reads(monkeypatch):
    source = """\
function Page() {
  return <Button onClick={() => {
    router.push('/x')
  }}>Go</Button>
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 2)

    assert "router" in result["reads"]
    assert "push" in result["reads"]
