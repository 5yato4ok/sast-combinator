from pathlib import Path

import mcp_server
from conftest import _stub_read_source


def _stub_resolve_source_dir():
    def _resolver(_pipeline_id: str) -> Path:
        return Path("/tmp")

    return _resolver


def test_real_finding_mutations_post_call_should_keep_http_call_identifiers(monkeypatch):
    source = """\
const updatePriceSet = async (
    updateServiceUrl: string,
    services: Record<string, { price: number | null }>,
    entityType: 'channel_partners' | 'organization'
) => {
    let somePriceSet = false;
    const data = Object.entries(services);
    if (data.length > 0) {
        await axios.post(updateServiceUrl, data);
    }
    return somePriceSet;
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts")
    extracted = mcp_server.extract_function("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts", 9)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts", 9)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        await axios.post(updateServiceUrl, data);"
    assert identifiers["reads"] == ["axios", "data", "post", "updateServiceUrl"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "typescript"


def test_real_finding_kmz_debug_line_should_keep_logger_and_template_reads(monkeypatch):
    source = """\
async function extractIcons(zipFile: JSZip): Promise<Record<string, string>> {
  const icons: Record<string, string> = {};

  for (const filename of imageFiles) {
    try {
      const fileData = await zipFile.files[filename].async('base64');
      logger.debug(`[KMZ] Extracted icon: ${filename} (${fileData.length} chars)`);
    } catch (error) {
      logger.warn(`[KMZ] Failed to extract icon ${filename}:`, error);
    }
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "kmz-parser.ts"))

    extracted = mcp_server.extract_function("07734951", "src/lib/map/kmz-parser.ts", 7)
    identifiers = mcp_server.find_identifiers("07734951", "src/lib/map/kmz-parser.ts", 7)

    assert extracted["meta"]["code_on_line"] == "      logger.debug(`[KMZ] Extracted icon: ${filename} (${fileData.length} chars)`);"
    assert identifiers["reads"] == ["debug", "fileData", "filename", "length", "logger"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "typescript"


def test_real_finding_kmz_object_keys_line_should_keep_object_and_icons_reads(monkeypatch):
    source = """\
async function extractIcons(zipFile: JSZip): Promise<Record<string, string>> {
  const icons: Record<string, string> = {};
  logger.debug(`[KMZ] Total extracted icons:`, Object.keys(icons));
  return icons;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "kmz-parser.ts"))

    extracted = mcp_server.extract_function("07734951", "src/lib/map/kmz-parser.ts", 3)
    identifiers = mcp_server.find_identifiers("07734951", "src/lib/map/kmz-parser.ts", 3)

    assert extracted["meta"]["code_on_line"] == "  logger.debug(`[KMZ] Total extracted icons:`, Object.keys(icons));"
    assert identifiers["reads"] == ["Object", "debug", "icons", "keys", "logger"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "typescript"


def test_real_finding_cpp_new_expression_should_keep_constructor_and_this_reads(monkeypatch):
    source = """\
VirtualCameraActionHandler::VirtualCameraActionHandler(
    WindowContext* windowContext,
    QObject* parent)
    :
    base_type(parent),
    WindowContextAware(windowContext)
{
    using namespace menu;

    new QnVirtualCameraSessionDelegate(this);
}
"""
    monkeypatch.setattr(
        mcp_server,
        "_read_source",
        _stub_read_source(source, "virtual_camera_action_handler.cpp"),
    )

    extracted = mcp_server.extract_function(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.cpp",
        10,
    )
    identifiers = mcp_server.find_identifiers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.cpp",
        10,
    )

    assert extracted["meta"]["code_on_line"] == "    new QnVirtualCameraSessionDelegate(this);"
    assert identifiers["reads"] == ["this"]  # QnVirtualCameraSessionDelegate is a type
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"


def test_real_finding_cpp_instance_call_should_keep_workbench_context_read(monkeypatch):
    source = """\
ConnectActionsHandler::ConnectActionsHandler(WindowContext* windowContext, QObject* parent):
    base_type(parent),
    WindowContextAware(windowContext)
{
    // The only instance of UserAuthDebugInfoWatcher is created to be owned by the context.
    workbenchContext()->instance<UserAuthDebugInfoWatcher>();
}
"""
    monkeypatch.setattr(
        mcp_server,
        "_read_source",
        _stub_read_source(source, "connect_actions_handler.cpp"),
    )

    extracted = mcp_server.extract_function(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        6,
    )
    identifiers = mcp_server.find_identifiers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        6,
    )

    assert extracted["meta"]["code_on_line"] == "    workbenchContext()->instance<UserAuthDebugInfoWatcher>();"
    assert identifiers["reads"] == ["instance", "workbenchContext"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
