# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

def test_real_finding_channel_partner_delete_flow_should_keep_full_code_flow_outputs(monkeypatch, tmp_path):
    source = _fixture_text("channel_partner_form/ChannelPartnerForm.tsx")
    _write_source_tree(
        tmp_path,
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        source,
    )
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ChannelPartnerForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
    )
    extracted = mcp_server.extract_function(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        27,
    )
    imports = mcp_server.find_imports(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
    )
    decorators = mcp_server.find_decorators(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        27,
    )
    identifiers = mcp_server.find_identifiers(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        27,
    )
    trace_axios = mcp_server.trace_identifier_backward(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        27,
        "axios",
    )
    callers = mcp_server.find_callers(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        "ChannelPartnerForm",
    )
    route = mcp_server.find_route_to_function("69ec5b01", "ChannelPartnerForm")
    definition = mcp_server.find_definition("69ec5b01", "ChannelPartnerForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\treturn axios"
    assert any("import axios" in item for item in imports)
    assert decorators == []
    assert identifiers == {
        "reads": ["axios", "catch", "console", "delete", "email", "error", "newSubCpId", "then"],
        "writes": [],
        "language": "typescript",
    }
    assert trace_axios == []
    assert callers == []
    assert route == []
    assert definition[0]["file"] == "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx"
    assert definition[0]["line"] == 4
    assert definition[0]["kind"] == "function"


def test_real_finding_advanced_fov_wrapper_should_keep_full_helper_flow_outputs(monkeypatch, tmp_path):
    source = _fixture_text("advanced_fov/AdvancedFOVDialog.wrapper.tsx")
    _write_source_tree(tmp_path, "src/components/map/edit/AdvancedFOVDialog.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    extracted = mcp_server.extract_function("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 26)
    imports = mcp_server.find_imports("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    decorators = mcp_server.find_decorators("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 26)
    identifiers = mcp_server.find_identifiers("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 26)
    trace_handle_map_hover = mcp_server.trace_identifier_backward(
        "07734951",
        "src/components/map/edit/AdvancedFOVDialog.tsx",
        26,
        "handleMapHover",
    )
    callers = mcp_server.find_callers(
        "07734951",
        "src/components/map/edit/AdvancedFOVDialog.tsx",
        "handleMapHover",
    )
    route = mcp_server.find_route_to_function("07734951", "handleMapHover")
    definition = mcp_server.find_definition("07734951", "handleMapHover")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "  const handleMapHoverWrapper = useCallback((lngLat: { lng: number; lat: number } | null) => {"
    assert imports == [
        "import React, { useCallback, useState } from 'react';",
        "import { logger } from '@/lib/logging/default-logger';",
    ]
    assert decorators == []
    assert identifiers == {
        "reads": ["handleMapHover", "lngLat", "setMapCursorActive", "useCallback"],
        "writes": ["handleMapHoverWrapper"],
        "language": "typescript",
    }
    assert trace_handle_map_hover == [
        {
                "line": 15,
                "code": "const handleMapHover = useCallback((lngLat: { lng: number; lat: number } | null) => {",
                "writes": ["handleMapHover"],
                "reads": [
                    "lat",
                    "lng",
                    "lngLat",
                    "mapped",
                    "setThumbnailPreviewFromMap",
                    "transformPoint",
                    "useCallback",
                ],
            },
        {
            "line": 8,
            "code": "const transformPoint = useCallback((",
            "writes": ["transformPoint"],
            "reads": ["lat", "lng", "useCallback"],
        },
    ]
    assert callers == [
        {
            "file": "src/components/map/edit/AdvancedFOVDialog.tsx",
            "line": 28,
            "caller_function": "AdvancedFOVDialog",
            "snippet": "       27|     setMapCursorActive(!!lngLat);\n>>>    28|     handleMapHover(lngLat);\n       29|   }, [handleMapHover]);",
        }
    ]
    assert route == []
    assert definition == [
        {
            "file": "src/components/map/edit/AdvancedFOVDialog.tsx",
            "line": 15,
            "kind": "variable",
            "snippet": "       13|   }, []);\n       14| \n>>>    15|   const handleMapHover = useCallback((lngLat: { lng: number; lat: number } | null) => {\n       16|     if (!lngLat) {\n       17|       setThumbnailPreviewFromMap(null);",
        }
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx finding on server_certificate_warning.cpp:136. "
        "There are no real caller sites in the project source, but find_callers still returns "
        "the constructor declaration from the header as if it were a caller."
    ),
)
def test_real_finding_server_certificate_warning_should_not_treat_constructor_declaration_as_caller(monkeypatch):
    source = _fixture_text("server_certificate_warning/server_certificate_warning.cpp")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "server_certificate_warning.cpp"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
    )
    extracted = mcp_server.extract_function(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
        17,
    )
    identifiers = mcp_server.find_identifiers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
        17,
    )
    callers = mcp_server.find_callers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
        "ServerCertificateWarning",
    )
    definition = mcp_server.find_definition("9ce90895", "ServerCertificateWarning")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "                auto viewer = new ServerCertificateViewer("
    assert identifiers == {
        "reads": ["ServerCertificateViewer", "certificateInfo", "presented", "this"],
        "writes": ["viewer"],
        "language": "cpp",
    }
    assert callers == []
    assert definition[0]["kind"] == "class"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-connect-ui finding on app/helpers.ts:265. "
        "The helper findNextFocusable is defined in the same file, but find_definition still "
        "returns no definition for it during the triage flow."
    ),
)
def test_real_finding_helpers_move_to_next_focusable_should_keep_full_real_helper_flow(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "app/helpers.ts": "nx_connect/helpers.move_to_next.ts",
            "app/components/ServiceInput/ServiceInput.tsx": "nx_connect/ServiceInput.tsx",
        },
    )
    source = _fixture_text("nx_connect/helpers.move_to_next.ts")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "helpers.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", "app/helpers.ts")
    extracted = mcp_server.extract_function("69ec5b01", "app/helpers.ts", 6)
    imports = mcp_server.find_imports("69ec5b01", "app/helpers.ts")
    decorators = mcp_server.find_decorators("69ec5b01", "app/helpers.ts", 6)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/helpers.ts", 6)
    trace_next_focusable = mcp_server.trace_identifier_backward("69ec5b01", "app/helpers.ts", 6, "findNextFocusable")
    callers = mcp_server.find_callers("69ec5b01", "app/helpers.ts", "moveToNextFocusable")
    route = mcp_server.find_route_to_function("69ec5b01", "moveToNextFocusable")
    definition = mcp_server.find_definition("69ec5b01", "findNextFocusable")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "const nextFocusable = findNextFocusable();"
    assert imports == ['import { focusElement } from "./focus";']
    assert decorators == []
    assert identifiers == {
        "reads": ["findNextFocusable"],
        "writes": ["nextFocusable"],
        "language": "typescript",
    }
    assert trace_next_focusable == []
    assert callers == [
        {
            "file": "app/components/ServiceInput/ServiceInput.tsx",
            "line": 4,
            "caller_function": "ServiceInput",
            "snippet": "        3| export function ServiceInput(): React.JSX.Element {\n>>>     4|     if (!moveToNextFocusable()) {\n        5|         handleInputBlur();",
        }
    ]
    assert route == []
    assert definition == []


def test_real_finding_advanced_fov_logger_line_should_keep_full_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("advanced_fov/AdvancedFOVDialog.logger.tsx")
    _write_source_tree(tmp_path, "src/components/map/edit/AdvancedFOVDialog.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    extracted = mcp_server.extract_function("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 23)
    imports = mcp_server.find_imports("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    decorators = mcp_server.find_decorators("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 23)
    identifiers = mcp_server.find_identifiers("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 23)
    trace_error = mcp_server.trace_identifier_backward("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 23, "error")
    trace_logger = mcp_server.trace_identifier_backward("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 23, "logger")
    callers = mcp_server.find_callers("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", "AdvancedFOVDialog")
    route = mcp_server.find_route_to_function("07734951", "AdvancedFOVDialog")
    definition = mcp_server.find_definition("07734951", "AdvancedFOVDialog")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "      logger.error('Failed to transform point:', error);"
    assert "import { logger } from '@/lib/logging/default-logger';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["error", "logger"],
        "writes": [],
        "language": "typescript",
    }
    assert trace_error == []
    assert trace_logger == []
    assert callers == []
    assert route == []
    assert definition == [
        {
            "file": "src/components/map/edit/AdvancedFOVDialog.tsx",
            "line": 6,
            "kind": "function",
            "snippet": "        4| import { logger } from '@/lib/logging/default-logger';\n        5| \n>>>     6| export function AdvancedFOVDialog({\n        7|   show,\n        8|   thumbnail,",
        }
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx finding on connect_actions_handler.cpp:338. "
        "There are no real project callers for ConnectActionsHandler, but find_callers still "
        "returns the declaration and destructor as if they were caller sites."
    ),
)
def test_real_finding_connect_actions_handler_should_not_treat_declaration_and_destructor_as_callers(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp": (
                "connect_actions_handler_callers/connect_actions_handler.cpp"
            ),
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.h": (
                "connect_actions_handler_callers/connect_actions_handler.h"
            ),
        },
    )
    source = _fixture_text("connect_actions_handler_callers/connect_actions_handler.cpp")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "connect_actions_handler.cpp"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
    )
    extracted = mcp_server.extract_function(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        8,
    )
    imports = mcp_server.find_imports(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
    )
    decorators = mcp_server.find_decorators(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        8,
    )
    identifiers = mcp_server.find_identifiers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        8,
    )
    callers = mcp_server.find_callers(
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
        "ConnectActionsHandler",
    )
    route = mcp_server.find_route_to_function("9ce90895", "ConnectActionsHandler")
    definition = mcp_server.find_definition("9ce90895", "ConnectActionsHandler")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == (
        ""
    )
    assert '#include "connect_actions_handler.h"' in imports
    assert decorators == []
    assert identifiers["language"] == "cpp"
    assert {"connectTimeout", "crashReporter", "resourceModeAction", "sessionTimeoutWatcher"}.issubset(
        set(identifiers["reads"])
    )
    assert callers == []
    assert route == []
    assert any(item["file"].endswith("connect_actions_handler.h") and item["line"] == 1 and item["kind"] == "class" for item in definition)
