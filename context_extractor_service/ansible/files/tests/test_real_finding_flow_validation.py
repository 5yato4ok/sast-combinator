from pathlib import Path

import mcp_server
from conftest import _stub_read_source


def _stub_resolve_source_dir():
    def _resolver(_pipeline_id: str) -> Path:
        return Path("/tmp")

    return _resolver


def test_real_finding_jenkinsfile_should_follow_config_flow(monkeypatch):
    source = """\
pipeline {
    environment {
        // Primary constants
        SERVICE_NAME = "nx-connect-ui"
        AWS_ACCOUNT_ID = "036867143060"
        AWS_REGION = "us-east-1"

        // Derivative constants
        ECR_URI = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
        SERVICE_ECR_REPOSITORY = "${ECR_URI}/${SERVICE_NAME}"
    }
}
    """
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Jenkinsfile"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "Jenkinsfile")
    environment = mcp_server.classify_environment("69ec5b01", "Jenkinsfile")
    block = mcp_server.extract_config_block("69ec5b01", "Jenkinsfile", 5)

    assert classification["type"] == "config"
    assert environment["environment"] == "unknown"
    assert "AWS_ACCOUNT_ID = \"036867143060\"" in block["block_text"]
    assert block["start_line"] == 3
    assert block["end_line"] == 10


def test_real_finding_landing_page_should_keep_meaningful_identifiers(monkeypatch):
    source = """\
function LandingPage() {
  const timers = [];

  function push() {
    return true;
  }

  timers.push(setTimeout(() => setShowAlert(false), 1600));
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    extracted = mcp_server.extract_function("07734951", "src/app/landing/page.tsx", 8)
    identifiers = mcp_server.find_identifiers("07734951", "src/app/landing/page.tsx", 8)

    assert extracted["meta"]["code_on_line"] == "  timers.push(setTimeout(() => setShowAlert(false), 1600));"
    assert identifiers["reads"] == ["push", "setShowAlert", "setTimeout", "timers"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "typescript"


def test_real_finding_authorization_message_listener_should_keep_event_reads(monkeypatch):
    source = """\
export const createAuthorizationListener =
    (
        cloudApi: NxCloudApiService,
        accountService: NxAccountService,
    ) =>
    async () => {
        const opened = window.open('url', '_blank')!;
        let authenticated = false;
        await new Promise<void>(resolve => {
            window.addEventListener('message', (event: MessageEvent<'authenticated'>) => {
                if (event.data === 'authenticated') {
                    authenticated = true;
                    opened.close();
                    defer(() => cloudApi.getAllAccountInfo(true))
                        .pipe(map(({ account2faEnabled }) => account2faEnabled))
                        .subscribe(resolve);
                }
            });
        });
    };
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "authorization.ts"))

    extracted = mcp_server.extract_function("5a36b942", "front_end/libs/utils/authorization.ts", 10)
    identifiers = mcp_server.find_identifiers("5a36b942", "front_end/libs/utils/authorization.ts", 10)

    assert extracted["meta"]["code_on_line"] == "            window.addEventListener('message', (event: MessageEvent<'authenticated'>) => {"
    assert identifiers["language"] == "typescript"
    assert "window" in identifiers["reads"]
    assert "addEventListener" in identifiers["reads"]
    assert "event" in identifiers["reads"]
    # MessageEvent is a type annotation, not a runtime value


def test_real_finding_menu_change_append_should_keep_append_and_state_label(monkeypatch):
    source = """\
async function setPreviewState(asset_id, create_id, el, state) {
    const selectElement = $(el);
    const stateLabel = `<span>${state}</span>`;
    selectElement.parent().append(stateLabel);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "menuChange.js"))

    extracted = mcp_server.extract_function("5a36b942", "cloud/cms/static/js/menuChange.js", 4)
    identifiers = mcp_server.find_identifiers("5a36b942", "cloud/cms/static/js/menuChange.js", 4)

    assert extracted["meta"]["code_on_line"] == "    selectElement.parent().append(stateLabel);"
    assert identifiers["language"] == "javascript"
    assert "selectElement" in identifiers["reads"]
    assert "parent" in identifiers["reads"]
    assert "append" in identifiers["reads"]
    assert "stateLabel" in identifiers["reads"]
