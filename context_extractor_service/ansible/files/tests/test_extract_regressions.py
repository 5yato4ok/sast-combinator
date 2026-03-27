import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


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


def test_code_on_line_should_not_collapse_cpp_body_to_opening_brace():
    source = """\
void ItemGrabber::grabToImage(QQuickItem* item, const QJSValue& callback)
{
    new ItemGrabberWorker(item, callback);
}
"""
    result = extract_function_from_source(source, "item_grabber.cpp", 2, 200)

    assert result["meta"]["code_on_line"] == "{"

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


def test_code_on_line_should_preserve_outer_multiline_cpp_expression_for_pointer_arithmetic():
    source = """\
int parseBlockSize(const char* const responseBuffer, int responseLength) {
    const auto optionNameLength = (int) std::strlen(kBlockSizeOption);
    const int blockSizeValueLength = responseLength
        - optionNameLength
        - kOptionAckCodeLen
        - kTerminatingBytes;
    const auto blockSizeValuePtr = responseBuffer
        + responseLength
        - (blockSizeValueLength + 1);
    return blockSizeValueLength;
}
"""
    result = extract_function_from_source(source, "simple_tftp_client.cpp", 8, 200)

    assert result["meta"]["code_on_line"] == (
        "responseBuffer\n"
        "        + responseLength\n"
        "        - (blockSizeValueLength + 1)"
    )


def test_code_on_line_should_preserve_multiline_assignment_expression_for_continuation_line():
    source = """\
void describe(PluginInfo* pluginInfo) {
    QString originalPluginInfoDescription;
    if (pluginInfo)
    {
        originalPluginInfoDescription =
            NX_FMT("Original PluginInfo fields: errorCode [%1], statusMessage %2",
                pluginInfo->errorCode, nx::kit::utils::toString(pluginInfo->statusMessage));
    }
}
"""
    result = extract_function_from_source(source, "plugin_manager.cpp", 7, 200)

    assert result["meta"]["code_on_line"] == (
        "originalPluginInfoDescription =\n"
        '            NX_FMT("Original PluginInfo fields: errorCode [%1], statusMessage %2",\n'
        "                pluginInfo->errorCode, nx::kit::utils::toString(pluginInfo->statusMessage))"
    )
