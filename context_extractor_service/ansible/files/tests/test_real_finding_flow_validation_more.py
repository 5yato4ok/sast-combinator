import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def _stub_resolve_source_dir():
    def _resolver(_pipeline_id: str) -> Path:
        return Path("/tmp")

    return _resolver


def test_real_finding_alert_component_should_keep_definition_and_identifier_payload(monkeypatch):
    source = """\
import InfoIcon from '@/icons/info.svg';

export default function Alert({ type, ...props }: Alert) {
    return (
        <div className={classnames(styles.alert, styles[type])} {...props}>
            {type === 'info' && (
                <div className={styles.icon}>
                    <InfoIcon width={40} height={40} />
                </div>
            )}
            <div className={styles.contentWrapper}>{props.children}</div>
        </div>
    );
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Alert.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "app/components/ui/Alert/Alert.tsx")
    extracted = mcp_server.extract_function("69ec5b01", "app/components/ui/Alert/Alert.tsx", 3)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/components/ui/Alert/Alert.tsx", 3)
    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "export default function Alert({ type, ...props }: Alert) {"
    assert identifiers["reads"] == ["InfoIcon", "alert", "children", "classnames", "contentWrapper", "div", "icon", "styles"]
    assert identifiers["writes"] == ["Alert", "props", "type"]
    assert identifiers["language"] == "typescript"


def test_real_finding_root_layout_tracking_id_should_keep_write_and_definition(monkeypatch):
    source = """\
export default function RootLayoutClient({ children }: { children: ReactNode }) {
    useLayoutEffect(() => {
        const domain = window.location.hostname;
        const trackingID = domain.includes('connect.nxgo.io') ? 'G-ZFX72ZBEEX' : configData?.GOOGLE_ANALYTICS_ID;
        gtagInitialize(trackingID);
    }, []);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "RootLayoutClient.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "app/(external)/RootLayoutClient.tsx")
    extracted = mcp_server.extract_function("69ec5b01", "app/(external)/RootLayoutClient.tsx", 4)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/(external)/RootLayoutClient.tsx", 4)
    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        const trackingID = domain.includes('connect.nxgo.io') ? 'G-ZFX72ZBEEX' : configData?.GOOGLE_ANALYTICS_ID;"
    assert identifiers["reads"] == ["GOOGLE_ANALYTICS_ID", "configData", "domain", "includes"]
    assert identifiers["writes"] == ["trackingID"]
    assert identifiers["language"] == "typescript"


def test_real_finding_fetch_redirect_handler_should_keep_network_identifiers(monkeypatch):
    source = """\
function fetch(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : require('http');
    protocol.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        const redirectUrl = new URL(res.headers.location, url).href;
        console.log(`  → Following redirect to ${redirectUrl}`);
        return resolve(fetch(redirectUrl, maxRedirects - 1));
      }
    });
  });
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "scripts/generate-customization.js")
    extracted = mcp_server.extract_function("07734951", "scripts/generate-customization.js", 4)
    identifiers = mcp_server.find_identifiers("07734951", "scripts/generate-customization.js", 4)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    protocol.get(url, (res) => {"
    assert identifiers["language"] == "javascript"
    assert "protocol" in identifiers["reads"]
    assert "get" in identifiers["reads"]
    assert "url" in identifiers["reads"]
    assert "res" in identifiers["reads"]
    assert identifiers["writes"] == []


def test_real_finding_write_file_sync_should_keep_fs_and_json_reads(monkeypatch):
    source = """\
async function main() {
  const outputPath = path.join(OUTPUT_DIR, `${customization}.json`);
  fs.writeFileSync(outputPath, JSON.stringify(config, null, 2), 'utf8');
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "scripts/generate-customization.js")
    extracted = mcp_server.extract_function("07734951", "scripts/generate-customization.js", 3)
    identifiers = mcp_server.find_identifiers("07734951", "scripts/generate-customization.js", 3)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "  fs.writeFileSync(outputPath, JSON.stringify(config, null, 2), 'utf8');"
    assert identifiers["reads"] == ["JSON", "config", "fs", "outputPath", "stringify", "writeFileSync"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "javascript"
