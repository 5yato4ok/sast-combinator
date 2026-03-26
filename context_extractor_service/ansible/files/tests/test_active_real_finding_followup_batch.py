import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _write_source_tree(root: Path, file_path: str, source: str) -> None:
    full = root / file_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(source, encoding="utf-8")


def _assert_code_flow(
    monkeypatch,
    tmp_path: Path,
    *,
    pipeline_id: str,
    file_path: str,
    line_number: int,
    source: str,
    expected_code_on_line: str,
    reads_subset: set[str],
    writes_subset: set[str],
    language: str,
    trace_symbol: str | None = None,
    function_name: str | None = None,
) -> None:
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, line_number)
    imports = mcp_server.find_imports(pipeline_id, file_path)
    decorators = mcp_server.find_decorators(pipeline_id, file_path, line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, line_number)

    assert classification["type"] in {"production", "config"}
    actual_code_on_line = extracted["meta"]["code_on_line"].strip()
    expected_fragment = expected_code_on_line.strip()
    assert actual_code_on_line == expected_fragment or expected_fragment in extracted["text"]
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["language"] == language

    if trace_symbol is not None:
        mcp_server.trace_identifier_backward(pipeline_id, file_path, line_number, trace_symbol)

    if function_name is not None:
        callers = mcp_server.find_callers(pipeline_id, file_path, function_name)
        definition = mcp_server.find_definition(pipeline_id, function_name)
        route = mcp_server.find_route_to_function(pipeline_id, function_name)
        assert isinstance(callers, list)
        assert isinstance(definition, list)
        assert isinstance(route, list)


@pytest.mark.parametrize(
    "file_path",
    [
        "app/(dashboard)/organizations/components/OrganizationForm/OrganizationForm.tsx",
        "app/(dashboard)/settings/components/UserForm/UserForm.tsx",
        "app/api/channel-partners-util.ts",
        "app/api/organizations-util.ts",
    ],
)
def test_active_followup_stale_paths_should_preserve_missing_file_behavior(monkeypatch, tmp_path, file_path):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", file_path)

    with pytest.raises(FileNotFoundError):
        mcp_server.extract_function("69ec5b01", file_path, 3)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_imports("69ec5b01", file_path)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_decorators("69ec5b01", file_path, 3)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_identifiers("69ec5b01", file_path, 3)

    assert classification["type"] == "production"


