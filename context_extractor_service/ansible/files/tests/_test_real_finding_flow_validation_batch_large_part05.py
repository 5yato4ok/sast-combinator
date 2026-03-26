# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against real cloud_portal findings on context-extractor.js and template-engine.js. "
        "For generic symbol main, MCP still pollutes find_callers/find_definition with unrelated project-wide main() "
        "functions instead of keeping navigation local to the real module."
    ),
)
@pytest.mark.parametrize(
    ("target_file", "fixture_file", "line_number", "trace_name", "expected_code_on_line", "expected_writes"),
    [
        (
            ".github/chatmodes/modules/context-extractor.js",
            "cloud_portal/main_modules/context-extractor.js",
            18,
            "commitsInput",
            "          commits = JSON.parse(fs.readFileSync(commitsInput, 'utf8'));",
            ["commits"],
        ),
        (
            ".github/chatmodes/modules/context-extractor.js",
            "cloud_portal/main_modules/context-extractor.js",
            35,
            "filesInput",
            "          files = JSON.parse(fs.readFileSync(filesInput, 'utf8'));",
            ["files"],
        ),
        (
            ".github/chatmodes/modules/context-extractor.js",
            "cloud_portal/main_modules/context-extractor.js",
            52,
            "metaDataInput",
            "          metaData = JSON.parse(fs.readFileSync(metaDataInput, 'utf8'));",
            ["metaData"],
        ),
        (
            ".github/chatmodes/modules/template-engine.js",
            "cloud_portal/main_modules/template-engine.js",
            18,
            "dataInput",
            "          data = JSON.parse(fs.readFileSync(dataInput, 'utf8'));",
            ["data"],
        ),
        (
            ".github/chatmodes/modules/template-engine.js",
            "cloud_portal/main_modules/template-engine.js",
            37,
            "analysisInput",
            "          analysisContext = JSON.parse(fs.readFileSync(analysisInput, 'utf8'));",
            ["analysisContext"],
        ),
    ],
)
def test_real_finding_generic_main_navigation_should_stay_local_to_module(
    monkeypatch, tmp_path, target_file, fixture_file, line_number, trace_name, expected_code_on_line, expected_writes
):
    _write_fixture_tree(
        tmp_path,
        {
            ".github/chatmodes/modules/context-extractor.js": "cloud_portal/main_modules/context-extractor.js",
            ".github/chatmodes/modules/template-engine.js": "cloud_portal/main_modules/template-engine.js",
            "get_zip_from_cloud.py": "cloud_portal/main_modules/get_zip_from_cloud.py",
            "build_scripts/extract_brand_core_values.py": "cloud_portal/main_modules/extract_brand_core_values.py",
            "channel_partners/scripts/tests/check_dependencies.py": "cloud_portal/main_modules/check_dependencies.py",
        },
    )
    source = _fixture_text(fixture_file)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, Path(target_file).name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", target_file)
    extracted = mcp_server.extract_function("5a36b942", target_file, line_number)
    imports = mcp_server.find_imports("5a36b942", target_file)
    decorators = mcp_server.find_decorators("5a36b942", target_file, line_number)
    identifiers = mcp_server.find_identifiers("5a36b942", target_file, line_number)
    trace = mcp_server.trace_identifier_backward("5a36b942", target_file, line_number, trace_name)
    callers = mcp_server.find_callers("5a36b942", target_file, "main")
    definition = mcp_server.find_definition("5a36b942", "main")
    route = mcp_server.find_route_to_function("5a36b942", "main")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_code_on_line
    assert "import fs from 'fs';" in imports
    assert decorators == []
    assert identifiers["writes"] == expected_writes
    assert identifiers["language"] == "javascript"
    assert trace[0]["writes"] == [trace_name]
    assert callers == [
        {
            "file": target_file,
            "line": 26 if "context-extractor" in target_file else 47,
            "caller_function": None,
            "snippet": callers[0]["snippet"],
        }
    ]
    assert definition == [
        {
            "file": target_file,
            "line": 2,
            "kind": "function",
            "snippet": definition[0]["snippet"],
        }
    ]
    assert route == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real cloud_portal finding on content.component.ts:105. "
        "The target line is blank, but MCP still leaks identifiers from the surrounding block "
        "instead of returning empty reads and writes for the real line."
    ),
)
def test_real_finding_content_component_blank_line_should_not_leak_identifiers(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/content_component/content.component.ts")
    _write_source_tree(tmp_path, "front_end/libs/features/content/content.component.ts", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "content.component.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", "front_end/libs/features/content/content.component.ts")
    extracted = mcp_server.extract_function("5a36b942", "front_end/libs/features/content/content.component.ts", 24)
    imports = mcp_server.find_imports("5a36b942", "front_end/libs/features/content/content.component.ts")
    decorators = mcp_server.find_decorators("5a36b942", "front_end/libs/features/content/content.component.ts", 24)
    identifiers = mcp_server.find_identifiers("5a36b942", "front_end/libs/features/content/content.component.ts", 24)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == ""
    assert "import { COOKIE_POLICY_CHANNEL } from '@libs/variables/broadcast-channels';" in imports
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx finding on virtual_camera_action_handler.cpp:86. "
        "find_callers still treats the destructor and header declaration as callers of the constructor "
        "instead of returning no callers for the real target shape."
    ),
)
def test_real_finding_virtual_camera_constructor_should_not_treat_destructor_as_caller(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.cpp": "virtual_camera/virtual_camera_action_handler.cpp",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.h": "virtual_camera/virtual_camera_action_handler.h",
        },
    )
    source = _fixture_text("virtual_camera/virtual_camera_action_handler.cpp")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "virtual_camera_action_handler.cpp"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.cpp"
    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 13)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 13)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 13)
    callers = mcp_server.find_callers("9ce90895", file_path, "VirtualCameraActionHandler")
    definition = mcp_server.find_definition("9ce90895", "VirtualCameraActionHandler")
    route = mcp_server.find_route_to_function("9ce90895", "VirtualCameraActionHandler")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    using namespace menu;"
    assert '#include "virtual_camera_action_handler.h"' in imports
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "cpp"}
    assert callers == []
    assert route == []
    assert definition == [
        {
            "file": "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.h",
            "line": 3,
            "kind": "class",
            "snippet": "        1| namespace nx::vms::client::desktop {\n        2| \n>>>     3| class VirtualCameraActionHandler:\n        4|     public QObject,\n        5|     public WindowContextAware",
        },
        {
            "file": "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/virtual_camera/virtual_camera_action_handler.h",
            "line": 11,
            "kind": "function",
            "snippet": "        9| \n       10| public:\n>>>    11|     explicit VirtualCameraActionHandler(WindowContext* windowContext, QObject* parent = nullptr);\n       12|     virtual ~VirtualCameraActionHandler() override;\n       13| ",
        },
    ]


