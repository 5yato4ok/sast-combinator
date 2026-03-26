# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

def test_real_finding_landing_page_timer_flow_should_keep_real_outputs(monkeypatch, tmp_path):
    source = _fixture_text("landing_page/page.tsx")
    _write_source_tree(tmp_path, "src/app/landing/page.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", "src/app/landing/page.tsx")
    extracted = mcp_server.extract_function("07734951", "src/app/landing/page.tsx", 17)
    imports = mcp_server.find_imports("07734951", "src/app/landing/page.tsx")
    decorators = mcp_server.find_decorators("07734951", "src/app/landing/page.tsx", 17)
    identifiers = mcp_server.find_identifiers("07734951", "src/app/landing/page.tsx", 17)
    trace_set_show_alert = mcp_server.trace_identifier_backward("07734951", "src/app/landing/page.tsx", 17, "setShowAlert")
    callers = mcp_server.find_callers("07734951", "src/app/landing/page.tsx", "LandingPage")
    route = mcp_server.find_route_to_function("07734951", "LandingPage")
    definition = mcp_server.find_definition("07734951", "LandingPage")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    timers.push(setTimeout(() => setShowAlert(false), 1600));"
    assert "import { trackPromoLinkClick } from '@/lib/logging/analytics';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["push", "setShowAlert", "setTimeout", "timers"],
        "writes": [],
        "language": "typescript",
    }
    assert trace_set_show_alert == [
        {
            "line": 6,
            "code": "const [showAlert, setShowAlert] = useState(true);",
            "writes": ["setShowAlert"],
            "reads": ["useState"],
        }
    ]
    assert callers == []
    assert route == []
    assert definition == [
        {
            "file": "src/app/landing/page.tsx",
            "line": 3,
            "kind": "function",
            "snippet": "        1| import { trackPromoLinkClick } from '@/lib/logging/analytics';\n        2| \n>>>     3| export default function LandingPage() {\n        4|   const { t } = useTranslation();\n        5|   const videoRef = useRef<HTMLVideoElement>(null);",
        }
    ]


def test_real_finding_kmz_logger_debug_flow_should_keep_real_outputs(monkeypatch, tmp_path):
    source = _fixture_text("kmz_parser/kmz-parser.ts")
    _write_source_tree(tmp_path, "src/lib/map/kmz-parser.ts", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "kmz-parser.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", "src/lib/map/kmz-parser.ts")
    extracted = mcp_server.extract_function("07734951", "src/lib/map/kmz-parser.ts", 12)
    imports = mcp_server.find_imports("07734951", "src/lib/map/kmz-parser.ts")
    decorators = mcp_server.find_decorators("07734951", "src/lib/map/kmz-parser.ts", 12)
    identifiers = mcp_server.find_identifiers("07734951", "src/lib/map/kmz-parser.ts", 12)
    trace_image_files = mcp_server.trace_identifier_backward("07734951", "src/lib/map/kmz-parser.ts", 12, "imageFiles")
    callers = mcp_server.find_callers("07734951", "src/lib/map/kmz-parser.ts", "extractIcons")
    route = mcp_server.find_route_to_function("07734951", "extractIcons")
    definition = mcp_server.find_definition("07734951", "extractIcons")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "  logger.debug(`[KMZ] Found ${imageFiles.length} image files in KMZ:`, imageFiles);"
    assert imports == [
        "import JSZip from 'jszip';",
        "import { logger } from '@/lib/logging/default-logger';",
        "import type { GeoJSONData, GeoJSONFeature } from '@/types/map';",
    ]
    assert decorators == []
    assert identifiers == {
        "reads": ["debug", "imageFiles", "length", "logger"],
        "writes": [],
        "language": "typescript",
    }
    assert trace_image_files == [
        {
            "line": 8,
            "code": "const imageFiles = Object.keys(zipFile.files).filter(name =>",
            "writes": ["imageFiles"],
            "reads": ["Object", "files", "filter", "keys", "match", "name", "toLowerCase", "zipFile"],
        }
    ]
    assert callers == []
    assert route == []
    assert definition == [
        {
            "file": "src/lib/map/kmz-parser.ts",
            "line": 5,
            "kind": "function",
            "snippet": "        3| import type { GeoJSONData, GeoJSONFeature } from '@/types/map';\n        4| \n>>>     5| export async function extractIcons(zipFile: JSZip): Promise<Record<string, string>> {\n        6|   const icons: Record<string, string> = {};\n        7| ",
        }
    ]


