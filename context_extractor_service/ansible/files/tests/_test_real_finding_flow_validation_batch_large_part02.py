# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.parametrize(
    ("pipeline_id", "file_path", "line_number", "file_name", "source", "code_on_line", "reads", "writes", "language"),
    [
        (
            "07734951",
            "src/lib/auth/oauth-handler.ts",
            3,
            "oauth-handler.ts",
            """\
function handleOAuthCodeInUrl(): boolean {
  const oauthUrl = `/auth/oauth?code=encoded`;
  window.location.href = oauthUrl;
  return true;
}
""",
            "  window.location.href = oauthUrl;",
            ["location", "oauthUrl", "window"],
            ["href"],
            "typescript",
        ),
        (
            "07734951",
            "src/lib/logging/logger.ts",
            4,
            "logger.ts",
            """\
private write(level: keyof typeof LogLevel, ...args: unknown[]): void {
  let prefix = this.prefix;
  if (level === LogLevel.ERROR) {
    console.error(prefix, ...args);
  } else {
    console.log(prefix, ...args);
  }
}
""",
            "    console.error(prefix, ...args);",
            ["args", "console", "error", "prefix"],
            [],
            "typescript",
        ),
        (
            "07734951",
            "src/lib/logging/logger.ts",
            6,
            "logger.ts",
            """\
private write(level: keyof typeof LogLevel, ...args: unknown[]): void {
  let prefix = this.prefix;
  if (level === LogLevel.ERROR) {
    console.error(prefix, ...args);
  } else {
    console.log(prefix, ...args);
  }
}
""",
            "    console.log(prefix, ...args);",
            ["args", "console", "log", "prefix"],
            [],
            "typescript",
        ),
        (
            "07734951",
            "scripts/parse-timezone-data.js",
            4,
            "parse-timezone-data.js",
            """\
function parseCoordinates(coordString) {
  const match = coordString.match(/^([+-])(\\d{2})(\\d{2})$/);
  if (!match) {
    console.error('Failed to parse:', coordString);
    return null;
  }
}
""",
            "    console.error('Failed to parse:', coordString);",
            ["console", "coordString", "error"],
            [],
            "javascript",
        ),
        (
            "07734951",
            "src/components/dashboard/layout/create-map-popover.tsx",
            3,
            "create-map-popover.tsx",
            """\
const generateUUID = (): string => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};
""",
            "    const r = Math.random() * 16 | 0;",
            ["Math", "random"],
            ["r"],
            "typescript",
        ),
        (
            "5a36b942",
            ".github/chatmodes/modules/context-extractor.js",
            5,
            "context-extractor.js",
            """\
async function main() {
  const filesInput = args[1];
  let files;
  if (filesInput && filesInput.endsWith('.json')) {
    files = JSON.parse(fs.readFileSync(filesInput, 'utf8'));
  }
}
""",
            "    files = JSON.parse(fs.readFileSync(filesInput, 'utf8'));",
            ["JSON", "filesInput", "fs", "parse", "readFileSync"],
            ["files"],
            "javascript",
        ),
        (
            "5a36b942",
            ".github/chatmodes/modules/context-extractor.js",
            5,
            "context-extractor.js",
            """\
async function main() {
  const metaDataInput = args[1];
  let metaData;
  if (metaDataInput && metaDataInput.endsWith('.json')) {
    metaData = JSON.parse(fs.readFileSync(metaDataInput, 'utf8'));
  }
}
""",
            "    metaData = JSON.parse(fs.readFileSync(metaDataInput, 'utf8'));",
            ["JSON", "fs", "metaDataInput", "parse", "readFileSync"],
            ["metaData"],
            "javascript",
        ),
        (
            "5a36b942",
            ".github/chatmodes/modules/template-engine.js",
            4,
            "template-engine.js",
            """\
async getTemplateContent(templateName) {
  const templatePath = path.join(process.cwd(), '.gitlab/merge_request_templates', templateName);
  try {
    return fs.readFileSync(templatePath, 'utf8');
  } catch (error) {
    throw new Error(`Failed to read template ${templateName}: ${error.message}`);
  }
}
""",
            "    return fs.readFileSync(templatePath, 'utf8');",
            ["fs", "readFileSync", "templatePath"],
            [],
            "javascript",
        ),
        (
            "5a36b942",
            ".github/chatmodes/modules/template-engine.js",
            5,
            "template-engine.js",
            """\
async function main() {
  const contextInput = args[1];
  let context;
  if (contextInput.endsWith('.json')) {
    context = JSON.parse(fs.readFileSync(contextInput, 'utf8'));
  } else {
    context = JSON.parse(contextInput);
  }
}
""",
            "    context = JSON.parse(fs.readFileSync(contextInput, 'utf8'));",
            ["JSON", "contextInput", "fs", "parse", "readFileSync"],
            ["context"],
            "javascript",
        ),
        (
            "5a36b942",
            ".github/chatmodes/modules/template-engine.js",
            5,
            "template-engine.js",
            """\
async function main() {
  const scoresInput = args[1];
  let scores;
  if (scoresInput.endsWith('.json')) {
    scores = JSON.parse(fs.readFileSync(scoresInput, 'utf8'));
  } else {
    scores = JSON.parse(scoresInput);
  }
}
""",
            "    scores = JSON.parse(fs.readFileSync(scoresInput, 'utf8'));",
            ["JSON", "fs", "parse", "readFileSync", "scoresInput"],
            ["scores"],
            "javascript",
        ),
        (
            "9ce90895",
            "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_shm_utils.cpp",
            5,
            "nxai_shm_utils.cpp",
            """\
char* nxai_shm_key_to_string(nxai_shm_t shm)
{
    // Windows implementation
    // Copy string so it can be freed
    char* shm_key_string = (char*) malloc(strlen(shm.key));
    strcpy(shm_key_string, shm.key);
    return shm_key_string;
}
""",
            "    char* shm_key_string = (char*) malloc(strlen(shm.key));",
            ["key", "malloc", "shm", "strlen"],
            ["shm_key_string"],
            "cpp",
        ),
        (
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_administration/widgets/security_settings_widget.cpp",
            3,
            "security_settings_widget.cpp",
            """\
void SecuritySettingsWidget::openPixelationConfigurationDialog()
{
    auto dialog = new PixelationIntensityDialog(
        m_pixelationSettings.intensity,
        mainWindowWidget());
}
""",
            "    auto dialog = new PixelationIntensityDialog(",
            ["intensity", "m_pixelationSettings", "mainWindowWidget"],
            ["dialog"],
            "cpp",
        ),
        (
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/workbench/timeline/live_preview.cpp",
            1,
            "live_preview.cpp",
            """\
LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);
const QmlProperty<AbstractResourceThumbnail*> previewSource{q->widget(), "previewSource"};
""",
            "LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);",
            ["q"],
            ["thumbnailSource"],
            "cpp",
        ),
        (
            "5a36b942",
            "cloud/cms/static/js/menuChange.js",
            3,
            "menuChange.js",
            """\
queryParams.set('customization', this.value);

window.location.href = window.location.pathname + '?' + queryParams.toString();
""",
            "window.location.href = window.location.pathname + '?' + queryParams.toString();",
            ["location", "pathname", "queryParams", "toString", "window"],
            ["href"],
            "javascript",
        ),
        (
            "5a36b942",
            "front_end/libs/services/uri.service.ts",
            2,
            "uri.service.ts",
            """\
changePort(newPort: string): void {
    window.location.replace(
        `${window.location.protocol}//${window.location.hostname}:${newPort}/${window.location.hash}`,
    );
}
""",
            "    window.location.replace(",
            ["hash", "hostname", "location", "newPort", "protocol", "replace", "window"],
            [],
            "typescript",
        ),
    ],
)
def test_real_finding_batch_should_keep_expected_semantic_outputs(
    monkeypatch,
    pipeline_id,
    file_path,
    line_number,
    file_name,
    source,
    code_on_line,
    reads,
    writes,
    language,
):
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, file_name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, line_number)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == code_on_line
    assert identifiers["reads"] == reads
    assert identifiers["writes"] == writes
    assert identifiers["language"] == language


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real cloud_portal finding on git-operations.js:702. "
        "The finding line is the execSync assignment, but extract_function still returns "
        "the whole options object block in code_on_line instead of the exact finding line."
    ),
)
def test_real_finding_git_operations_execsync_should_keep_exact_assignment_line(monkeypatch):
    source = """\
async runCommand(command, options = {}) {
  try {
    const result = execSync(command, {
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      cwd: process.cwd(),
      timeout: timeout
    });
    return result.trim();
  } catch (error) {}
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "git-operations.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("5a36b942", ".github/chatmodes/modules/git-operations.js")
    extracted = mcp_server.extract_function("5a36b942", ".github/chatmodes/modules/git-operations.js", 4)
    identifiers = mcp_server.find_identifiers("5a36b942", ".github/chatmodes/modules/git-operations.js", 4)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    const result = execSync(command, {"
    assert identifiers["reads"] == ["command", "cwd", "encoding", "execSync", "maxBuffer", "process", "timeout"]
    assert identifiers["writes"] == ["result"]
    assert identifiers["language"] == "javascript"