def test_real_finding_jenkinsfile_config_flow_should_keep_real_outputs(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/ci/Jenkinsfile")
    _write_source_tree(tmp_path, "Jenkinsfile", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Jenkinsfile"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", "Jenkinsfile")
    environment = mcp_server.classify_environment("69ec5b01", "Jenkinsfile")
    block = mcp_server.extract_config_block("69ec5b01", "Jenkinsfile", 4)
    env_vars = mcp_server.extract_env_variables("69ec5b01", "Jenkinsfile")
    related = mcp_server.find_related_configs("69ec5b01", "Jenkinsfile")

    assert classification == {
        "type": "config",
        "confidence": 0.9,
        "reason": "filename is a CI/build pipeline file",
    }
    assert environment["environment"] == "unknown"
    assert environment["confidence"] == 0.5
    assert block == {
        "block_text": (
            '        // Primary constants\n'
            '        SERVICE_NAME = "nx-connect-ui"\n'
            '        AWS_ACCOUNT_ID = "036867143060"\n'
            '        AWS_REGION = "us-east-1"\n'
            '\n'
            '        // Derivative constants\n'
            '        ECR_URI = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"\n'
            '        SERVICE_ECR_REPOSITORY = "${ECR_URI}/${SERVICE_NAME}"\n'
            '        UNIQUE_DOCKER_TAG = "${env.GIT_COMMIT}.${env.BUILD_NUMBER}"\n'
            '        IMAGE_FULL_SPEC = "${SERVICE_ECR_REPOSITORY}:${UNIQUE_DOCKER_TAG}"\n'
            '        IMAGE_LATEST_SPEC = "${SERVICE_ECR_REPOSITORY}:latest"'
        ),
        "block_type": "indented_block",
        "key_path": "",
        "start_line": 3,
        "end_line": 13,
    }
    assert env_vars == [
        {"name": "SERVICE_NAME", "value": "nx-connect-ui", "source": "dotenv", "line": 4, "has_secret_pattern": False},
        {"name": "AWS_ACCOUNT_ID", "value": "036867143060", "source": "dotenv", "line": 5, "has_secret_pattern": False},
        {"name": "AWS_REGION", "value": "us-east-1", "source": "dotenv", "line": 6, "has_secret_pattern": False},
        {"name": "ECR_URI", "value": "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com", "source": "dotenv", "line": 9, "has_secret_pattern": False},
        {"name": "SERVICE_ECR_REPOSITORY", "value": "${ECR_URI}/${SERVICE_NAME}", "source": "dotenv", "line": 10, "has_secret_pattern": False},
        {"name": "UNIQUE_DOCKER_TAG", "value": "${env.GIT_COMMIT}.${env.BUILD_NUMBER}", "source": "dotenv", "line": 11, "has_secret_pattern": False},
        {"name": "IMAGE_FULL_SPEC", "value": "${SERVICE_ECR_REPOSITORY}:${UNIQUE_DOCKER_TAG}", "source": "dotenv", "line": 12, "has_secret_pattern": False},
        {"name": "IMAGE_LATEST_SPEC", "value": "${SERVICE_ECR_REPOSITORY}:latest", "source": "dotenv", "line": 13, "has_secret_pattern": False},
    ]
    assert related == []


def test_real_finding_root_layout_client_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/root_layout/RootLayoutClient.tsx")
    _write_source_tree(tmp_path, "app/(external)/RootLayoutClient.tsx", source)
    _write_source_tree(tmp_path, "app/(dashboard)/RootLayoutClient.tsx", _fixture_text("nx_connect/root_layout/DashboardRootLayoutClient.tsx"))
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "RootLayoutClient.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(external)/RootLayoutClient.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 8)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 8)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 8)
    trace_config = mcp_server.trace_identifier_backward("69ec5b01", file_path, 8, "configData")
    trace_domain = mcp_server.trace_identifier_backward("69ec5b01", file_path, 8, "domain")
    callers = mcp_server.find_callers("69ec5b01", file_path, "RootLayoutClient")
    definition = mcp_server.find_definition("69ec5b01", "RootLayoutClient")
    route = mcp_server.find_route_to_function("69ec5b01", "RootLayoutClient")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\tconst trackingID = domain.includes('connect.nxgo.io') ? 'G-ZFX72ZBEEX' : configData?.GOOGLE_ANALYTICS_ID;"
    assert "import Logo from '@/app/(external)/components/Logo/Logo';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["GOOGLE_ANALYTICS_ID", "configData", "domain", "includes"],
        "writes": ["trackingID"],
        "language": "typescript",
    }
    assert trace_config == [{"line": 4, "code": "const configData = await fetchConfig();", "writes": ["configData"], "reads": ["fetchConfig"]}]
    assert trace_domain == [{"line": 7, "code": "const domain = window.location.hostname;", "writes": ["domain"], "reads": ["hostname", "location", "window"]}]
    assert callers == []
    assert route == []
    assert any(item["file"] == "app/(external)/RootLayoutClient.tsx" for item in definition)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-connect-ui finding on CompanyAndContactInfo.tsx:115. "
        "For generic helper resizeWindow, MCP still mixes callers and definitions from other files "
        "instead of keeping navigation local to the component helper."
    ),
)
def test_real_finding_company_contact_resize_window_navigation_should_stay_local(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "app/(dashboard)/channel-partners/[id]/components/CompanyAndContactInfo/CompanyAndContactInfo.tsx": "nx_connect/company_contact/CompanyAndContactInfo.tsx",
            "app/(dashboard)/channel-partners/[id]/page.tsx": "nx_connect/company_contact/ChannelPartnerPage.tsx",
            "app/(dashboard)/subscription-key/components/SubscriptionKeysTable/SubscriptionKeysTable.tsx": "nx_connect/company_contact/SubscriptionKeysTable.tsx",
        },
    )
    source = _fixture_text("nx_connect/company_contact/CompanyAndContactInfo.tsx")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "CompanyAndContactInfo.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/[id]/components/CompanyAndContactInfo/CompanyAndContactInfo.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 13)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 13)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 13)
    callers = mcp_server.find_callers("69ec5b01", file_path, "resizeWindow")
    definition = mcp_server.find_definition("69ec5b01", "resizeWindow")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t};"
    assert "import React from 'react';" in imports
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}
    assert callers == [{"file": file_path, "line": 15, "caller_function": None, "snippet": callers[0]["snippet"]}]
    assert definition == [{"file": file_path, "line": 1, "kind": "variable", "snippet": definition[0]["snippet"]}]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-connect-ui finding on page.tsx:199. "
        "The target line is blank, but MCP still leaks identifiers from the surrounding block "
        "instead of returning empty reads and writes for the real line."
    ),
)
def test_real_finding_channel_partner_details_blank_line_should_not_leak_identifiers(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/channel_partner_details/page.tsx")
    _write_source_tree(tmp_path, "app/(dashboard)/channel-partners/[id]/page.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/[id]/page.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 7)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 7)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 7)
    definition = mcp_server.find_definition("69ec5b01", "ChannelPartnerDetails")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == ""
    assert "import React from 'react';" in imports
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}
    assert definition == [{"file": file_path, "line": 1, "kind": "function", "snippet": definition[0]["snippet"]}]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-maps-ui finding on generate-customization.js:18. "
        "For generic helper fetch, MCP still pulls unrelated callers from other files instead of "
        "keeping navigation local to the script."
    ),
)
def test_real_finding_generate_customization_fetch_navigation_should_stay_local(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "scripts/generate-customization.js": "nx_maps/generate_customization.js",
            "src/app/debug/oauth/page.tsx": "nx_maps/OAuthDebugPage.tsx",
        },
    )
    source = _fixture_text("nx_maps/generate_customization.js")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "scripts/generate-customization.js"
    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, 8)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, 8)
    identifiers = mcp_server.find_identifiers("07734951", file_path, 8)
    callers = mcp_server.find_callers("07734951", file_path, "fetch")
    definition = mcp_server.find_definition("07734951", "fetch")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    protocol.get(url, (res) => {"
    assert "const https = require('https');" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["Error", "URL", "chunk", "console", "data", "fetch", "get", "headers", "href", "location", "log", "maxRedirects", "on", "protocol", "redirectUrl", "reject", "res", "resolve", "statusCode", "url"],
        "writes": [],
        "language": "javascript",
    }
    assert callers == [{"file": file_path, "line": 13, "caller_function": "fetch", "snippet": callers[0]["snippet"]}]
    assert definition == [{"file": file_path, "line": 1, "kind": "function", "snippet": definition[0]["snippet"]}]


