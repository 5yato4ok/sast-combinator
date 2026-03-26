import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live_mcp_group_audit import (
    _collect_mcp_payload,
    _candidate_function_name,
    _candidate_trace_identifiers,
    _is_config_path,
    _tools_for_group,
    summarize,
)


def test_is_config_path_matches_realistic_finding_paths():
    assert _is_config_path("cloud/ams/deploy/ams_service_crash_receiver/Dockerfile") is True
    assert _is_config_path("deploy/cloud_portal/flowerconfig.py") is True
    assert _is_config_path("src/config.ts") is False
    assert _is_config_path("front_end/libs/services/uri.service.ts") is False


def test_tools_for_group_switches_between_code_and_config_flows():
    config_group = {
        "pipeline_id": "9ce90895",
        "title": "Missing User",
        "file_path": "cloud/ams/deploy/ams_service_crash_receiver/Dockerfile",
        "line": 40,
        "count": 1,
    }
    code_group = {
        "pipeline_id": "5a36b942",
        "title": "Open Redirect Vulnerability",
        "file_path": "front_end/libs/services/uri.service.ts",
        "line": 39,
        "count": 1,
    }

    assert [name for name, _args in _tools_for_group(config_group)] == [
        "classify_file",
        "classify_environment",
        "extract_config_block",
        "extract_env_variables",
        "find_related_configs",
    ]
    assert [name for name, _args in _tools_for_group(code_group)] == [
        "classify_file",
        "extract_function",
        "find_imports",
        "find_decorators",
        "find_identifiers",
    ]


def test_candidate_trace_identifiers_prefers_simple_read_variables():
    payload = {
        "reads": ["window", "newPort", "window.location", "review-url", "window"],
        "writes": [],
    }

    assert _candidate_trace_identifiers(payload) == ["window", "newPort"]


def test_candidate_function_name_extracts_common_shapes():
    assert _candidate_function_name({"text": """def change_view(request):
    return True
"""}) == "change_view"
    assert _candidate_function_name({"text": """export default function Alert() {
  return null
}
"""}) == "Alert"
    assert _candidate_function_name({"text": """const MapSearch = ({ a }) => {
  return a
}
"""}) == "MapSearch"
    assert _candidate_function_name({"text": """void ItemGrabber::grabToImage()
{
}
"""}) == "grabToImage"


def test_summarize_counts_errors_anomalies_and_tool_usage():
    report = [
        {
            "group": {"file_path": "a.ts", "line": 1},
            "results": [
                {
                    "tool": "extract_function",
                    "is_error": False,
                    "payload": {},
                    "anomalies": ["code_on_line_too_large"],
                },
                {
                    "tool": "find_identifiers",
                    "is_error": True,
                    "payload": "Unsupported file extension",
                    "anomalies": ["unsupported_tsx_identifiers"],
                },
                {
                    "tool": "trace_identifier_backward",
                    "is_error": False,
                    "payload": {"reads": ["processor"], "writes": ["processor"]},
                    "anomalies": ["trace_self_referential_assignment"],
                },
                {
                    "tool": "find_route_to_function",
                    "is_error": False,
                    "payload": {"file": "cloud/cms/static/tinymce/js/tinymce/tinymce.min.js", "pattern": "/admin"},
                    "anomalies": ["route_to_vendor_asset"],
                },
            ],
        },
        {
            "group": {"file_path": "Dockerfile", "line": 10},
            "results": [
                {
                    "tool": "find_related_configs",
                    "is_error": False,
                    "payload": {},
                    "anomalies": ["shell_script_false_related_config"],
                },
            ],
        },
    ]

    summary = summarize(report)

    assert summary["groups"] == 2
    assert summary["tool_errors"] == 1
    assert summary["tool_counts"] == {
        "extract_function": 1,
        "find_identifiers": 1,
        "find_related_configs": 1,
        "find_route_to_function": 1,
        "trace_identifier_backward": 1,
    }
    assert summary["anomalies"] == {
        "code_on_line_too_large": 1,
        "route_to_vendor_asset": 1,
        "shell_script_false_related_config": 1,
        "trace_self_referential_assignment": 1,
        "unsupported_tsx_identifiers": 1,
    }


class _FakeContentItem:
    def __init__(self, text: str):
        self.text = text


def test_collect_mcp_payload_should_preserve_multiple_dict_items():
    payload = _collect_mcp_payload(
        [
            _FakeContentItem('{"file":"page.ts","line":2,"caller_function":"run"}'),
            _FakeContentItem('{"file":"page.ts","line":5,"caller_function":null}'),
        ]
    )

    assert payload == [
        {"file": "page.ts", "line": 2, "caller_function": "run"},
        {"file": "page.ts", "line": 5, "caller_function": None},
    ]



def test_candidate_function_name_should_not_extract_void_from_anonymous_typed_arrow():
    payload = {
        "text": """(
        cloudApi: NxCloudApiService,
        accountService: NxAccountService,
        handleWindowRef: (opened: Window) => void = () => {},
    ) =>
    async () => {
        return true;
    }""",
    }

    assert _candidate_function_name(payload) is None
