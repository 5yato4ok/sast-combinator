# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.parametrize(
    (
        "pipeline_id",
        "fixture_path",
        "file_path",
        "line_number",
        "function_name",
        "expected_line",
        "required_imports",
        "reads_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
        "expected_definition_kind",
        "expected_caller_lines",
    ),
    [
        (
            "69ec5b01",
            "channel_partner_form/ChannelPartnerForm.error.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
            8,
            "createChannelPartner",
            "			console.error('Error during channel partner creation: ', error);",
            {"import axios from '@/app/axiosInstance';"},
            {"console", "error"},
            "error",
            None,
            4,
            "variable",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/layout.tsx",
            "src/app/layout.tsx",
            11,
            "RootLayout",
            "{React.createElement('meta', {\n          name: 'version',\n          value: config.version\n        })}",
            {
                "import React from 'react';",
                "import { config } from '@/config';",
                "import { AuthGuard } from '@/components/auth/auth-guard';",
            },
            {"React", "config", "createElement", "version"},
            "config",
            None,
            7,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            19,
            "handleOAuthLogin",
            "        logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);",
            {
                "import React, { useEffect, useRef } from 'react';",
                "import { usePathname, useRouter } from 'next/navigation';",
                "import { logger } from '@/lib/logging/default-logger';",
                "import { config } from '@/config';",
            },
            {"error", "logger", "systemInfoResult"},
            "systemInfoResult",
            16,
            14,
            "variable",
            {50},
        ),
        (
            "07734951",
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            24,
            "handleOAuthLogin",
            "      logger.error('[Auth]: OAuth login failed', error);",
            {
                "import React, { useEffect, useRef } from 'react';",
                "import { usePathname, useRouter } from 'next/navigation';",
                "import { logger } from '@/lib/logging/default-logger';",
                "import { config } from '@/config';",
            },
            {"error", "logger"},
            "error",
            None,
            14,
            "variable",
            {50},
        ),
        (
            "07734951",
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            34,
            "checkPermissions",
            "      logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);",
            {
                "import React, { useEffect, useRef } from 'react';",
                "import { usePathname, useRouter } from 'next/navigation';",
                "import { logger } from '@/lib/logging/default-logger';",
                "import { config } from '@/config';",
            },
            {"error", "logger", "systemInfoResult"},
            "systemInfoResult",
            32,
            31,
            "variable",
            {42},
        ),
        (
            "07734951",
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            51,
            "AuthGuard",
            "        logger.error('[Auth]: OAuth login failed on navigation', error);",
            {
                "import React, { useEffect, useRef } from 'react';",
                "import { usePathname, useRouter } from 'next/navigation';",
                "import { logger } from '@/lib/logging/default-logger';",
                "import { config } from '@/config';",
            },
            {"error", "logger"},
            "error",
            None,
            8,
            "function",
            set(),
        ),
        (
            "07734951",
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            15,
            "handleSaveCalibration",
            "        logger.error('Failed to calculate transformation matrix');",
            {
                "import React, { useCallback, useState } from 'react';",
                "import { logger } from '@/lib/logging/default-logger';",
            },
            {"error", "logger"},
            "matrix",
            13,
            11,
            "variable",
            {50},
        ),
        (
            "07734951",
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            22,
            "handleSaveCalibration",
            "      logger.error('Failed to save calibration:', error);",
            {
                "import React, { useCallback, useState } from 'react';",
                "import { logger } from '@/lib/logging/default-logger';",
            },
            {"error", "logger"},
            "error",
            None,
            11,
            "variable",
            {50},
        ),
        (
            "07734951",
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            30,
            "handleResetCalibration",
            "      logger.error('No delete handler provided');",
            {
                "import React, { useCallback, useState } from 'react';",
                "import { logger } from '@/lib/logging/default-logger';",
            },
            {"error", "logger"},
            "error",
            None,
            28,
            "variable",
            {50},
        ),
        (
            "07734951",
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            43,
            "handleResetCalibration",
            "      logger.error('Failed to delete calibration:', error);",
            {
                "import React, { useCallback, useState } from 'react';",
                "import { logger } from '@/lib/logging/default-logger';",
            },
            {"error", "logger"},
            "error",
            None,
            28,
            "variable",
            {50},
        ),
    ],
)
def test_real_findings_auth_guard_actions_and_layout_batch_should_keep_full_flow(
    monkeypatch,
    pipeline_id,
    fixture_path,
    file_path,
    line_number,
    function_name,
    expected_line,
    required_imports,
    reads_subset,
    trace_symbol,
    expected_trace_line,
    expected_definition_line,
    expected_definition_kind,
    expected_caller_lines,
    tmp_path,
):
    source = _fixture_text(fixture_path)
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, Path(file_path).name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, line_number)
    imports = mcp_server.find_imports(pipeline_id, file_path)
    decorators = mcp_server.find_decorators(pipeline_id, file_path, line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, line_number)
    trace = mcp_server.trace_identifier_backward(pipeline_id, file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers(pipeline_id, file_path, function_name)
    definition = mcp_server.find_definition(pipeline_id, function_name)
    route = mcp_server.find_route_to_function(pipeline_id, function_name)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_line
    assert required_imports.issubset(set(imports))
    assert decorators == []
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
    if expected_trace_line is None:
        assert trace == []
    else:
        assert trace
        assert trace[0]["line"] == expected_trace_line
    if expected_caller_lines:
        assert callers
        assert expected_caller_lines.issubset({item["line"] for item in callers if item["file"] == file_path})
    else:
        assert callers == []
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []


