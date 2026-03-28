from _active_real_finding_audit_helpers import *
def test_active_finding_nxai_sprintf_definition_should_not_resolve_to_call_site(monkeypatch, tmp_path):
    file_path = "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_utils.cpp"
    source = """\
char* nxai_sprintf(size_t initial_size, const char* fmt, ...)
{
    char* return_string = (char*) malloc(initial_size);
    size_t len = vsnprintf(return_string, initial_size, fmt, args);
    if (len >= initial_size)
        return_string = (char*) realloc(return_string, len + 1);
    return return_string;
}

char* nxai_pointer_to_string(void* pointer)
{
    return nxai_sprintf(32, "%p", pointer);
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 5)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 5)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 5)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 5, "len")
    definition = mcp_server.find_definition("9ce90895", "nxai_sprintf")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        return_string = (char*) realloc(return_string, len + 1);"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["len", "realloc", "return_string"]
    assert identifiers["writes"] == ["return_string"]
    assert identifiers["language"] == "cpp"
    assert trace == [{"line": 4, "code": "size_t len = vsnprintf(return_string, initial_size, fmt, args);", "writes": ["len"], "reads": ["args", "fmt", "initial_size", "return_string", "vsnprintf"]}]
    assert definition == [{"file": file_path, "line": 1, "kind": "function"}]




def test_active_finding_csv_visit_definition_should_not_be_polluted_by_unrelated_visit_symbols(
    monkeypatch,
    tmp_path,
):
    target = "open/libs/nx_fusion/src/nx/fusion/serialization/csv_macros.h"
    source = """\
class HeaderVisitor {
private:
    template<class T, class Access, class Member, class Tag>
    bool visit(const T &, const Access &access, const Member *, const Tag &) {
        if(std::is_same<Tag, QnCsv::field_tag>::value) {
            m_stream->writeField(m_prefix + access(name));
        } else {
            QnCsv::serialize_header<Member>(m_prefix + access(name) + '.', m_stream);
        }
        return true;
    }
};
"""
    unrelated_defs = """\
class Compiler {
public:
    virtual bool visit(Node* node);
};
"""
    unrelated_call = """\
bool visitChunks() {
    return visit(m_chunks);
}
"""
    _write_source_tree(tmp_path, target, source)
    _write_source_tree(tmp_path, "artifacts/qt-solutions/qtscriptclassic/src/qscriptcompiler_p.h", unrelated_defs)
    _write_source_tree(tmp_path, "vms/server/nx_vms_server/src/recorder/device_file_catalog.h", unrelated_call)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target)
    extracted = mcp_server.extract_function("9ce90895", target, 6)
    imports = mcp_server.find_imports("9ce90895", target)
    decorators = mcp_server.find_decorators("9ce90895", target, 6)
    identifiers = mcp_server.find_identifiers("9ce90895", target, 6)
    trace = mcp_server.trace_identifier_backward("9ce90895", target, 6, "name")
    callers = mcp_server.find_callers("9ce90895", target, "visit")
    definition = mcp_server.find_definition("9ce90895", "visit")
    route = mcp_server.find_route_to_function("9ce90895", "visit")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "            m_stream->writeField(m_prefix + access(name));"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["access", "m_prefix", "m_stream", "name", "writeField"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
    assert trace == []
    assert callers == []
    assert definition == [{"file": target, "line": 4, "kind": "function"}]
    assert route == []




def test_active_finding_find_callers_should_not_parse_entire_tree_for_generic_symbol_search(monkeypatch, tmp_path):
    target_file = "vms/server/plugins/analytics/nx_ai_manager_plugin/plugin/src/engine.cpp"
    irrelevant_file = "vms/server/plugins/analytics/plugin_aaa/engine.cpp"
    _write_source_tree(
        tmp_path,
        target_file,
        """\
Engine* buildEngine()
{
    return new Engine();
}
""",
    )
    _write_source_tree(
        tmp_path,
        irrelevant_file,
        """\
class Worker
{
public:
    void run()
    {
        worker();
    }
};
""",
    )

    original_parse_required = project_analysis._parse_required
    parse_calls: list[str] = []

    def deterministic_iter_source_files(_source_dir: Path):
        yield Path(irrelevant_file)
        yield Path(target_file)

    def counting_parse_required(source: str, filepath: Path):
        parse_calls.append(str(filepath.relative_to(tmp_path)))
        return original_parse_required(source, filepath)

    monkeypatch.setattr(project_analysis_callers, "_iter_source_files", deterministic_iter_source_files)
    monkeypatch.setattr(project_analysis_callers, "_parse_required", counting_parse_required)

    callers = project_analysis.find_callers(tmp_path, target_file, "Engine")

    assert callers == []
    assert target_file in parse_calls
    assert irrelevant_file not in parse_calls




def test_active_finding_third_party_resource_searcher_should_not_be_classified_as_vendored(
    monkeypatch,
    tmp_path,
):
    file_path = "vms/server/nx_vms_server/src/plugins/resource/third_party/third_party_resource_searcher.cpp"
    source = """\