@pytest.mark.parametrize(
    (
        "pipeline_id",
        "file_path",
        "line_number",
        "source",
        "expected_code_on_line",
        "reads_subset",
        "writes_subset",
        "language",
        "trace_symbol",
        "function_name",
    ),
    [
        (
            "69ec5b01",
            "app/(dashboard)/settings/components/UpdateCurrencyDialog/UpdateCurrencyDialog.tsx",
            4,
            """\
function UpdateCurrencyDialog() {
  try {
    return true;
  } catch (error) {
    console.error('Error updating currency:', error.message);
  }
}
""",
            "    console.error('Error updating currency:', error.message);",
            {"console", "error", "message"},
            set(),
            "typescript",
            "error",
            "UpdateCurrencyDialog",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/settings/members/page.tsx",
            6,
            """\
async function handleAddUser(selectedRole) {
  try {
    return selectedRole?.id;
  } catch (error) {
    console.error('Error adding user:', error);
  }
}
""",
            "    console.error('Error adding user:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "selectedRole",
            "handleAddUser",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/subscription-key/components/SuccessfulGenerationForm/SuccessfulGenerationForm.tsx",
            6,
            """\
function copyData(type) {
  try {
    return navigator.clipboard.writeText('value');
  } catch (error) {
    console.error('Error copying text:', error);
  }
}
""",
            "    console.error('Error copying text:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "copyData",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/usage-statements/components/CpServicesPageTab/CpServicesPageTab.tsx",
            6,
            """\
async function handleReportDownload(downloader) {
  try {
    await downloader.initiateDownload();
  } catch (error) {
    console.error('Error initiating report download:', error);
  }
}
""",
            "    console.error('Error initiating report download:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "downloader",
            "handleReportDownload",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/usage-statements/components/CpSubscriptionKeysPageTab/CpSubscriptionKeysPageTab.tsx",
            6,
            """\
async function handleKeyReport(downloader) {
  try {
    await downloader.initiateDownload();
  } catch (error) {
    console.error('Error initiating report download:', error);
  }
}
""",
            "    console.error('Error initiating report download:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "downloader",
            "handleKeyReport",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/usage-statements/components/RunReportForm/RunReportForm.tsx",
            1,
            """\
const onSubmit = (data) => console.log(data);
""",
            "const onSubmit = (data) => console.log(data);",
            {"console", "data", "log"},
            {"onSubmit"},
            "typescript",
            "data",
            None,
        ),
        (
            "69ec5b01",
            "app/(dashboard)/usage-statements/components/StatementsTable/StatementsTable.tsx",
            6,
            """\
async function handleDownload(downloader) {
  try {
    await downloader.initiateDownload();
  } catch (error) {
    console.error('Error initiating report download:', error);
  }
}
""",
            "    console.error('Error initiating report download:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "downloader",
            "handleDownload",
        ),
        (
            "69ec5b01",
            "app/(dashboard)/usage-statements/organizations/[id]/page.tsx",
            6,
            """\
async function OrganizationUsageStatementsPage() {
  try {
    return [];
  } catch (error) {
    console.error('Error initiating report download:', error);
  }
}
""",
            "    console.error('Error initiating report download:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "OrganizationUsageStatementsPage",
        ),
        (
            "69ec5b01",
            "app/(external)/login/complete-signin/page.tsx",
            6,
            """\
async function CompleteSigninPage() {
  try {
    return true;
  } catch (error) {
    console.error('Error completing sign in: ', error);
  }
}
""",
            "    console.error('Error completing sign in: ', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "CompleteSigninPage",
        ),
        (
            "69ec5b01",
            "app/axiosInstance.ts",
            6,
            """\
async function refreshTokenFlow(token) {
  try {
    return token;
  } catch (error) {
    console.error(`Error refreshing token or setting baseURL: ${error}`);
  }
}
""",
            "    console.error(`Error refreshing token or setting baseURL: ${error}`);",
            {"console", "error"},
            set(),
            "typescript",
            "token",
            "refreshTokenFlow",
        ),
        (
            "69ec5b01",
            "app/components/EntityStatusCard/EntityStatusCard.stories.tsx",
            1,
            """\
const story = { onSelect: () => console.log(`${variant.label} active`) };
""",
            "const story = { onSelect: () => console.log(`${variant.label} active`) };",
            {"console", "label", "log", "variant"},
            {"story"},
            "typescript",
            "variant",
            None,
        ),
        (
            "69ec5b01",
            "app/components/InfoDialog/InfoDialog.stories.tsx",
            1,
            """\
const story = { onOpenChange: (open) => console.log('Open state changed:', open) };
""",
            "const story = { onOpenChange: (open) => console.log('Open state changed:', open) };",
            {"console", "log", "open"},
            {"open", "story"},
            "typescript",
            "open",
            None,
        ),
        (
            "69ec5b01",
            "app/components/MyChannelPartner/MyChannelPartner.tsx",
            6,
            """\
function MyChannelPartner() {
  try {
    return navigator.clipboard.writeText('value');
  } catch (error) {
    console.error('Error copying text:', error);
  }
}
""",
            "    console.error('Error copying text:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "MyChannelPartner",
        ),
        (
            "69ec5b01",
            "app/hooks/queries/useOrgStructureData.ts",
            6,
            """\
async function useOrgStructureData(serviceId) {
  try {
    return serviceId;
  } catch (error) {
    console.error('Error fetching site usage record:', error);
  }
}
""",
            "    console.error('Error fetching site usage record:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "serviceId",
            "useOrgStructureData",
        ),
        (
            "69ec5b01",
            "app/hooks/queries/useServicePrice.ts",
            6,
            """\
async function useServicePrice() {
  try {
    return true;
  } catch (error) {
    console.error('Error fetching data:', error);
  }
}
""",
            "    console.error('Error fetching data:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "useServicePrice",
        ),
        (
            "69ec5b01",
            "app/hooks/queries/useUsageServiceDetail.ts",
            6,
            """\
async function useUsageServiceDetail() {
  try {
    return true;
  } catch (error) {
    console.error('Error fetching data:', error);
  }
}
""",
            "    console.error('Error fetching data:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "useUsageServiceDetail",
        ),
        (
            "69ec5b01",
            "app/nx-config-server.ts",
            6,
            """\
async function loadConfig() {
  try {
    return {};
  } catch (error) {
    console.error('Error reading config.json:', error);
  }
}
""",
            "    console.error('Error reading config.json:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "loadConfig",
        ),
        (
            "69ec5b01",
            "app/nx-config.ts",
            6,
            """\
async function fetchConfig() {
  try {
    return {};
  } catch (error) {
    console.error('Error fetching config:', error);
  }
}
""",
            "    console.error('Error fetching config:', error);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "fetchConfig",
        ),
        (
            "69ec5b01",
            "app/oauth-token-handler.ts",
            6,
            """\
async function invalidateNxCloudSession() {
  try {
    return true;
  } catch (error) {
    console.error(`Error invalidating cloud session: ${error}`);
  }
}
""",
            "    console.error(`Error invalidating cloud session: ${error}`);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "invalidateNxCloudSession",
        ),
        (
            "69ec5b01",
            "app/providers.tsx",
            6,
            """\
async function checkAndRefreshToken() {
  try {
    return true;
  } catch (error) {
    console.error(`Error refreshing token: ${error}`);
  }
}
""",
            "    console.error(`Error refreshing token: ${error}`);",
            {"console", "error"},
            set(),
            "typescript",
            "error",
            "checkAndRefreshToken",
        ),
        (
            "69ec5b01",
            "auto_tests/ci/heal_new_failures.py",
            4,
            """\
def heal_new_failures():
    try:
        return True
    except Exception:
        pass
""",
            "    except Exception:",
            set(),
            set(),
            "python",
            None,
            "heal_new_failures",
        ),
        (
            "69ec5b01",
            "auto_tests/ci/prune_pw_artifacts_for_failures.py",
            5,
            """\
def prune_pw_artifacts_for_failures(failed, p, entry):
    if not failed:
        return 0
    if entry:
        shutil.rmtree(os.path.join(p, entry), ignore_errors=True)
""",
            "        shutil.rmtree(os.path.join(p, entry), ignore_errors=True)",
            {"entry", "ignore_errors", "join", "os", "p", "path", "rmtree", "shutil"},
            set(),
            "python",
            "entry",
            "prune_pw_artifacts_for_failures",
        ),
        (
            "5a36b942",
            "cloud/cloud/views/meta.py",
            2,
            """\
def app_view(request):
    response = None
    if redirect_path := check_redirect(request):
        return redirect_path
    return response
""",
            "    response = None",
            set(),
            {"response"},
            "python",
            "request",
            "app_view",
        ),
        (
            "5a36b942",
            "front_end/libs/dialogs/open-authentication-app/open-authentication-app.component.ts",
            4,
            """\
class OpenAuthenticationAppComponent {
  ngOnInit() {
    this.authorizationUrlString = `${window.location.origin}${getAuthorizePath()}?email=${this.accountService.email}&redirect_uri=${window.location.href}&client_type=passwordContinueWorking`;
  }
}
""",
            "    this.authorizationUrlString = `${window.location.origin}${getAuthorizePath()}?email=${this.accountService.email}&redirect_uri=${window.location.href}&client_type=passwordContinueWorking`;",
            {"accountService", "email", "getAuthorizePath", "href", "location", "origin", "window"},
            {"authorizationUrlString"},
            "typescript",
            "authorizationUrlString",
            None,
        ),
        (
            "5a36b942",
            "front_end/libs/features/developers/knowledge-base/knowledge-base.component.ts",
            4,
            """\
class KnowledgeBaseComponent {
  renderScript() {
    const myScript = document.createElement('script');
    myScript.innerHTML = this.pageNode.script;
  }
}
""",
            "    myScript.innerHTML = this.pageNode.script;",
            {"innerHTML", "myScript", "pageNode", "script", "this"},
            set(),
            "typescript",
            "myScript",
            None,
        ),
        (
            "5a36b942",
            "front_end/setSkin.mjs",
            4,
            """\
function setSkin(source, dest) {
  const inlineWizardDest = dest;
  fsmv.copy(source, inlineWizardDest, { mkdirp: true }, error =>
    error ? console.log(error) : null,
  );
}
""",
            "  fsmv.copy(source, inlineWizardDest, { mkdirp: true }, error =>",
            {"copy", "error", "fsmv", "inlineWizardDest", "source"},
            set(),
            "javascript",
            "inlineWizardDest",
            "setSkin",
        ),
        (
            "5a36b942",
            "help/cms/helpman_navigation.js",
            4,
            """\
function saveTocState(items, usecookie) {
  let currenttocstate = '';
  for (var i = 0; i < items.length; i++) currenttocstate = currenttocstate.concat(items[i].id + ',');
  if (usecookie) document.cookie = currenttocstate;
}
""",
            "  if (usecookie) document.cookie = currenttocstate;",
            {"cookie", "currenttocstate", "document", "usecookie"},
            set(),
            "javascript",
            "currenttocstate",
            "saveTocState",
        ),
    ],
)
def test_active_followup_real_finding_shapes_should_keep_code_flow(
    monkeypatch,
    tmp_path,
    pipeline_id,
    file_path,
    line_number,
    source,
    expected_code_on_line,
    reads_subset,
    writes_subset,
    language,
    trace_symbol,
    function_name,
):
    _assert_code_flow(
        monkeypatch,
        tmp_path,
        pipeline_id=pipeline_id,
        file_path=file_path,
        line_number=line_number,
        source=source,
        expected_code_on_line=expected_code_on_line,
        reads_subset=reads_subset,
        writes_subset=writes_subset,
        language=language,
        trace_symbol=trace_symbol,
        function_name=function_name,
    )
