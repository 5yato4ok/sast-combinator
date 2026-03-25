import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: Go code_on_line still expands beyond the target line "
        "for md5.Sum assignment sites."
    ),
)
def test_code_on_line_should_be_exact_go_line_for_real_md5_finding():
    source = """\
package fetcher

import (
    "crypto/md5"
    "encoding/json"
)

type siteInfoWithHash struct {
    Hash [16]byte
    Updated bool
    Parsed any
}

func (s *siteInfoWithHash) UnmarshalJSON(data []byte) error {
    hash := md5.Sum(data)
    if hash == s.Hash {
        return nil
    }
    s.Hash = hash
    s.Updated = true
    return json.Unmarshal(data, &s.Parsed)
}
"""
    result = extract_function_from_source(source, "site_info_reader.go", 15, 200)

    assert result["meta"]["code_on_line"] == "    hash := md5.Sum(data)"


def test_code_on_line_should_not_collapse_to_block_brace_for_typescript():
    source = """\
class ContentComponent {
    ngOnInit(): void {
        if (this.account.is_staff) {
            window.location.href = decodeURIComponent(
                this.route.snapshot.queryParams.next
                    ? this.route.snapshot.queryParams.next
                    : '/admin/',
            );
        }
    }
}
"""
    result = extract_function_from_source(source, "content.component.ts", 4, 200)

    assert result["meta"]["code_on_line"] == "            window.location.href = decodeURIComponent("


def test_extract_function_should_support_tsx_files():
    source = """\
export default function OAuthDebugPage() {
    const nextUrl = "/oauth/callback";

    return <a href={nextUrl}>Continue</a>;
}
"""
    result = extract_function_from_source(source, "page.tsx", 4, 200)

    assert "Unsupported file extension" not in result["text"]
    assert "OAuthDebugPage" in result["text"]

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed repeatedly in live nx-maps-ui findings: on lines inside a multiline "
        "destructured TypeScript signature, code_on_line expands to the whole object pattern."
    ),
)
def test_code_on_line_should_not_expand_to_full_destructured_signature_block():
    source = """\
const MapSearch = ({
  systems,
  getLoadedDevices,
  mapCenter,
  deviceCount = 0,
}) => {
  return systems.length
}
"""
    result = extract_function_from_source(source, "MapSearch.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == "  systems,"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: extract_function returns only the opening brace for "
        "C++ function body lines like ItemGrabber::grabToImage."
    ),
)
def test_code_on_line_should_not_collapse_cpp_body_to_opening_brace():
    source = """\
void ItemGrabber::grabToImage(QQuickItem* item, const QJSValue& callback)
{
    new ItemGrabberWorker(item, callback);
}
"""
    result = extract_function_from_source(source, "item_grabber.cpp", 2, 200)

    assert result["meta"]["code_on_line"] == "    new ItemGrabberWorker(item, callback);"

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live cloud_portal findings: code_on_line can expand from a top-level Python "
        "import line to the whole file preamble plus the next definition."
    ),
)
def test_code_on_line_should_not_expand_to_python_import_preamble():
    source = """\
import argparse
from pathlib import Path

import cssutils
import logging


def read_branding(content):
    return content.replace('$brand_core', 'cyan ')
"""
    result = extract_function_from_source(source, "preprocess.py", 1, 200)

    assert result["meta"]["code_on_line"] == "import argparse"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx-connect-ui findings: multiline JSX opening tags are returned as a "
        "large block in code_on_line instead of the specific target line."
    ),
)
def test_code_on_line_should_not_expand_to_full_multiline_jsx_opening_tag():
    source = """\
function Page() {
  return (
    <Button
      disabled={isDisabledManageServicesButton()}
      variant="primary"
      onClick={() => {
        router.push('/x')
      }}
    >
      Go
    </Button>
  )
}
"""
    result = extract_function_from_source(source, "page.tsx", 3, 200)

    assert result["meta"]["code_on_line"] == "    <Button"

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: code_on_line expands a single C/C++ preprocessor branch "
        "line into the whole conditional block."
    ),
)
def test_code_on_line_should_not_expand_to_cpp_preprocessor_branch_block():
    source = """\
char* nxai_shm_key_to_string(nxai_shm_t shm)
{
#if defined(_MSC_VER)
    char* shm_key_string = (char*) malloc(strlen(shm.key));
    strcpy(shm_key_string, shm.key);
#else
    char* shm_key_string = nxai_sprintf(32, "%d", shm.key);
#endif
    return shm_key_string;
}
"""
    result = extract_function_from_source(source, "nxai_shm_utils.cpp", 3, 200)

    assert result["meta"]["code_on_line"] == "#if defined(_MSC_VER)"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx findings: code_on_line expands a C++ private struct/member block "
        "instead of returning the specific target line."
    ),
)
def test_code_on_line_should_not_expand_to_cpp_private_struct_block():
    source = """\
struct Private {
    LivePreview* const q;
    QnTimeSlider* const slider;

    LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);
    const QmlProperty<qreal> markerLineLength{q->widget(), "markerLineLength"};
};
"""
    result = extract_function_from_source(source, "live_preview.cpp", 1, 200)

    assert result["meta"]["code_on_line"] == "struct Private {"



@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed in live nx-connect-ui mutations.ts findings: extract_function returns the "
        "whole typed arrow signature block in code_on_line instead of the specific parameter line."
    ),
)
def test_code_on_line_should_not_expand_typed_arrow_parameter_signature_block():
    source = """\
export const buildMutation = async (
  updateServiceUrl: string,
  services: Record<string, { price: number | null }>,
  entityType: 'channel_partners' | 'organization'
) => {
  const includeTier = entityType === 'channel_partners';
  return includeTier;
}
"""
    result = extract_function_from_source(source, "mutations.ts", 3, 200)

    assert result["meta"]["code_on_line"] == "  services: Record<string, { price: number | null }>,"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Observed on JSX callback lines like map/page.tsx: extract_function reports "
        "Function not found even though the finding line is inside an inline arrow callback."
    ),
)
def test_extract_function_should_not_lose_inline_jsx_callback_context():
    source = """\
function Page() {
  return <Button onClick={() => {
    router.push('/x')
  }}>Go</Button>
}
"""
    result = extract_function_from_source(source, "page.tsx", 2, 200)

    assert result["text"] != "// Function not found."
    assert "onClick={() => {" in result["text"]