def test_real_finding_channel_partner_form_import_line_should_keep_import_flow(monkeypatch, tmp_path):
    source = _fixture_text("channel_partner_form/ChannelPartnerForm.imports.tsx")
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
        6,
    )
    imports = mcp_server.find_imports(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
    )
    decorators = mcp_server.find_decorators(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        6,
    )
    identifiers = mcp_server.find_identifiers(
        "69ec5b01",
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        6,
    )

    assert classification["type"] == "production"
    assert extracted["text"] == "// Function not found."
    assert extracted["meta"]["code_on_line"] == (
        "import SettingsForm from '@/app/(dashboard)/channel-partners/components/ChannelPartnerForm/SettingsForm/SettingsForm';"
    )
    assert imports == [
        "import { DialogClose } from '@/app/components/ui/Dialog/Dialog';",
        "import { CloseButton } from '@/app/(dashboard)/components/CloseButton/CloseButton';",
        "import CompanyInformationForm from '@/app/(dashboard)/channel-partners/components/ChannelPartnerForm/CompanyInformationForm/CompanyInformationForm';",
        "import ContactInformationForm from '@/app/(dashboard)/channel-partners/components/ChannelPartnerForm/ContactInformationForm/ContactInformationForm';",
        "import ServicesForm from '@/app/(dashboard)/channel-partners/components/ChannelPartnerForm/ServicesForm/ServicesForm';",
        "import SettingsForm from '@/app/(dashboard)/channel-partners/components/ChannelPartnerForm/SettingsForm/SettingsForm';",
        "import './styles.scss';",
    ]
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}


