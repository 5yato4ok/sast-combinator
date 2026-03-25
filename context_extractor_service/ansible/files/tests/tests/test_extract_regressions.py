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