QnResourcePtr ThirdPartyResourceSearcher::createResource(
    nx::Uuid resourceTypeId, const QnResourceParams& params )
{
    nxcip::CameraInfo cameraInfo;
    strcpy(cameraInfo.url, params.url.toLatin1().constData());
    return {};
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 5)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 5)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 5)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 5, "params")
    definition = mcp_server.find_definition("9ce90895", "createResource")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    strcpy(cameraInfo.url, params.url.toLatin1().constData());"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["cameraInfo", "constData", "params", "strcpy", "toLatin1", "url"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
    assert trace == []
    assert definition == [{"file": file_path, "line": 1, "kind": "function"}]




def test_active_finding_engine_definition_should_prefer_local_plugin_engine(monkeypatch, tmp_path):
    target_cpp = "vms/server/plugins/analytics/nx_ai_manager_plugin/plugin/src/engine.cpp"
    target_header = "vms/server/plugins/analytics/nx_ai_manager_plugin/plugin/src/engine.h"
    source_header = """\
class Engine: public nx::sdk::analytics::Engine
{
public:
    virtual ~Engine() override;

private:
    std::thread socket_listening_thread;
};
"""
    source_cpp = """\
#include "engine.h"

Engine::~Engine()
{
    if (socket_listening_thread.joinable())
        socket_listening_thread.join();
}
"""
    unrelated_header = """\
class Engine: public nx::sdk::RefCountable<nx::sdk::analytics::IEngine>
{
};
"""
    _write_source_tree(tmp_path, target_header, source_header)
    _write_source_tree(tmp_path, target_cpp, source_cpp)
    _write_source_tree(
        tmp_path,
        "vms/server/plugins/analytics/onvif_analytics_plugin/src/nx/vms_server_plugins/analytics/onvif_analytics_plugin/engine.h",
        unrelated_header,
    )
    _write_source_tree(
        tmp_path,
        "vms/server/plugins/cloud_storage/nx_cloud_storage_plugin/src/nx/vms_server_plugins/cloud_storage/nx_cloud/engine.h",
        unrelated_header,
    )
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target_cpp)
    extracted = mcp_server.extract_function("9ce90895", target_cpp, 3)
    imports = mcp_server.find_imports("9ce90895", target_cpp)
    decorators = mcp_server.find_decorators("9ce90895", target_cpp, 3)
    identifiers = mcp_server.find_identifiers("9ce90895", target_cpp, 3)
    trace = mcp_server.trace_identifier_backward("9ce90895", target_cpp, 3, "socket_listening_thread")
    definition = mcp_server.find_definition("9ce90895", "Engine")
    route = mcp_server.find_route_to_function("9ce90895", "Engine")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "Engine::~Engine()"
    assert imports == ['#include "engine.h"']
    assert decorators == []
    assert identifiers["reads"] == ["Engine"]
    assert identifiers["writes"] == ["Engine"]
    assert identifiers["language"] == "cpp"
    assert trace == []
    assert definition == [{"file": target_header, "line": 1, "kind": "class"}]
    assert route == []




def test_active_finding_jwk_definition_should_find_generate_key_pair_for_signing(monkeypatch, tmp_path):
    target_cpp = "open/libs/nx_network/src/nx/network/jose/jwk.cpp"
    target_header = "open/libs/nx_network/src/nx/network/jose/jwk.h"
    source_header = """\
std::expected<KeyPair, std::string /*error*/>
    generateKeyPairForSigning(const Algorithm& algorithm);
"""
    source_cpp = """\
std::expected<KeyPair, std::string /*error*/>
    generateKeyPairForSigning(const Algorithm& /*algorithm*/)
{
    const int keySize = 2048;
    return KeyPair{};
}
"""
    caller_source = """\
void useKeyPair()
{
    const auto kp = generateKeyPairForSigning(Algorithm::RS256);
}
"""
    _write_source_tree(tmp_path, target_header, source_header)
    _write_source_tree(tmp_path, target_cpp, source_cpp)
    _write_source_tree(tmp_path, "open/libs/nx_network/unit_tests/src/jose/jwk_ut.cpp", caller_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target_cpp)
    extracted = mcp_server.extract_function("9ce90895", target_cpp, 4)
    imports = mcp_server.find_imports("9ce90895", target_cpp)
    decorators = mcp_server.find_decorators("9ce90895", target_cpp, 4)
    identifiers = mcp_server.find_identifiers("9ce90895", target_cpp, 4)
    trace = mcp_server.trace_identifier_backward("9ce90895", target_cpp, 4, "keySize")
    callers = mcp_server.find_callers("9ce90895", target_cpp, "generateKeyPairForSigning")
    definition = mcp_server.find_definition("9ce90895", "generateKeyPairForSigning")
    route = mcp_server.find_route_to_function("9ce90895", "generateKeyPairForSigning")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    const int keySize = 2048;"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == []
    assert identifiers["writes"] == ["keySize"]
    assert identifiers["language"] == "cpp"
    assert trace == [{"line": 4, "code": "const int keySize = 2048;", "writes": ["keySize"], "reads": []}]
    assert callers == [{"file": "open/libs/nx_network/unit_tests/src/jose/jwk_ut.cpp", "line": 3, "caller_function": "useKeyPair", "snippet": "        2| {\n>>>     3|     const auto kp = generateKeyPairForSigning(Algorithm::RS256);\n        4| }"}]
    assert definition == [{"file": target_cpp, "line": 2, "kind": "function"}]
    assert route == []