def test_real_finding_mutations_closing_line_should_keep_non_applicable_flow(monkeypatch, tmp_path):
    source = _fixture_text("mutations/update_prices.ts")
    _write_source_tree(tmp_path, "app/(dashboard)/channel-partners/create/mutations.ts", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts")
    extracted = mcp_server.extract_function("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts", 12)
    imports = mcp_server.find_imports("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts")
    decorators = mcp_server.find_decorators("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts", 12)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/(dashboard)/channel-partners/create/mutations.ts", 12)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "};"
    assert imports == ["import axios from '@/app/axiosInstance';"]
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-connect-ui finding on mutations.ts:138. "
        "trace_identifier_backward still loses updateServiceUrl on the axios.post line."
    ),
)
def test_real_finding_mutations_post_call_should_keep_full_flow(monkeypatch, tmp_path):
    source = _fixture_text("mutations/update_prices.ts")
    _write_source_tree(tmp_path, "app/(dashboard)/channel-partners/create/mutations.ts", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/create/mutations.ts"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 10)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 10)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 10)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 10, "updateServiceUrl")
    callers = mcp_server.find_callers("69ec5b01", file_path, "updatePrices")
    definition = mcp_server.find_definition("69ec5b01", "updatePrices")
    route = mcp_server.find_route_to_function("69ec5b01", "updatePrices")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    await axios.post(updateServiceUrl, data);"
    assert imports == ["import axios from '@/app/axiosInstance';"]
    assert decorators == []
    assert identifiers == {
        "reads": ["axios", "data", "post", "updateServiceUrl"],
        "writes": [],
        "language": "typescript",
    }
    assert trace == [{"line": 3, "code": "export const updatePrices = async (updateServiceUrl: string, data: unknown[]) => {", "writes": ["updatePrices"], "reads": ["data", "updateServiceUrl"]}]
    assert callers == []
    assert definition == [{"file": file_path, "line": 3, "kind": "variable", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_channel_partner_page_resize_call_should_keep_full_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/company_contact/ChannelPartnerPage.tsx")
    _write_source_tree(tmp_path, "app/(dashboard)/channel-partners/[id]/page.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/[id]/page.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 4)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 4)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 4)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 4, "resizeWindow")
    callers = mcp_server.find_callers("69ec5b01", file_path, "ChannelPartnerDetails")
    definition = mcp_server.find_definition("69ec5b01", "ChannelPartnerDetails")
    route = mcp_server.find_route_to_function("69ec5b01", "ChannelPartnerDetails")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\tresizeWindow();"
    assert imports == []
    assert decorators == []
    assert identifiers == {"reads": ["resizeWindow"], "writes": [], "language": "typescript"}
    assert trace == [{"line": 2, "code": "const resizeWindow = () => {};", "writes": ["resizeWindow"], "reads": []}]
    assert callers == []
    assert definition == [{"file": file_path, "line": 1, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_advanced_fov_dependency_destructure_should_keep_full_flow(monkeypatch, tmp_path):
    source = _fixture_text("advanced_fov/AdvancedFOVDialog.dependencies.tsx")
    _write_source_tree(tmp_path, "src/components/map/edit/AdvancedFOVDialog.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AdvancedFOVDialog.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    extracted = mcp_server.extract_function("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 19)
    imports = mcp_server.find_imports("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx")
    decorators = mcp_server.find_decorators("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 19)
    identifiers = mcp_server.find_identifiers("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", 19)
    trace_select_point = mcp_server.trace_identifier_backward(
        "07734951",
        "src/components/map/edit/AdvancedFOVDialog.tsx",
        19,
        "handleSelectPoint",
    )
    callers = mcp_server.find_callers("07734951", "src/components/map/edit/AdvancedFOVDialog.tsx", "AdvancedFOVDialog")
    route = mcp_server.find_route_to_function("07734951", "AdvancedFOVDialog")
    definition = mcp_server.find_definition("07734951", "AdvancedFOVDialog")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    thumbnailCursorPosition,"
    assert imports == ["import React from 'react';"]
    assert decorators == []
    assert identifiers == {
        "reads": [
            "defaultMapCenter",
            "handleSelectPoint",
            "handleThumbnailMapPreview",
            "isCalibrated",
            "pointColors",
            "pointPairs",
            "setPointPairs",
            "thumbnailImageRef",
            "thumbnailRef",
            "transformPoint",
            "useCalibrationPointInteraction",
        ],
        "writes": [],
        "language": "typescript",
    }
    assert trace_select_point == [
        {
            "line": 4,
            "code": "const handleSelectPoint = () => {};",
            "writes": ["handleSelectPoint"],
            "reads": [],
        }
    ]
    assert callers == []
    assert route == []
    assert definition == [
        {
            "file": "src/components/map/edit/AdvancedFOVDialog.tsx",
            "line": 3,
            "kind": "function",
            "snippet": "        1| import React from 'react';\n        2| \n>>>     3| export function AdvancedFOVDialog({ marker, calibrationViewState, thumbnailRef, thumbnailImageRef, pointPairs, isCalibrated, pointColors, transformPoint, setPointPairs }) {\n        4|   const handleSelectPoint = () => {};\n        5|   const handleThumbnailMapPreview = () => {};",
        }
    ]


@pytest.mark.parametrize(
    ("line_number", "expected_code_on_line", "expected_reads"),
    [
        (
            15,
            "    fs.writeFileSync(path.resolve(dest, `${color}.css`), skin.css.toString(), { flag: 'w' });",
            ["color", "css", "dest", "flag", "fs", "path", "resolve", "skin", "toString", "writeFileSync"],
        ),
        (
            17,
            "        fs.writeFileSync(path.resolve(dest, 'skin.css'), skin.css.toString(), { flag: 'w' });",
            ["css", "dest", "flag", "fs", "path", "resolve", "skin", "toString", "writeFileSync"],
        ),
    ],
)
def test_real_finding_build_skins_write_flow_should_keep_non_applicable_navigation(
    monkeypatch, tmp_path, line_number, expected_code_on_line, expected_reads
):
    source = _fixture_text("cloud_portal/build_skins/buildSkins.mjs")
    _write_source_tree(tmp_path, "front_end/buildSkins.mjs", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "buildSkins.mjs"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", "front_end/buildSkins.mjs")
    extracted = mcp_server.extract_function("5a36b942", "front_end/buildSkins.mjs", line_number)
    imports = mcp_server.find_imports("5a36b942", "front_end/buildSkins.mjs")
    decorators = mcp_server.find_decorators("5a36b942", "front_end/buildSkins.mjs", line_number)
    identifiers = mcp_server.find_identifiers("5a36b942", "front_end/buildSkins.mjs", line_number)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_code_on_line
    assert imports == [
        "import fs from 'fs';",
        "import path from 'path';",
        "import { fileURLToPath } from 'url';",
        "import * as sass from 'sass';",
    ]
    assert decorators == []
    assert identifiers == {"reads": expected_reads, "writes": [], "language": "javascript"}


