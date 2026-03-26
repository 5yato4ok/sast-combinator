# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

def test_real_finding_use_scroll_listener_should_keep_event_listener_reads(monkeypatch):
    source = """\
const useScroll =
    (ref: RefObject<HTMLElement>): ScrollState => {
        useLayoutEffect(() => {
            const handleScroll = () => {};
            const element = ref.current;
            if (element) {
                element.addEventListener('scroll', handleScroll, { passive: true });
            }
        }, [ref]);
    };
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "useScroll.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "app/hooks/useScroll.ts")
    extracted = mcp_server.extract_function("69ec5b01", "app/hooks/useScroll.ts", 7)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/hooks/useScroll.ts", 7)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "                element.addEventListener('scroll', handleScroll, { passive: true });"
    assert identifiers["reads"] == ["addEventListener", "element", "handleScroll"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "typescript"


def test_real_finding_global_search_dangerously_set_inner_html_should_keep_command_key_reads(monkeypatch):
    source = """\
const GlobalSearchBar = ({ onOpenChange }, forwardedRef) => {
    const getCommandKeySymbol = () => 'Ctrl';
    return (
        <div className={styles.commandKeyCombo}>
            <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />
            <span className={styles.commandKey}>K</span>
        </div>
    );
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "GlobalSearchBar.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("69ec5b01", "app/components/GlobalSearch/GlobalSearchBar.tsx")
    extracted = mcp_server.extract_function("69ec5b01", "app/components/GlobalSearch/GlobalSearchBar.tsx", 5)
    identifiers = mcp_server.find_identifiers("69ec5b01", "app/components/GlobalSearch/GlobalSearchBar.tsx", 5)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "            <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />"
    assert identifiers["language"] == "typescript"
    assert "getCommandKeySymbol" in identifiers["reads"]
    assert "styles" in identifiers["reads"]
    assert "span" in identifiers["reads"]
    assert identifiers["writes"] == []


def test_real_finding_oauth_redirect_assignment_should_keep_href_write(monkeypatch):
    source = """\
function OAuthDebugPage() {
  const handleLogin = () => {
    window.location.href = buildOauthUrl();
  };
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "src/app/debug/oauth/page.tsx")
    extracted = mcp_server.extract_function("07734951", "src/app/debug/oauth/page.tsx", 3)
    identifiers = mcp_server.find_identifiers("07734951", "src/app/debug/oauth/page.tsx", 3)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    window.location.href = buildOauthUrl();"
    assert identifiers["reads"] == ["buildOauthUrl", "location", "window"]
    assert identifiers["writes"] == ["href"]
    assert identifiers["language"] == "typescript"


def test_real_finding_parse_timezone_read_file_should_keep_top_level_identifiers(monkeypatch):
    source = """\
// Read zone.tab file
const zoneTabPath = process.argv[2] || '/Users/valdomar/Downloads/tzdata2025b/zone.tab';
const content = fs.readFileSync(zoneTabPath, 'utf8');

const timezones = {};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "parse-timezone-data.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "scripts/parse-timezone-data.js")
    extracted = mcp_server.extract_function("07734951", "scripts/parse-timezone-data.js", 3)
    identifiers = mcp_server.find_identifiers("07734951", "scripts/parse-timezone-data.js", 3)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "const content = fs.readFileSync(zoneTabPath, 'utf8');"
    assert identifiers["reads"] == ["fs", "readFileSync", "zoneTabPath"]
    assert identifiers["writes"] == ["content"]
    assert identifiers["language"] == "javascript"


def test_real_finding_map_search_signature_should_keep_param_writes(monkeypatch):
    source = """\
const MapSearch = ({
    systems,
    getLoadedDevices,
    findClosestMatchMarkers,
    findClosestMatchMarker,
    setSelectedMarker,
    map,
    t,
    mapboxAccessToken,
    mapCenter,
    mapZoom,
    isImageMap = false,
    systemId = 'unknown',
    deviceCount = 0
}) => {
    const [searchValue, setSearchValue] = useState('');
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "MapSearch.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "src/components/map/MapSearch.tsx")
    extracted = mcp_server.extract_function("07734951", "src/components/map/MapSearch.tsx", 15)
    identifiers = mcp_server.find_identifiers("07734951", "src/components/map/MapSearch.tsx", 15)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "}) => {"
    assert identifiers["language"] == "typescript"
    assert identifiers["reads"] == []
    assert identifiers["writes"] == [
        "deviceCount",
        "findClosestMatchMarker",
        "findClosestMatchMarkers",
        "getLoadedDevices",
        "isImageMap",
        "map",
        "mapCenter",
        "mapZoom",
        "mapboxAccessToken",
        "setSelectedMarker",
        "systemId",
        "systems",
        "t",
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-maps-ui finding on token-storage.ts:42. "
        "The finding line is a single object property, but extract_function still returns "
        "the whole COOKIE_NAMES object in code_on_line instead of the exact property line."
    ),
)
def test_real_finding_token_storage_property_should_keep_exact_object_property_line(monkeypatch):
    source = """\
// Cookie names
const COOKIE_NAMES = {
  ACCESS_TOKEN: 'nx_access_token',
  REFRESH_TOKEN: 'nx_refresh_token',
  SYSTEM_ACCESS_TOKEN: 'nx_system_access_token',
  SYSTEM_REFRESH_TOKEN: 'nx_system_refresh_token',
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "token-storage.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "src/lib/auth/token-storage.ts")
    extracted = mcp_server.extract_function("07734951", "src/lib/auth/token-storage.ts", 3)
    identifiers = mcp_server.find_identifiers("07734951", "src/lib/auth/token-storage.ts", 3)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "  ACCESS_TOKEN: 'nx_access_token',"
    assert identifiers["writes"] == ["COOKIE_NAMES"]
    assert identifiers["reads"] == []
    assert identifiers["language"] == "typescript"