def test_active_finding_stun_token_manager_definition_should_find_qualified_get_token(monkeypatch, tmp_path):
    target_cpp = "cloud/auth/libcloud_db/src/nx/cloud/db/utils/stun_token_manager.cpp"
    target_header = "cloud/auth/libcloud_db/src/nx/cloud/db/utils/stun_token_manager.h"
    source_header = """\
class StunTokenManager
{
public:
    std::tuple<api::Result, TokenData> getToken(
        const std::string& serverName,
        const std::string& sessionId);
};
"""
    source_cpp = """\
std::tuple<api::Result, TokenData> StunTokenManager::getToken(
    const std::string& serverName, const std::string& sessionId)
{
    nx::network::stun::EncryptedBlock encryptedBlock;
    encryptedBlock.keyLength = m_Sha1macKeyLength;
    strcpy((char*) encryptedBlock.macKey, sessionId.substr(0, encryptedBlock.keyLength).c_str());
    return {{api::ResultCode::ok}, {}};
}
"""
    unrelated_rule_helper = """\
template <typename Rule>
QString getToken(const Rule& rule) { return getProp(rule, "auth", "token"); }
"""
    unrelated_java = """\
public static void getToken(int callbackId)
{
}
"""
    caller_source = """\
void issueToken()
{
    auto token = m_stunTokenManager.getToken(serverName, sessionId);
}
"""
    _write_source_tree(tmp_path, target_header, source_header)
    _write_source_tree(tmp_path, target_cpp, source_cpp)
    _write_source_tree(tmp_path, "vms/server/nx_vms_server/unit_tests/api_src/api/rules/encrypt_rule_ut.cpp", unrelated_rule_helper)
    _write_source_tree(tmp_path, "open/vms/client/mobile_client/android.in/src/com/nxvms/mobile/push/firebase/FirebaseTokenHelper.java", unrelated_java)
    _write_source_tree(tmp_path, "cloud/auth/libcloud_db/src/nx/cloud/db/managers/oauth/oauth_manager_jwt.cpp", caller_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target_cpp)
    extracted = mcp_server.extract_function("9ce90895", target_cpp, 6)
    imports = mcp_server.find_imports("9ce90895", target_cpp)
    decorators = mcp_server.find_decorators("9ce90895", target_cpp, 6)
    identifiers = mcp_server.find_identifiers("9ce90895", target_cpp, 6)
    trace = mcp_server.trace_identifier_backward("9ce90895", target_cpp, 6, "encryptedBlock")
    definition = mcp_server.find_definition("9ce90895", "StunTokenManager::getToken")

    assert classification["type"] == "production"
    assert (
        extracted["meta"]["code_on_line"]
        == "    strcpy((char*) encryptedBlock.macKey, sessionId.substr(0, encryptedBlock.keyLength).c_str());"
    )
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["c_str", "encryptedBlock", "keyLength", "macKey", "sessionId", "strcpy", "substr"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
    assert trace == [{"line": 4, "code": "nx::network::stun::EncryptedBlock encryptedBlock;", "writes": ["encryptedBlock"], "reads": []}]
    assert definition == [{"file": target_cpp, "line": 1, "kind": "function"}]




def test_active_finding_missing_demo_data_file_should_raise_file_not_found_for_code_tools(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        classification = mcp_server.classify_file("69ec5b01", "app/(dashboard)/demoData.tsx")

        with pytest.raises(FileNotFoundError, match=r"File not found: app/\(dashboard\)/demoData\.tsx"):
            mcp_server.extract_function("69ec5b01", "app/(dashboard)/demoData.tsx", 97)

        with pytest.raises(FileNotFoundError):
            mcp_server.find_imports("69ec5b01", "app/(dashboard)/demoData.tsx")

        with pytest.raises(FileNotFoundError, match=r"File not found: app/\(dashboard\)/demoData\.tsx"):
            mcp_server.find_decorators("69ec5b01", "app/(dashboard)/demoData.tsx", 97)

        with pytest.raises(FileNotFoundError, match=r"File not found: app/\(dashboard\)/demoData\.tsx"):
            mcp_server.find_identifiers("69ec5b01", "app/(dashboard)/demoData.tsx", 97)

    assert classification["type"] == "production"
