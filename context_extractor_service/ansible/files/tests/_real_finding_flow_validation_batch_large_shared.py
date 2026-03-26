import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


FIXTURE_SOURCE_MAP = {
    "5a36b942": {
        "cloud/cms/static/js/menuChange.js": "part22/menuChange.js",
        "front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts": (
            "part22/channel-partners-api.spec.ts"
        ),
        ".github/chatmodes/modules/git-operations.js": "part22/git-operations.js",
    },
    "07734951": {
        "src/lib/logging/logger.ts": "nx_maps_ui/logger.ts",
        "src/components/map/edit/AdvancedFOVDialog.tsx": "advanced_fov/AdvancedFOVDialog.logger.tsx",
    },
    "69ec5b01": {
        "app/helpers.ts": "nx_connect/helpers.move_to_next.ts",
        "app/components/ServiceInput/ServiceInput.tsx": "nx_connect/ServiceInput.tsx",
    },
    "9ce90895": {
        "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_shm_utils.cpp": "part22/nxai_shm_utils.cpp",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_administration/widgets/security_settings_widget.cpp": (
            "part22/security_settings_widget.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_health/cloud_storage_watcher.cpp": (
            "part22/cloud_storage_watcher.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp": (
            "part22/connect_actions_handler.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.h": (
            "part22/connect_actions_handler.h"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp": (
            "server_certificate_warning/server_certificate_warning.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/ui/widgets/properties/server_settings_widget.cpp": (
            "part22/server_settings_widget.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_viewer.cpp": (
            "part22/server_certificate_viewer.cpp"
        ),
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/welcome_screen.cpp": (
            "part22/welcome_screen.cpp"
        ),
    },
}


FIXTURE_LINE_MAPS = {
    ("5a36b942", "cloud/cms/static/js/menuChange.js"): {355: 1, 359: 3},
    (
        "5a36b942",
        "front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts",
    ): {385: 1, 389: 5, 390: 6},
    ("5a36b942", ".github/chatmodes/modules/git-operations.js"): {55: 25, 107: 32, 116: 41, 684: 2, 702: 18},
    ("07734951", "src/lib/logging/logger.ts"): {109: 4, 113: 5, 117: 12, 119: 14},
    ("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx"): {166: 10, 167: 15},
    (
        "9ce90895",
        "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_shm_utils.cpp",
    ): {47: 5},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_administration/widgets/security_settings_widget.cpp",
    ): {281: 1, 306: 11, 411: 7},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_health/cloud_storage_watcher.cpp",
    ): {12: 1, 15: 7, 85: 11},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
    ): {147: 1, 310: 11, 336: 8, 533: 13, 567: 17},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
    ): {24: 8, 136: 18},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/ui/widgets/properties/server_settings_widget.cpp",
    ): {59: 1, 607: 3},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_viewer.cpp",
    ): {54: 1, 153: 3, 368: 6},
    (
        "9ce90895",
        "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/welcome_screen.cpp",
    ): {63: 1, 136: 11, 331: 7},
    ("69ec5b01", "app/helpers.ts"): {238: 3, 265: 6},
    ("69ec5b01", "app/components/ServiceInput/ServiceInput.tsx"): {290: 4},
}


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def _stub_resolve_source_dir():
    def _resolver(_pipeline_id: str) -> Path:
        return Path("/tmp")

    return _resolver


def _write_source_tree(root: Path, file_path: str, source: str) -> None:
    full = root / file_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(source, encoding="utf-8")


def _stub_real_source_dir(root: str):
    def _resolver(_pipeline_id: str) -> Path:
        return Path(root)

    return _resolver


def _fixture_text(relative_path: str) -> str:
    return (ROOT / "fixtures" / "real_finding_flow" / relative_path).read_text(encoding="utf-8")


def _real_source_text(pipeline_id: str, file_path: str) -> str:
    return _fixture_text(FIXTURE_SOURCE_MAP[pipeline_id][file_path])


def _map_fixture_line(pipeline_id: str, file_path: str, line_number: int | None):
    if line_number is None:
        return None
    return FIXTURE_LINE_MAPS.get((pipeline_id, file_path), {}).get(line_number, line_number)


def _write_fixture_tree(root: Path, mapping: dict[str, str]) -> None:
    for source_path, fixture_path in mapping.items():
        _write_source_tree(root, source_path, _fixture_text(fixture_path))


def _patch_real_run_root(monkeypatch, pipeline_id: str) -> None:
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: Path("/tmp"))



__all__ = [
    "Path",
    "FIXTURE_SOURCE_MAP",
    "FIXTURE_LINE_MAPS",
    "ROOT",
    "_fixture_text",
    "_map_fixture_line",
    "_patch_real_run_root",
    "_real_source_text",
    "_stub_read_source",
    "_stub_real_source_dir",
    "_stub_resolve_source_dir",
    "_write_fixture_tree",
    "_write_source_tree",
    "mcp_server",
    "pytest",
]
