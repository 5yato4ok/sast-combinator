import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor import project_analysis
from context_extractor.project_analysis import callers as project_analysis_callers
from context_extractor.config_analysis import extract_config_block, find_related_configs
from context_extractor.extract import extract_function_from_source


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


def _assert_trace_codes(trace: list[dict], expected_codes: list[str]) -> None:
    assert [step["code"] for step in trace] == expected_codes
    assert all(step["line"] >= 1 for step in trace)


def test_active_finding_top_level_typescript_secret_should_keep_property_line_and_identifier_context(
    monkeypatch,
):
    source = """\
import { LogLevel } from '@/lib/logging/logger';
import packageJson from '../package.json';

function loadBrandConfig() {
  return { customization: 'default' };
}

export const config: Config = {
  site: {
    brand: loadBrandConfig(),
    url: typeof window !== 'undefined' ? window.location.origin : '',
  },
  logLevel: (process.env.NEXT_PUBLIC_LOG_LEVEL as keyof typeof LogLevel) ?? LogLevel.ALL,
  cloudUrl: { prod: 'https://{cloudSystemId}.relay.vmsproxy.com' },
  mapboxApiKey: 'pk.eyJ1IjoibW1hbG9uZS1ueCIsImEiOiJjbWdnOTRnMTkwZHQxMmxzY3duZDVyd3VzIn0.9aIxfps5azwN9XcX4BsY3Q',
  googleAnalyticsMeasurementId: 'G-3KQ976MRQ0',
  version: packageJson.version,
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "config.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("07734951", "src/config.ts")
    extracted = extract_function_from_source(source, "config.ts", 15, 200)
    identifiers = mcp_server.find_identifiers("07734951", "src/config.ts", 15)

    assert classification["type"] == "production"
    assert extracted["text"] == "// Function not found."
    assert (
        extracted["meta"]["code_on_line"]
        == "  mapboxApiKey: 'pk.eyJ1IjoibW1hbG9uZS1ueCIsImEiOiJjbWdnOTRnMTkwZHQxMmxzY3duZDVyd3VzIn0.9aIxfps5azwN9XcX4BsY3Q',"
    )
    assert identifiers["writes"] == ["config"]
    assert identifiers["language"] == "typescript"
    assert {"ALL", "LogLevel", "NEXT_PUBLIC_LOG_LEVEL", "loadBrandConfig", "packageJson", "process", "window"} <= set(
        identifiers["reads"]
    )


AMS_SERVICE_CRASH_RECEIVER_DOCKERFILE = """\
FROM ubuntu:latest

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \\
    apt-get install -y --no-install-recommends openssh-server vim && \\
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -d /home/sftpuser -s /usr/sbin/nologin sftpuser && \\
    mkdir -p /home/sftpuser/.ssh && \\
    chown sftpuser:sftpuser /home/sftpuser/.ssh && \\
    chmod 700 /home/sftpuser/.ssh

COPY crash_receiver_key.pub /home/sftpuser/.ssh/authorized_keys

RUN chmod 600 /home/sftpuser/.ssh/authorized_keys && \\
    chown sftpuser:sftpuser /home/sftpuser/.ssh/authorized_keys

RUN mkdir -p /home/sftpuser/sftp/upload && \\
    chown root:root /home/sftpuser /home/sftpuser/sftp && \\
    chmod 755 /home/sftpuser /home/sftpuser/sftp && \\
    chown sftpuser:sftpuser /home/sftpuser/sftp/upload && \\
    chmod 755 /home/sftpuser/sftp/upload

RUN mkdir -p /run/sshd && \\
    echo "Match User sftpuser" >> /etc/ssh/sshd_config && \\
    echo "    ChrootDirectory /home/sftpuser/sftp/" >> /etc/ssh/sshd_config && \\
    echo "    ForceCommand internal-sftp" >> /etc/ssh/sshd_config && \\
    echo "    PasswordAuthentication no" >> /etc/ssh/sshd_config && \\
    echo "    PubkeyAuthentication yes" >> /etc/ssh/sshd_config && \\
    echo "    PermitTunnel no" >> /etc/ssh/sshd_config && \\
    echo "    AllowAgentForwarding no" >> /etc/ssh/sshd_config && \\
    echo "    AllowTcpForwarding no" >> /etc/ssh/sshd_config && \\
    echo "    X11Forwarding no" >> /etc/ssh/sshd_config

EXPOSE 22

# chown for case when folder is mounted
CMD [ "/usr/bin/chown", "sftpuser:sftpuser", "/home/sftpuser/sftp/upload" ]
CMD [ "/usr/sbin/sshd", "-D", "-e" ]
"""


def test_active_finding_extract_config_block_should_keep_final_docker_cmd_instruction():
    block = extract_config_block(
        AMS_SERVICE_CRASH_RECEIVER_DOCKERFILE,
        Path("cloud/ams/deploy/ams_service_crash_receiver/Dockerfile"),
        41,
    )

    assert block["block_text"] == 'CMD [ "/usr/sbin/sshd", "-D", "-e" ]'
    assert block["start_line"] == 41
    assert block["end_line"] == 41


def test_active_finding_extract_config_block_should_keep_real_entrypoint_instruction():
    source = """\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
ARG PKG_PATH=stage/analytics_server
COPY $PKG_PATH /pkg
COPY entrypoint.sh /pkg/
WORKDIR "/pkg"
ENTRYPOINT ["./entrypoint.sh"]
"""

    block = extract_config_block(
        source,
        Path("cloud/ams/deploy/ams_service/Dockerfile"),
        7,
    )

    assert block["block_text"] == 'ENTRYPOINT ["./entrypoint.sh"]'
    assert block["block_type"] == "entrypoint_instruction"
    assert block["key_path"] == "ENTRYPOINT"
    assert block["start_line"] == 7
    assert block["end_line"] == 7


def test_active_finding_related_configs_should_ignore_unrelated_same_basename_dockerfiles():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        target_dir = root / "cloud" / "ams" / "deploy" / "ams_service_crash_receiver"
        target_dir.mkdir(parents=True)
        (target_dir / "Dockerfile").write_text(AMS_SERVICE_CRASH_RECEIVER_DOCKERFILE, encoding="utf-8")
        (target_dir / "docker-compose.yml").write_text(
            "services:\n"
            "  crash-receiver:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
            encoding="utf-8",
        )

        unrelated_compose_dir = root / "open" / "artifacts" / "coturn" / "src" / "docker"
        unrelated_compose_dir.mkdir(parents=True)
        (unrelated_compose_dir / "docker-compose-all.yml").write_text(
            "services:\n"
            "  coturn:\n"
            "    build:\n"
            "      context: coturn/debian\n"
            "      dockerfile: Dockerfile\n",
            encoding="utf-8",
        )
        unrelated_docker_dir = unrelated_compose_dir / "coturn" / "debian"
        unrelated_docker_dir.mkdir(parents=True)
        (unrelated_docker_dir / "Dockerfile").write_text("FROM debian:stable\n", encoding="utf-8")

        (root / "cloud" / "ams" / "deploy" / "ams_service").mkdir(parents=True)
        (root / "cloud" / "ams" / "deploy" / "ams_service" / "Dockerfile").write_text(
            "FROM ubuntu:latest\n",
            encoding="utf-8",
        )

        related = find_related_configs(root, "cloud/ams/deploy/ams_service_crash_receiver/Dockerfile")

    assert related == [{"file": "cloud/ams/deploy/ams_service_crash_receiver/docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_active_finding_related_configs_should_not_link_sibling_service_dockerfile():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        target_dir = root / "cloud" / "ams" / "deploy" / "ams_service_crash_receiver"
        target_dir.mkdir(parents=True)
        (target_dir / "Dockerfile").write_text(AMS_SERVICE_CRASH_RECEIVER_DOCKERFILE, encoding="utf-8")
        (target_dir / "docker-compose.yml").write_text(
            "services:\n"
            "  crash-receiver:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
            encoding="utf-8",
        )

        sibling_dir = root / "cloud" / "ams" / "deploy" / "ams_service"
        sibling_dir.mkdir(parents=True)
        (sibling_dir / "Dockerfile").write_text("ENTRYPOINT [\"./entrypoint.sh\"]\n", encoding="utf-8")

        related = find_related_configs(root, "cloud/ams/deploy/ams_service_crash_receiver/Dockerfile")

    assert related == [{"file": "cloud/ams/deploy/ams_service_crash_receiver/docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_active_finding_related_configs_should_not_link_sibling_service_compose():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ams_service = root / "cloud" / "ams" / "deploy" / "ams_service"
        ams_service.mkdir(parents=True)
        (ams_service / "Dockerfile").write_text('ENTRYPOINT ["./entrypoint.sh"]\n', encoding="utf-8")

        sibling = root / "cloud" / "ams" / "deploy" / "ams_service_crash_receiver"
        sibling.mkdir(parents=True)
        (sibling / "docker-compose.yml").write_text(
            "services:\n"
            "  ams_service_crash_receiver:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
            encoding="utf-8",
        )
        (sibling / "Dockerfile").write_text("FROM ubuntu:latest\n", encoding="utf-8")

        related = find_related_configs(root, "cloud/ams/deploy/ams_service/Dockerfile")

    assert related == []


def test_active_finding_extract_config_block_should_keep_yaml_secret_pair():
    source = """\
bucket: 'cloud-portal'

smtp:
    host: 'email-smtp.us-east-1.amazonaws.com'
    user: 'AKIAJ6MLW7ZT7WXXXOIA'
    password: 'AlYDnddPk8mWorQFVogh8sqkQX6Nv01JwxxfMoYJAFeC'
    port: 587
"""

    block = extract_config_block(source, Path("cloud/cloud/cloud_portal.yaml"), 5)

    assert block["block_text"] == "user: 'AKIAJ6MLW7ZT7WXXXOIA'"
    assert block["block_type"] == "block_mapping_pair"
    assert block["key_path"] == "smtp.user"
    assert block["start_line"] == 5
    assert block["end_line"] == 5


def test_active_finding_native_lambda_trace_should_resolve_local_null_binding(monkeypatch, tmp_path):
    file_path = "vms/libs/nx_analytics_db/src/nx/analytics/db/analytics_db_controller.cpp"
    source = """\
#include "analytics_db_controller.h"
#include <nx/analytics/db/attributes_dao/sqlite_attributes_dao.h>

void DbController::applyOldSqliteScripts()
{
    auto migrateTextIndex = [](nx::sql::QueryContext* queryContext)
    {
        AbstractObjectTypeDictionary* fakeDict = nullptr;
        SqliteAttributesDao attrDao(*fakeDict);
        auto query = queryContext->connection()->createQuery();
        query->prepare("SELECT id, content from unique_attributes");
    };
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 9)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 9)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 9)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 9, "fakeDict")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        SqliteAttributesDao attrDao(*fakeDict);"
    assert imports == [
        '#include "analytics_db_controller.h"',
        "#include <nx/analytics/db/attributes_dao/sqlite_attributes_dao.h>",
    ]
    assert decorators == []
    assert identifiers["reads"] == ["fakeDict"]
    assert identifiers["writes"] == ["attrDao"]
    assert identifiers["language"] == "cpp"
    assert trace == [{"line": 8, "code": "AbstractObjectTypeDictionary* fakeDict = nullptr;", "writes": ["fakeDict"], "reads": []}]


def test_active_finding_debug_handler_trace_should_step_back_to_pointer_declaration(monkeypatch, tmp_path):
    file_path = "vms/server/nx_vms_server/src/rest/handlers/debug_handler.cpp"
    source = """\
#include "debug_handler.h"

void QnDebugHandler::afterExecute()
{
    int* const crashPtr = nullptr;
    *crashPtr = 0;
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 6)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 6)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 6)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 6, "crashPtr")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    *crashPtr = 0;"
    assert imports == ['#include "debug_handler.h"']
    assert decorators == []
    assert identifiers["reads"] == []
    assert identifiers["writes"] == ["crashPtr"]
    assert identifiers["language"] == "cpp"
    assert trace == [{"line": 5, "code": "int* const crashPtr = nullptr;", "writes": ["crashPtr"], "reads": []}]


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


def test_active_finding_image_library_discovery_manager_should_keep_parameter_and_local_path_context(
    monkeypatch,
    tmp_path,
):
    file_path = "open/vms/server/plugins/device/image_library_plugin/src/discovery_manager.cpp"
    source = """\
int DiscoveryManager::checkHostAddress(
    nxcip::CameraInfo* cameraInfo,
    const char* address,
    const char* /*login*/,
    const char* /*password*/ )
{
    const std::string path = fileUrlToPath(address);
    strcpy(cameraInfo->url, address);
    strcpy(cameraInfo->uid, path.c_str());
    strcpy(cameraInfo->modelName, path.c_str());
    return 1;
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted_url = mcp_server.extract_function("9ce90895", file_path, 8)
    identifiers_url = mcp_server.find_identifiers("9ce90895", file_path, 8)
    trace_address = mcp_server.trace_identifier_backward("9ce90895", file_path, 8, "address")
    extracted_uid = mcp_server.extract_function("9ce90895", file_path, 9)
    identifiers_uid = mcp_server.find_identifiers("9ce90895", file_path, 9)
    trace_path = mcp_server.trace_identifier_backward("9ce90895", file_path, 9, "path")
    extracted_model = mcp_server.extract_function("9ce90895", file_path, 10)
    identifiers_model = mcp_server.find_identifiers("9ce90895", file_path, 10)

    assert classification["type"] == "production"
    assert extracted_url["meta"]["code_on_line"] == "    strcpy(cameraInfo->url, address);"
    assert identifiers_url["reads"] == ["address", "cameraInfo", "strcpy", "url"]
    assert identifiers_url["writes"] == []
    assert identifiers_url["language"] == "cpp"
    assert trace_address == []
    assert extracted_uid["meta"]["code_on_line"] == "    strcpy(cameraInfo->uid, path.c_str());"
    assert identifiers_uid["reads"] == ["c_str", "cameraInfo", "path", "strcpy", "uid"]
    assert identifiers_uid["writes"] == []
    assert trace_path == [{"line": 7, "code": "const std::string path = fileUrlToPath(address);", "writes": ["path"], "reads": ["address", "fileUrlToPath"]}]
    assert extracted_model["meta"]["code_on_line"] == "    strcpy(cameraInfo->modelName, path.c_str());"
    assert identifiers_model["reads"] == ["c_str", "cameraInfo", "modelName", "path", "strcpy"]
    assert identifiers_model["writes"] == []


def test_active_finding_soap_wrapper_should_keep_header_copy_context(monkeypatch, tmp_path):
    file_path = "vms/server/nx_vms_server/src/plugins/resource/onvif/soap_wrapper.cpp"
    source = """\
void PullPointSubscriptionWrapper::createPullMessagesRequestHeader(
    std::string& subscriptionId, std::string& subscriptionReference)
{
    char* SubscriptionIdBuf = (char*)malloc(subscriptionId.size() + 1);
    strcpy(SubscriptionIdBuf, subscriptionId.c_str());

    char* toBuf = (char*)malloc(subscriptionReference.size() + 1);
    strcpy(toBuf, subscriptionReference.c_str());
}

void PullPointSubscriptionWrapper::addMessageIdToHeader()
{
    std::string messageId{nx::Uuid::createUuid().toSimpleStdString()};
    char* messageIdBuf = (char*)malloc(messageId.size() + 1);
    strcpy(messageIdBuf, messageId.c_str());
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted_subscription = mcp_server.extract_function("9ce90895", file_path, 5)
    identifiers_subscription = mcp_server.find_identifiers("9ce90895", file_path, 5)
    trace_subscription = mcp_server.trace_identifier_backward("9ce90895", file_path, 5, "subscriptionId")
    extracted_reference = mcp_server.extract_function("9ce90895", file_path, 8)
    identifiers_reference = mcp_server.find_identifiers("9ce90895", file_path, 8)
    trace_reference = mcp_server.trace_identifier_backward("9ce90895", file_path, 8, "subscriptionReference")
    extracted_message_id = mcp_server.extract_function("9ce90895", file_path, 15)
    identifiers_message_id = mcp_server.find_identifiers("9ce90895", file_path, 15)
    trace_message_id = mcp_server.trace_identifier_backward("9ce90895", file_path, 15, "messageId")

    assert classification["type"] == "production"
    assert extracted_subscription["meta"]["code_on_line"] == "    strcpy(SubscriptionIdBuf, subscriptionId.c_str());"
    assert identifiers_subscription["reads"] == ["SubscriptionIdBuf", "c_str", "strcpy", "subscriptionId"]
    assert identifiers_subscription["writes"] == []
    assert trace_subscription == []
    assert extracted_reference["meta"]["code_on_line"] == "    strcpy(toBuf, subscriptionReference.c_str());"
    assert identifiers_reference["reads"] == ["c_str", "strcpy", "subscriptionReference", "toBuf"]
    assert identifiers_reference["writes"] == []
    assert trace_reference == []
    assert extracted_message_id["meta"]["code_on_line"] == "    strcpy(messageIdBuf, messageId.c_str());"
    assert identifiers_message_id["reads"] == ["c_str", "messageId", "messageIdBuf", "strcpy"]
    assert identifiers_message_id["writes"] == []
    assert trace_message_id == [{"line": 13, "code": "std::string messageId{nx::Uuid::createUuid().toSimpleStdString()};", "writes": ["messageId"], "reads": ["createUuid", "toSimpleStdString"]}]


def test_active_finding_member_string_copies_should_keep_object_context(monkeypatch, tmp_path):
    media_encoder_path = "open/vms/server/plugins/device/image_library_plugin/src/media_encoder.cpp"
    soap_server_path = "vms/server/nx_vms_server/src/soap/soapserver.cpp"
    media_encoder_source = """\
int MediaEncoder::getMediaUrl(char* urlBuf) const
{
    strcpy(urlBuf, m_cameraManager->info().url);
    return nxcip::NX_NO_ERROR;
}
"""
    soap_server_source = """\
bool QnSoapServer::bind()
{
    strcpy(m_service->soap->endpoint, m_path.c_str());
    strcpy(m_service->soap->path, m_path.c_str());
    return true;
}
"""
    _write_source_tree(tmp_path, media_encoder_path, media_encoder_source)
    _write_source_tree(tmp_path, soap_server_path, soap_server_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    media_classification = mcp_server.classify_file("9ce90895", media_encoder_path)
    media_extracted = mcp_server.extract_function("9ce90895", media_encoder_path, 3)
    media_identifiers = mcp_server.find_identifiers("9ce90895", media_encoder_path, 3)
    media_trace = mcp_server.trace_identifier_backward("9ce90895", media_encoder_path, 3, "m_cameraManager")

    soap_classification = mcp_server.classify_file("9ce90895", soap_server_path)
    soap_endpoint_extracted = mcp_server.extract_function("9ce90895", soap_server_path, 3)
    soap_endpoint_identifiers = mcp_server.find_identifiers("9ce90895", soap_server_path, 3)
    soap_path_extracted = mcp_server.extract_function("9ce90895", soap_server_path, 4)
    soap_path_identifiers = mcp_server.find_identifiers("9ce90895", soap_server_path, 4)
    soap_trace = mcp_server.trace_identifier_backward("9ce90895", soap_server_path, 4, "m_path")

    assert media_classification["type"] == "production"
    assert media_extracted["meta"]["code_on_line"] == "    strcpy(urlBuf, m_cameraManager->info().url);"
    assert media_identifiers["reads"] == ["info", "m_cameraManager", "strcpy", "url", "urlBuf"]
    assert media_identifiers["writes"] == []
    assert media_trace == []

    assert soap_classification["type"] == "production"
    assert soap_endpoint_extracted["meta"]["code_on_line"] == "    strcpy(m_service->soap->endpoint, m_path.c_str());"
    assert soap_endpoint_identifiers["reads"] == ["c_str", "endpoint", "m_path", "m_service", "soap", "strcpy"]
    assert soap_endpoint_identifiers["writes"] == []
    assert soap_path_extracted["meta"]["code_on_line"] == "    strcpy(m_service->soap->path, m_path.c_str());"
    assert soap_path_identifiers["reads"] == ["c_str", "m_path", "m_service", "path", "soap", "strcpy"]
    assert soap_path_identifiers["writes"] == []
    assert soap_trace == []


def test_active_finding_camera_manager_param_copies_should_keep_url_member_context(monkeypatch, tmp_path):
    multicast_path = "vms/server/plugins/device/generic_multicast_plugin/src/generic_multicast_camera_manager.cpp"
    rtsp_path = "vms/server/plugins/device/generic_rtsp_plugin/src/generic_rtsp_camera_manager.cpp"
    multicast_source = """\
int GenericMulticastCameraManager::getParamValue(const char* paramName, char* valueBuf, int* valueBufSize) const
{
    *valueBufSize = requiredBufSize;
    strcpy(valueBuf, m_info.url);
    return nxcip::NX_NO_ERROR;
}
"""
    rtsp_source = """\
int GenericRTSPCameraManager::getParamValue(const char* paramName, char* valueBuf, int* valueBufSize) const
{
    *valueBufSize = requiredBufSize;
    strcpy(valueBuf, m_info.url);
    return nxcip::NX_NO_ERROR;
}
"""
    _write_source_tree(tmp_path, multicast_path, multicast_source)
    _write_source_tree(tmp_path, rtsp_path, rtsp_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    multicast_classification = mcp_server.classify_file("9ce90895", multicast_path)
    multicast_extracted = mcp_server.extract_function("9ce90895", multicast_path, 4)
    multicast_identifiers = mcp_server.find_identifiers("9ce90895", multicast_path, 4)
    multicast_trace = mcp_server.trace_identifier_backward("9ce90895", multicast_path, 4, "m_info")

    rtsp_classification = mcp_server.classify_file("9ce90895", rtsp_path)
    rtsp_extracted = mcp_server.extract_function("9ce90895", rtsp_path, 4)
    rtsp_identifiers = mcp_server.find_identifiers("9ce90895", rtsp_path, 4)
    rtsp_trace = mcp_server.trace_identifier_backward("9ce90895", rtsp_path, 4, "m_info")

    assert multicast_classification["type"] == "production"
    assert multicast_extracted["meta"]["code_on_line"] == "    strcpy(valueBuf, m_info.url);"
    assert multicast_identifiers["reads"] == ["m_info", "strcpy", "url", "valueBuf"]
    assert multicast_identifiers["writes"] == []
    assert multicast_trace == []

    assert rtsp_classification["type"] == "production"
    assert rtsp_extracted["meta"]["code_on_line"] == "    strcpy(valueBuf, m_info.url);"
    assert rtsp_identifiers["reads"] == ["m_info", "strcpy", "url", "valueBuf"]
    assert rtsp_identifiers["writes"] == []
    assert rtsp_trace == []


def test_active_finding_rtsp_and_mjpeg_media_url_copies_should_keep_branch_context(monkeypatch, tmp_path):
    rtsp_path = "vms/server/plugins/device/generic_rtsp_plugin/src/generic_rtsp_media_encoder.cpp"
    mjpeg_path = "vms/server/plugins/device/mjpeg_link_plugin/src/media_encoder.cpp"
    rtsp_source = """\
int GenericRTSPMediaEncoder::getMediaUrl(char* urlBuf) const
{
    urlBuf[0] = 0;
    if (m_mediaUrl[0])
        strcpy(urlBuf, m_mediaUrl);
    else if (m_encoderIndex == 0)
        strcpy(urlBuf, m_cameraManager->info().url);
    return nxcip::NX_NO_ERROR;
}
"""
    mjpeg_source = """\
int MediaEncoder::getMediaUrl(char* urlBuf) const
{
    urlBuf[0] = 0;
    strcpy(urlBuf, getMediaUrlInternal().toUtf8().constData());
    return nxcip::NX_NO_ERROR;
}
"""
    _write_source_tree(tmp_path, rtsp_path, rtsp_source)
    _write_source_tree(tmp_path, mjpeg_path, mjpeg_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    rtsp_classification = mcp_server.classify_file("9ce90895", rtsp_path)
    rtsp_media_extracted = mcp_server.extract_function("9ce90895", rtsp_path, 5)
    rtsp_media_identifiers = mcp_server.find_identifiers("9ce90895", rtsp_path, 5)
    rtsp_media_trace = mcp_server.trace_identifier_backward("9ce90895", rtsp_path, 5, "m_mediaUrl")
    rtsp_manager_extracted = mcp_server.extract_function("9ce90895", rtsp_path, 7)
    rtsp_manager_identifiers = mcp_server.find_identifiers("9ce90895", rtsp_path, 7)
    rtsp_manager_trace = mcp_server.trace_identifier_backward("9ce90895", rtsp_path, 7, "m_cameraManager")

    mjpeg_classification = mcp_server.classify_file("9ce90895", mjpeg_path)
    mjpeg_extracted = mcp_server.extract_function("9ce90895", mjpeg_path, 4)
    mjpeg_identifiers = mcp_server.find_identifiers("9ce90895", mjpeg_path, 4)
    mjpeg_trace = mcp_server.trace_identifier_backward("9ce90895", mjpeg_path, 4, "getMediaUrlInternal")

    assert rtsp_classification["type"] == "production"
    assert rtsp_media_extracted["meta"]["code_on_line"] == "        strcpy(urlBuf, m_mediaUrl);"
    assert rtsp_media_identifiers["reads"] == ["info", "m_cameraManager", "m_encoderIndex", "m_mediaUrl", "strcpy", "url", "urlBuf"]
    assert rtsp_media_identifiers["writes"] == []
    assert rtsp_media_trace == []
    assert rtsp_manager_extracted["meta"]["code_on_line"] == "        strcpy(urlBuf, m_cameraManager->info().url);"
    assert rtsp_manager_identifiers["reads"] == ["info", "m_cameraManager", "m_encoderIndex", "m_mediaUrl", "strcpy", "url", "urlBuf"]
    assert rtsp_manager_identifiers["writes"] == []
    assert rtsp_manager_trace == []

    assert mjpeg_classification["type"] == "production"
    assert mjpeg_extracted["meta"]["code_on_line"] == "    strcpy(urlBuf, getMediaUrlInternal().toUtf8().constData());"
    assert mjpeg_identifiers["reads"] == ["constData", "getMediaUrlInternal", "strcpy", "toUtf8", "urlBuf"]
    assert mjpeg_identifiers["writes"] == []
    assert mjpeg_trace == []


def test_active_finding_systemexcept_win_should_keep_sprintf_argument_context(monkeypatch, tmp_path):
    file_path = "open/libs/nx_utils/src/nx/utils/crash_dump/systemexcept_win.cpp"
    source = """\
static bool GetCrashPrefix(char* sCrashPrefix)
{
    char sProgramName[MAX_SYMBOL_SIZE];
    if (!GetProgramName(sProgramName))
        return false;

    return sprintf(sCrashPrefix, "%s_%s", sProgramName, fullVersionId.c_str());
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 7)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 7)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 7)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 7, "fullVersionId")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == '    return sprintf(sCrashPrefix, "%s_%s", sProgramName, fullVersionId.c_str());'
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["c_str", "fullVersionId", "sCrashPrefix", "sProgramName", "sprintf"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
    assert trace == []


def test_active_finding_systemexcept_win_should_keep_vsprintf_buffer_context(monkeypatch, tmp_path):
    file_path = "open/libs/nx_utils/src/nx/utils/crash_dump/systemexcept_win.cpp"
    source = """\
static
void FWriteFile(HANDLE hFile, const char* fmt, ...)
{
    va_list vl;
    va_start(vl, fmt);
    char pBuffer[1024];
    DWORD dwWritten;
    int iRet = vsprintf(pBuffer, fmt, vl);
    va_end(vl);
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 8)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 8)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 8)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 8, "fmt")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    int iRet = vsprintf(pBuffer, fmt, vl);"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["fmt", "pBuffer", "vl", "vsprintf"]
    assert identifiers["writes"] == ["iRet"]
    assert identifiers["language"] == "cpp"
    assert trace == []


def test_active_finding_datetime_should_keep_sscanf_argument_context(monkeypatch, tmp_path):
    file_path = "open/libs/nx_utils/src/nx/utils/datetime.cpp"
    source = """\
QDateTime parseRfc1123Date(std::string_view str)
{
    static constexpr const char* kTemplate = "%3s, %d %3s %d %d:%d:%d";
    char weekday[4], monthStr[4];
    int day, year, hour, min, sec;
    if (sscanf(str.data(), kTemplate, weekday, &day, monthStr, &year, &hour, &min, &sec) != 7)
        return QDateTime();
    return QDateTime();
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 6)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 6)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 6)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 6, "str")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    if (sscanf(str.data(), kTemplate, weekday, &day, monthStr, &year, &hour, &min, &sec) != 7)"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["QDateTime", "data", "day", "hour", "kTemplate", "min", "monthStr", "sec", "sscanf", "str", "weekday", "year"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "cpp"
    assert trace == []


def test_active_finding_go_handlers_should_keep_md5_userid_context(monkeypatch, tmp_path):
    file_path = "cloud/vms_db/vms_fetch_service/internal/provider/handlers.go"
    source = """\
func (h *handlers) processRequest(user string) {
    userId := uuid.UUID(md5.Sum([]byte(user)))
    _ = userId
}

func (p *permissions) processPermissionsRequest(user string, org dao.OrgId, sites []string) any {
    for _, info := range p.GetUserAccess(uuid.UUID(md5.Sum([]byte(user))), "", org, sites).users {
        _ = info
    }
    return nil
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted_process = mcp_server.extract_function("9ce90895", file_path, 2)
    identifiers_process = mcp_server.find_identifiers("9ce90895", file_path, 2)
    trace_process = mcp_server.trace_identifier_backward("9ce90895", file_path, 2, "user")
    extracted_permissions = mcp_server.extract_function("9ce90895", file_path, 7)
    identifiers_permissions = mcp_server.find_identifiers("9ce90895", file_path, 7)
    trace_permissions = mcp_server.trace_identifier_backward("9ce90895", file_path, 7, "user")

    assert classification["type"] == "production"
    assert extracted_process["meta"]["code_on_line"] == "    userId := uuid.UUID(md5.Sum([]byte(user)))"
    assert identifiers_process["reads"] == ["Sum", "UUID", "md5", "user", "uuid"]
    assert identifiers_process["writes"] == ["userId"]
    assert identifiers_process["language"] == "go"
    assert trace_process == []
    assert extracted_permissions["meta"]["code_on_line"] == '    for _, info := range p.GetUserAccess(uuid.UUID(md5.Sum([]byte(user))), "", org, sites).users {'
    assert {"GetUserAccess", "Sum", "UUID", "md5", "org", "p", "sites", "user", "users", "uuid"} <= set(
        identifiers_permissions["reads"]
    )
    assert identifiers_permissions["writes"] == []
    assert identifiers_permissions["language"] == "go"
    assert trace_permissions == []


def test_active_finding_go_noncall_lines_should_keep_exact_code_on_line(monkeypatch, tmp_path):
    model_path = "cloud/storage/nx_chunk_log_service/internal/model/chmodel/model.go"
    model_source = """\
func New(cfg *config.Dao) (*Model, error) {
    // E.g. clickhouse://user:pass@host1:9000,host2:9000/db?dial_timeout=50ms&max_execution_time=5
    options, err := clickhouse.ParseDSN(cfg.DbUrl)
    return nil, err
}
"""
    config_path = "cloud/connectivity/discovery_service/internal/config/config.go"
    config_source = """\
type DaoConfig struct {
    DBName string `arg:"--dao/dbName" default:"discovery_service" help:"The name of the database to select"`
}
"""
    _write_source_tree(tmp_path, model_path, model_source)
    _write_source_tree(tmp_path, config_path, config_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 37 `// E.g. clickhouse://user:pass@host1:9000,host2:9000/db?dial_timeout=50ms&max_execution_time=5` -> fixture line 2
    # live line 188 `DBName              string ...` -> fixture line 2
    model_classification = mcp_server.classify_file("9ce90895", model_path)
    model_extracted = mcp_server.extract_function("9ce90895", model_path, 2)
    model_identifiers = mcp_server.find_identifiers("9ce90895", model_path, 2)
    model_cfg_trace = mcp_server.trace_identifier_backward("9ce90895", model_path, 2, "cfg")
    config_classification = mcp_server.classify_file("9ce90895", config_path)
    config_extracted = mcp_server.extract_function("9ce90895", config_path, 2)
    config_identifiers = mcp_server.find_identifiers("9ce90895", config_path, 2)
    config_db_name_trace = mcp_server.trace_identifier_backward("9ce90895", config_path, 2, "DBName")

    assert model_classification["type"] == "production"
    assert model_extracted["meta"]["code_on_line"] == "    // E.g. clickhouse://user:pass@host1:9000,host2:9000/db?dial_timeout=50ms&max_execution_time=5"
    assert model_identifiers == {"reads": [], "writes": [], "language": "go"}
    assert model_cfg_trace == []
    assert config_classification["type"] == "production"
    assert config_extracted["text"] == "// Function not found."
    assert (
        config_extracted["meta"]["code_on_line"]
        == '    DBName string `arg:"--dao/dbName" default:"discovery_service" help:"The name of the database to select"`'
    )
    assert config_identifiers == {"reads": [], "writes": ["DBName"], "language": "go"}
    assert config_db_name_trace == []


def test_active_finding_go_and_cpp_assignment_targets_should_keep_write_context(monkeypatch, tmp_path):
    cloud_modules_path = "cloud/connectivity/discovery_service/internal/discovery/cloud_modules_xml.go"
    cloud_modules_source = """\
func getCloudDbEndpoint() string {
    cdbHost = fmt.Sprintf("%s:%d", cdbHost, defaultCloudDbPort)
    return cdbHost
}
"""
    settings_path = "cloud/auth/libcloud_db/src/nx/cloud/db/settings.cpp"
    settings_source = """\
Settings::Settings()
{
    m_dbConnectionOptions.dbName = "nx_cloud";
}
"""
    _write_source_tree(tmp_path, cloud_modules_path, cloud_modules_source)
    _write_source_tree(tmp_path, settings_path, settings_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 320 `cdbHost = fmt.Sprintf("%s:%d", cdbHost, defaultCloudDbPort)` -> fixture line 2
    # live line 309 `m_dbConnectionOptions.dbName = "nx_cloud";` -> fixture line 3
    go_classification = mcp_server.classify_file("9ce90895", cloud_modules_path)
    go_extracted = mcp_server.extract_function("9ce90895", cloud_modules_path, 2)
    go_identifiers = mcp_server.find_identifiers("9ce90895", cloud_modules_path, 2)
    go_cdb_host_trace = mcp_server.trace_identifier_backward("9ce90895", cloud_modules_path, 2, "cdbHost")
    cpp_classification = mcp_server.classify_file("9ce90895", settings_path)
    cpp_extracted = mcp_server.extract_function("9ce90895", settings_path, 3)
    cpp_identifiers = mcp_server.find_identifiers("9ce90895", settings_path, 3)
    cpp_options_trace = mcp_server.trace_identifier_backward("9ce90895", settings_path, 3, "m_dbConnectionOptions")

    assert go_classification["type"] == "production"
    assert go_extracted["meta"]["code_on_line"] == '    cdbHost = fmt.Sprintf("%s:%d", cdbHost, defaultCloudDbPort)'
    assert go_identifiers == {
        "reads": ["Sprintf", "cdbHost", "defaultCloudDbPort", "fmt"],
        "writes": ["cdbHost"],
        "language": "go",
    }
    _assert_trace_codes(go_cdb_host_trace, ['cdbHost = fmt.Sprintf("%s:%d", cdbHost, defaultCloudDbPort)'])
    assert cpp_classification["type"] == "production"
    assert cpp_extracted["meta"]["code_on_line"] == '    m_dbConnectionOptions.dbName = "nx_cloud";'
    assert cpp_identifiers == {"reads": ["m_dbConnectionOptions"], "writes": ["dbName"], "language": "cpp"}
    assert cpp_options_trace == []


def test_active_finding_go_file_helpers_should_keep_argument_context(monkeypatch, tmp_path):
    vectorize_path = "cloud/storage/analytics_db_service/internal/vectorize/vectorize_utils.go"
    vectorize_source = """\
func VectorizeFolder(folder string, files []os.DirEntry) error {
    for _, file := range files {
        path := filepath.Join(folder, file.Name())
        data, err := os.ReadFile(path)
        if err != nil {
            return err
        }
        _ = data
    }
    return nil
}
"""
    rotate_path = "libs/go/tools/utils/nxlog/rotate.go"
    rotate_source = """\
func (r *logRotate) tryRotate(filesToRemove []string) {
    for _, file := range filesToRemove {
        if err := r.removeFile(file); err != nil {
            Errorf("Cannot remove file: %s (%v)", file, err)
        }
    }
}

func (*logRotate) removeFile(path string) error {
    return os.Remove(path)
}
"""
    _write_source_tree(tmp_path, vectorize_path, vectorize_source)
    _write_source_tree(tmp_path, rotate_path, rotate_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 286 `data, err := os.ReadFile(path)` -> fixture line 4
    # live line 74 `if err := r.removeFile(file); err != nil {` -> fixture line 3
    # live line 177 `return os.Remove(path)` -> fixture line 10
    vectorize_classification = mcp_server.classify_file("9ce90895", vectorize_path)
    vectorize_extracted = mcp_server.extract_function("9ce90895", vectorize_path, 4)
    vectorize_identifiers = mcp_server.find_identifiers("9ce90895", vectorize_path, 4)
    vectorize_path_trace = mcp_server.trace_identifier_backward("9ce90895", vectorize_path, 4, "path")
    rotate_if_classification = mcp_server.classify_file("9ce90895", rotate_path)
    rotate_if_extracted = mcp_server.extract_function("9ce90895", rotate_path, 3)
    rotate_if_identifiers = mcp_server.find_identifiers("9ce90895", rotate_path, 3)
    rotate_file_trace = mcp_server.trace_identifier_backward("9ce90895", rotate_path, 3, "file")
    rotate_return_extracted = mcp_server.extract_function("9ce90895", rotate_path, 10)
    rotate_return_identifiers = mcp_server.find_identifiers("9ce90895", rotate_path, 10)
    rotate_path_arg_trace = mcp_server.trace_identifier_backward("9ce90895", rotate_path, 10, "path")

    assert vectorize_classification["type"] == "production"
    assert vectorize_extracted["meta"]["code_on_line"] == "        data, err := os.ReadFile(path)"
    assert vectorize_identifiers == {"reads": ["ReadFile", "os", "path"], "writes": ["data", "err"], "language": "go"}
    _assert_trace_codes(vectorize_path_trace, ["path := filepath.Join(folder, file.Name())"])
    assert rotate_if_classification["type"] == "production"
    assert rotate_if_extracted["meta"]["code_on_line"] == "        if err := r.removeFile(file); err != nil {"
    assert rotate_if_identifiers == {
        "reads": ["Errorf", "err", "file", "r", "removeFile"],
        "writes": ["err"],
        "language": "go",
    }
    assert rotate_file_trace == []
    assert rotate_return_extracted["meta"]["code_on_line"] == "    return os.Remove(path)"
    assert rotate_return_identifiers == {"reads": ["Remove", "os", "path"], "writes": [], "language": "go"}
    assert rotate_path_arg_trace == []


def test_active_finding_native_pipe_copy_should_keep_buffer_offset_context(monkeypatch, tmp_path):
    pipe_utils_path = "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_pipe_utils.cpp"
    pipe_utils_source = """\
char* nxai_read_pipe_to_string() {
    char* out_string = (char*) malloc(sizeof(char) * 1024);
    size_t total_bytes_read = 0;
    char buffer[1024];
    DWORD bytes_read;
    out_string = (char*) realloc(out_string, total_bytes_read + bytes_read + 1);
    memcpy(out_string + total_bytes_read, buffer, bytes_read);
    total_bytes_read += bytes_read;
    ssize_t bytes_read;
    out_string = (char*) realloc(out_string, total_bytes_read + bytes_read + 1);
    memcpy(out_string + total_bytes_read, buffer, bytes_read);
    total_bytes_read += bytes_read;
    return out_string;
}
"""
    _write_source_tree(tmp_path, pipe_utils_path, pipe_utils_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 679 `memcpy(out_string + total_bytes_read, buffer, bytes_read);` -> fixture line 7
    # live line 688 `memcpy(out_string + total_bytes_read, buffer, bytes_read);` -> fixture line 11
    windows_classification = mcp_server.classify_file("9ce90895", pipe_utils_path)
    windows_extracted = mcp_server.extract_function("9ce90895", pipe_utils_path, 7)
    windows_identifiers = mcp_server.find_identifiers("9ce90895", pipe_utils_path, 7)
    windows_total_trace = mcp_server.trace_identifier_backward("9ce90895", pipe_utils_path, 7, "total_bytes_read")
    linux_extracted = mcp_server.extract_function("9ce90895", pipe_utils_path, 11)
    linux_identifiers = mcp_server.find_identifiers("9ce90895", pipe_utils_path, 11)
    linux_total_trace = mcp_server.trace_identifier_backward("9ce90895", pipe_utils_path, 11, "total_bytes_read")

    assert windows_classification["type"] == "production"
    assert windows_extracted["meta"]["code_on_line"] == "    memcpy(out_string + total_bytes_read, buffer, bytes_read);"
    assert windows_identifiers == {
        "reads": ["buffer", "bytes_read", "memcpy", "out_string", "total_bytes_read"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(windows_total_trace, ["size_t total_bytes_read = 0;"])
    assert linux_extracted["meta"]["code_on_line"] == "    memcpy(out_string + total_bytes_read, buffer, bytes_read);"
    assert linux_identifiers == {
        "reads": ["buffer", "bytes_read", "memcpy", "out_string", "total_bytes_read"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(
        linux_total_trace,
        [
            "total_bytes_read += bytes_read;",
            "DWORD bytes_read;",
        ],
    )


def test_active_finding_native_cleanup_and_inline_accessors_should_keep_symbol_context(monkeypatch, tmp_path):
    launcher_path = "open/vms/client/nx_vms_client_desktop/src/launcher/nov_launcher_win.cpp"
    launcher_source = """\
bool appendFile() {
    char* buffer = new char[IO_BUFFER_SIZE];
    try
    {
        delete[] buffer;
        return true;
    }
    catch (...)
    {
        delete[] buffer;
        return false;
    }
}
"""
    audio_buffer_path = "open/vms/libs/nx_vms_common/src/transcoding/ffmpeg_audio_buffer.h"
    audio_buffer_source = """\
class FfmpegAudioBuffer
{
public:
    [[nodiscard]] uint32_t sampleCount() const { return static_cast<uint32_t>(m_dataSize / m_sampleSize); }
};
"""
    _write_source_tree(tmp_path, launcher_path, launcher_source)
    _write_source_tree(tmp_path, audio_buffer_path, audio_buffer_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 60 `delete[] buffer;` -> fixture line 10
    # live line 51 `[[nodiscard]] uint32_t sampleCount() const { return static_cast<uint32_t>(m_dataSize / m_sampleSize); }` -> fixture line 4
    launcher_classification = mcp_server.classify_file("9ce90895", launcher_path)
    launcher_extracted = mcp_server.extract_function("9ce90895", launcher_path, 10)
    launcher_identifiers = mcp_server.find_identifiers("9ce90895", launcher_path, 10)
    launcher_buffer_trace = mcp_server.trace_identifier_backward("9ce90895", launcher_path, 10, "buffer")
    audio_classification = mcp_server.classify_file("9ce90895", audio_buffer_path)
    audio_extracted = mcp_server.extract_function("9ce90895", audio_buffer_path, 4)
    audio_identifiers = mcp_server.find_identifiers("9ce90895", audio_buffer_path, 4)
    audio_data_size_trace = mcp_server.trace_identifier_backward("9ce90895", audio_buffer_path, 4, "m_dataSize")

    assert launcher_classification["type"] == "production"
    assert launcher_extracted["meta"]["code_on_line"] == "        delete[] buffer;"
    assert launcher_identifiers == {"reads": ["buffer"], "writes": [], "language": "cpp"}
    _assert_trace_codes(launcher_buffer_trace, ["char* buffer = new char[IO_BUFFER_SIZE];"])
    assert audio_classification["type"] == "production"
    assert audio_extracted["meta"]["code_on_line"] == "    [[nodiscard]] uint32_t sampleCount() const { return static_cast<uint32_t>(m_dataSize / m_sampleSize); }"
    assert audio_identifiers == {
        "reads": ["m_dataSize", "m_sampleSize", "nodiscard", "static_cast"],
        "writes": ["sampleCount"],
        "language": "cpp",
    }
    assert audio_data_size_trace == []


def test_active_finding_native_vmaxproxy_buffer_flow_should_keep_recv_and_memmove_context(monkeypatch, tmp_path):
    vmaxproxy_path = "vms/vmaxproxy/src/main.cpp"
    vmaxproxy_source = """\
int main() {
    quint8 buffer[1024 * 4];
    int bufferLen = 0;
    int msgLen = isFullMessage(buffer, bufferLen);
    int bytesRead = mServerConnect.recv(buffer + bufferLen, sizeof(buffer) - bufferLen);
    bufferLen += bytesRead;
    msgLen = isFullMessage(buffer, bufferLen);
    memmove(buffer, buffer + msgLen, bufferLen - msgLen);
    bufferLen -= msgLen;
    return 0;
}
"""
    _write_source_tree(tmp_path, vmaxproxy_path, vmaxproxy_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 85 `int bytesRead = mServerConnect.recv(buffer + bufferLen, sizeof(buffer) - bufferLen);` -> fixture line 5
    # live line 109 `memmove(buffer, buffer + msgLen, bufferLen - msgLen);` -> fixture line 8
    classification = mcp_server.classify_file("9ce90895", vmaxproxy_path)
    recv_extracted = mcp_server.extract_function("9ce90895", vmaxproxy_path, 5)
    recv_identifiers = mcp_server.find_identifiers("9ce90895", vmaxproxy_path, 5)
    recv_buffer_len_trace = mcp_server.trace_identifier_backward("9ce90895", vmaxproxy_path, 5, "bufferLen")
    memmove_extracted = mcp_server.extract_function("9ce90895", vmaxproxy_path, 8)
    memmove_identifiers = mcp_server.find_identifiers("9ce90895", vmaxproxy_path, 8)
    memmove_buffer_len_trace = mcp_server.trace_identifier_backward("9ce90895", vmaxproxy_path, 8, "bufferLen")
    memmove_msg_len_trace = mcp_server.trace_identifier_backward("9ce90895", vmaxproxy_path, 8, "msgLen")

    assert classification["type"] == "production"
    assert recv_extracted["meta"]["code_on_line"] == "    int bytesRead = mServerConnect.recv(buffer + bufferLen, sizeof(buffer) - bufferLen);"
    assert recv_identifiers == {
        "reads": ["buffer", "bufferLen", "mServerConnect", "recv"],
        "writes": ["bytesRead"],
        "language": "cpp",
    }
    _assert_trace_codes(recv_buffer_len_trace, ["int bufferLen = 0;"])
    assert memmove_extracted["meta"]["code_on_line"] == "    memmove(buffer, buffer + msgLen, bufferLen - msgLen);"
    assert memmove_identifiers == {
        "reads": ["buffer", "bufferLen", "memmove", "msgLen"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(
        memmove_buffer_len_trace,
        [
            "bufferLen += bytesRead;",
            "int bytesRead = mServerConnect.recv(buffer + bufferLen, sizeof(buffer) - bufferLen);",
            "int bufferLen = 0;",
        ],
    )
    _assert_trace_codes(
        memmove_msg_len_trace,
        [
            "msgLen = isFullMessage(buffer, bufferLen);",
            "bufferLen += bytesRead;",
            "int bytesRead = mServerConnect.recv(buffer + bufferLen, sizeof(buffer) - bufferLen);",
        ],
    )


def test_active_finding_native_recv_windows_and_multiline_pointer_should_keep_offset_context(monkeypatch, tmp_path):
    eip_path = "vms/server/nx_vms_server/src/plugins/resource/flir/simple_eip_client.cpp"
    eip_source = """\
bool receiveMessage(char* buffer) {
    int totalBytesRead = 0;
    auto bytesRead = m_eipSocket->recv(
        buffer + totalBytesRead,
        kBufferSize - totalBytesRead);
    totalBytesRead += bytesRead;
    auto bytesRead2 = m_eipSocket->recv(
        buffer + totalBytesRead,
        kBufferSize - totalBytesRead);
    totalBytesRead += bytesRead2;
    return true;
}
"""
    tftp_path = "vms/server/nx_vms_server/src/plugins/resource/arecontvision/tools/simple_tftp_client.cpp"
    tftp_source = """\
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
    _write_source_tree(tmp_path, eip_path, eip_source)
    _write_source_tree(tmp_path, tftp_path, tftp_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 87 `kBufferSize - totalBytesRead);` -> fixture line 5
    # live line 103 `kBufferSize - totalBytesRead);` -> fixture line 9
    # live line 301 multiline `responseBuffer + responseLength - (blockSizeValueLength + 1)` -> fixture line 8
    eip_classification = mcp_server.classify_file("9ce90895", eip_path)
    eip_first_extracted = mcp_server.extract_function("9ce90895", eip_path, 5)
    eip_first_identifiers = mcp_server.find_identifiers("9ce90895", eip_path, 5)
    eip_first_total_trace = mcp_server.trace_identifier_backward("9ce90895", eip_path, 5, "totalBytesRead")
    eip_second_extracted = mcp_server.extract_function("9ce90895", eip_path, 9)
    eip_second_identifiers = mcp_server.find_identifiers("9ce90895", eip_path, 9)
    eip_second_total_trace = mcp_server.trace_identifier_backward("9ce90895", eip_path, 9, "totalBytesRead")
    tftp_classification = mcp_server.classify_file("9ce90895", tftp_path)
    tftp_extracted = mcp_server.extract_function("9ce90895", tftp_path, 8)
    tftp_identifiers = mcp_server.find_identifiers("9ce90895", tftp_path, 8)
    tftp_ptr_trace = mcp_server.trace_identifier_backward("9ce90895", tftp_path, 8, "blockSizeValuePtr")

    assert eip_classification["type"] == "production"
    assert eip_first_extracted["meta"]["code_on_line"] == "        kBufferSize - totalBytesRead);"
    assert eip_first_identifiers == {
        "reads": ["buffer", "kBufferSize", "m_eipSocket", "recv", "totalBytesRead"],
        "writes": ["bytesRead"],
        "language": "cpp",
    }
    _assert_trace_codes(eip_first_total_trace, ["int totalBytesRead = 0;"])
    assert eip_second_extracted["meta"]["code_on_line"] == "        kBufferSize - totalBytesRead);"
    assert eip_second_identifiers == {
        "reads": ["buffer", "kBufferSize", "m_eipSocket", "recv", "totalBytesRead"],
        "writes": ["bytesRead2"],
        "language": "cpp",
    }
    _assert_trace_codes(
        eip_second_total_trace,
        [
            "totalBytesRead += bytesRead;",
            "auto bytesRead = m_eipSocket->recv(",
            "int totalBytesRead = 0;",
        ],
    )
    assert tftp_classification["type"] == "production"
    assert tftp_extracted["meta"]["code_on_line"] == (
        "responseBuffer\n"
        "        + responseLength\n"
        "        - (blockSizeValueLength + 1)"
    )
    assert tftp_identifiers == {
        "reads": ["blockSizeValueLength", "responseBuffer", "responseLength"],
        "writes": ["blockSizeValuePtr"],
        "language": "cpp",
    }
    _assert_trace_codes(
        tftp_ptr_trace,
        [
            "const auto blockSizeValuePtr = responseBuffer",
            "const int blockSizeValueLength = responseLength",
            "const auto optionNameLength = (int) std::strlen(kBlockSizeOption);",
        ],
    )


def test_active_finding_tftp_multiline_pointer_should_preserve_full_expression_text(monkeypatch, tmp_path):
    tftp_path = "vms/server/nx_vms_server/src/plugins/resource/arecontvision/tools/simple_tftp_client.cpp"
    tftp_source = """\
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
    _write_source_tree(tmp_path, tftp_path, tftp_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    extracted = mcp_server.extract_function("9ce90895", tftp_path, 8)

    # Oracle: the target line sits inside one multiline pointer-arithmetic expression,
    # so code_on_line should preserve the full expression text, not a truncated prefix.
    assert extracted["meta"]["code_on_line"] == (
        "responseBuffer\n"
        "        + responseLength\n"
        "        - (blockSizeValueLength + 1)"
    )


def test_active_finding_plugin_manager_multiline_format_should_preserve_full_expression_text(
    monkeypatch, tmp_path
):
    file_path = "vms/server/nx_vms_server/src/plugins/plugin_manager.cpp"
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
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    extracted = mcp_server.extract_function("9ce90895", file_path, 7)

    assert extracted["meta"]["code_on_line"] == (
        "originalPluginInfoDescription =\n"
        "            NX_FMT(\"Original PluginInfo fields: errorCode [%1], statusMessage %2\",\n"
        "                pluginInfo->errorCode, nx::kit::utils::toString(pluginInfo->statusMessage))"
    )


def test_active_finding_cloud_storage_template_reads_should_keep_bounds_and_copy_context(
    monkeypatch, tmp_path
):
    file_path = (
        "open/vms/server/plugins/cloud_storage/stub_cloud_storage_plugin/src/"
        "nx/vms_server_plugins/cloud_storage/stub/data_manager.cpp"
    )
    source = """\
template<typename T, typename Container>
T read(const Container& c, int* outPos)
{
    T result;
    if (*outPos + sizeof(result) > c.size())
        throw std::runtime_error("Not enough data");

    memcpy(&result, c.data() + *outPos, sizeof(result));
    *outPos += sizeof(result);
    return result;
}

template<typename T, typename Container>
T readBytes(const Container& c, size_t size, int* outPos, int padding = 0)
{
    T result;
    if (*outPos + size > c.size())
        throw std::runtime_error("Not enough data");

    result.resize(size + padding);
    memcpy(result.data(), c.data() + *outPos, size);
    *outPos += size;
    return result;
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    first_guard = mcp_server.extract_function("9ce90895", file_path, 5)
    first_guard_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 5)
    first_copy = mcp_server.extract_function("9ce90895", file_path, 8)
    first_copy_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 8)
    second_guard = mcp_server.extract_function("9ce90895", file_path, 17)
    second_guard_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 17)
    second_copy = mcp_server.extract_function("9ce90895", file_path, 21)
    second_copy_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 21)

    assert classification["type"] == "production"
    assert first_guard["meta"]["code_on_line"] == "    if (*outPos + sizeof(result) > c.size())"
    assert first_guard_identifiers == {
        "reads": ["c", "outPos", "result", "runtime_error", "size"],
        "writes": [],
        "language": "cpp",
    }
    assert first_copy["meta"]["code_on_line"] == "    memcpy(&result, c.data() + *outPos, sizeof(result));"
    assert first_copy_identifiers == {
        "reads": ["c", "data", "memcpy", "outPos", "result"],
        "writes": [],
        "language": "cpp",
    }
    assert second_guard["meta"]["code_on_line"] == "    if (*outPos + size > c.size())"
    assert second_guard_identifiers == {
        "reads": ["c", "outPos", "runtime_error", "size"],
        "writes": [],
        "language": "cpp",
    }
    assert second_copy["meta"]["code_on_line"] == "    memcpy(result.data(), c.data() + *outPos, size);"
    assert second_copy_identifiers == {
        "reads": ["c", "data", "memcpy", "outPos", "result", "size"],
        "writes": [],
        "language": "cpp",
    }


def test_active_finding_logging_system_counters_and_pipe_buffers_should_keep_context(
    monkeypatch, tmp_path
):
    engine_path = (
        "open/vms/server/plugins/analytics/stub_analytics_plugin/src/"
        "nx/vms_server_plugins/analytics/stub/special_objects/engine.cpp"
    )
    engine_source = """\
QString renderMessage(QString messageToUser) {
    if (messageToUser.isEmpty())
        messageToUser += "No param values provided.";
    NX_PRINT << __func__ << "(): Returning a message: "
        << nx::kit::utils::toString(messageToUser);
    return messageToUser;
}
"""
    read_path = "vms/libs/nx_system_commands/src/nx/system_commands/domain_socket/read_linux.cpp"
    read_source = """\
int readData(int transportFd, void* context) {
    struct DataContext* dataContext = (struct DataContext*) context;
    ssize_t messageSize, readBytes, total = 0;
    while (total < messageSize)
    {
        readBytes = read(transportFd, (char*) dataContext->data + total, messageSize - total);
    }
    return 0;
}
"""
    pipe_path = (
        "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_pipe_utils.cpp"
    )
    pipe_source = """\
char* readPipe(int pipe, char* out_string, size_t total_bytes_read) {
    char buffer[8];
    ssize_t bytes_read;
    while ((bytes_read = read(pipe, buffer, sizeof(buffer))) > 0)
    {
        out_string = (char*) realloc(out_string, total_bytes_read + bytes_read + 1);
        memcpy(out_string + total_bytes_read, buffer, bytes_read);
        total_bytes_read += bytes_read;
    }
    return out_string;
}
"""
    monitor_path = "open/libs/nx_monitoring/src/nx/monitoring/monitor_linux.cpp"
    monitor_source = """\
int64_t calculate(Private* d, int64_t cpuTimeTotal, int64_t cpuTimeIdle) {
    const int64_t cpuTimeTotalDiff = cpuTimeTotal - d->prevCPUTimeTotal;
    const int64_t cpuTimeIdleDiff = cpuTimeIdle - d->prevCPUTimeIdle;
    return cpuTimeTotalDiff + cpuTimeIdleDiff;
}
"""
    _write_source_tree(tmp_path, engine_path, engine_source)
    _write_source_tree(tmp_path, read_path, read_source)
    _write_source_tree(tmp_path, pipe_path, pipe_source)
    _write_source_tree(tmp_path, monitor_path, monitor_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    engine_classification = mcp_server.classify_file("9ce90895", engine_path)
    engine_extracted = mcp_server.extract_function("9ce90895", engine_path, 5)
    engine_identifiers = mcp_server.find_identifiers("9ce90895", engine_path, 5)
    engine_trace = mcp_server.trace_identifier_backward("9ce90895", engine_path, 5, "messageToUser")
    read_extracted = mcp_server.extract_function("9ce90895", read_path, 6)
    read_identifiers = mcp_server.find_identifiers("9ce90895", read_path, 6)
    read_trace = mcp_server.trace_identifier_backward("9ce90895", read_path, 6, "total")
    pipe_extracted = mcp_server.extract_function("9ce90895", pipe_path, 6)
    pipe_identifiers = mcp_server.find_identifiers("9ce90895", pipe_path, 6)
    pipe_trace = mcp_server.trace_identifier_backward("9ce90895", pipe_path, 6, "out_string")
    pipe_copy_extracted = mcp_server.extract_function("9ce90895", pipe_path, 7)
    pipe_copy_identifiers = mcp_server.find_identifiers("9ce90895", pipe_path, 7)
    monitor_total_extracted = mcp_server.extract_function("9ce90895", monitor_path, 2)
    monitor_total_identifiers = mcp_server.find_identifiers("9ce90895", monitor_path, 2)
    monitor_total_trace = mcp_server.trace_identifier_backward(
        "9ce90895", monitor_path, 2, "cpuTimeTotalDiff"
    )
    monitor_idle_extracted = mcp_server.extract_function("9ce90895", monitor_path, 3)
    monitor_idle_identifiers = mcp_server.find_identifiers("9ce90895", monitor_path, 3)
    monitor_idle_trace = mcp_server.trace_identifier_backward(
        "9ce90895", monitor_path, 3, "cpuTimeIdleDiff"
    )

    assert engine_classification["type"] == "production"
    assert engine_extracted["meta"]["code_on_line"] == (
        'NX_PRINT << __func__ << "(): Returning a message: "\n'
        "        << nx::kit::utils::toString(messageToUser)"
    )
    assert engine_identifiers == {
        "reads": ["NX_PRINT", "__func__", "messageToUser", "toString"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(engine_trace, ['messageToUser += "No param values provided.";'])
    assert read_extracted["meta"]["code_on_line"] == (
        "        readBytes = read(transportFd, (char*) dataContext->data + total, messageSize - total);"
    )
    assert read_identifiers == {
        "reads": ["data", "dataContext", "messageSize", "read", "total", "transportFd"],
        "writes": ["readBytes"],
        "language": "cpp",
    }
    _assert_trace_codes(read_trace, ["ssize_t messageSize, readBytes, total = 0;"])
    assert pipe_extracted["meta"]["code_on_line"] == (
        "        out_string = (char*) realloc(out_string, total_bytes_read + bytes_read + 1);"
    )
    assert pipe_identifiers == {
        "reads": ["bytes_read", "out_string", "realloc", "total_bytes_read"],
        "writes": ["out_string"],
        "language": "cpp",
    }
    _assert_trace_codes(
        pipe_trace,
        [
            "out_string = (char*) realloc(out_string, total_bytes_read + bytes_read + 1);",
            "while ((bytes_read = read(pipe, buffer, sizeof(buffer))) > 0)",
        ],
    )
    assert pipe_copy_extracted["meta"]["code_on_line"] == (
        "        memcpy(out_string + total_bytes_read, buffer, bytes_read);"
    )
    assert pipe_copy_identifiers == {
        "reads": ["buffer", "bytes_read", "memcpy", "out_string", "total_bytes_read"],
        "writes": [],
        "language": "cpp",
    }
    assert monitor_total_extracted["meta"]["code_on_line"] == (
        "    const int64_t cpuTimeTotalDiff = cpuTimeTotal - d->prevCPUTimeTotal;"
    )
    assert monitor_total_identifiers == {
        "reads": ["cpuTimeTotal", "d", "prevCPUTimeTotal"],
        "writes": ["cpuTimeTotalDiff"],
        "language": "cpp",
    }
    _assert_trace_codes(
        monitor_total_trace,
        ["const int64_t cpuTimeTotalDiff = cpuTimeTotal - d->prevCPUTimeTotal;"],
    )
    assert monitor_idle_extracted["meta"]["code_on_line"] == (
        "    const int64_t cpuTimeIdleDiff = cpuTimeIdle - d->prevCPUTimeIdle;"
    )
    assert monitor_idle_identifiers == {
        "reads": ["cpuTimeIdle", "d", "prevCPUTimeIdle"],
        "writes": ["cpuTimeIdleDiff"],
        "language": "cpp",
    }
    _assert_trace_codes(
        monitor_idle_trace,
        ["const int64_t cpuTimeIdleDiff = cpuTimeIdle - d->prevCPUTimeIdle;"],
    )


def test_active_finding_accl_manager_substring_assignments_should_keep_end_tracking(
    monkeypatch, tmp_path
):
    file_path = "vms/server/plugins/analytics/nx_ai_manager_plugin/plugin/src/accl_manager/utils.cpp"
    source = """\
void parse(std::string line) {
    std::string os_id;
    std::string version_id;
    size_t start = line.find('=') + 1;
    // Remove quotes if present
    if (line[start] == '"')
    {
        start++;
        size_t end = line.rfind('"');
        os_id = lower_case(line.substr(start, end - start));
    }
    else
    {
        size_t end = line.length();
        os_id = lower_case(line.substr(start, end - start));
    }
    if (line.find("VERSION_ID=") == 0)
    {
        size_t start = line.find('=') + 1;
        // Remove quotes if present
        if (line[start] == '"')
        {
            start++;
            size_t end = line.rfind('"');
            version_id = line.substr(start, end - start);
        }
        else
        {
            size_t end = line.length();
            version_id = line.substr(start, end - start);
        }
    }
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    quoted_os = mcp_server.extract_function("9ce90895", file_path, 10)
    quoted_os_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 10)
    quoted_os_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 10, "os_id")
    plain_os = mcp_server.extract_function("9ce90895", file_path, 15)
    plain_os_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 15)
    plain_os_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 15, "os_id")
    quoted_version = mcp_server.extract_function("9ce90895", file_path, 25)
    quoted_version_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 25)
    quoted_version_trace = mcp_server.trace_identifier_backward(
        "9ce90895", file_path, 25, "version_id"
    )
    plain_version = mcp_server.extract_function("9ce90895", file_path, 30)
    plain_version_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 30)
    plain_version_trace = mcp_server.trace_identifier_backward(
        "9ce90895", file_path, 30, "version_id"
    )

    assert quoted_os["meta"]["code_on_line"] == "        os_id = lower_case(line.substr(start, end - start));"
    assert quoted_os_identifiers == {
        "reads": ["end", "line", "lower_case", "start", "substr"],
        "writes": ["os_id"],
        "language": "cpp",
    }
    _assert_trace_codes(
        quoted_os_trace,
        [
            "os_id = lower_case(line.substr(start, end - start));",
            "size_t end = line.rfind('\"');",
        ],
    )
    assert plain_os["meta"]["code_on_line"] == "        os_id = lower_case(line.substr(start, end - start));"
    assert plain_os_identifiers == {
        "reads": ["end", "line", "lower_case", "start", "substr"],
        "writes": ["os_id"],
        "language": "cpp",
    }
    _assert_trace_codes(
        plain_os_trace,
        [
            "os_id = lower_case(line.substr(start, end - start));",
            "size_t end = line.length();",
        ],
    )
    assert quoted_version["meta"]["code_on_line"] == (
        "            version_id = line.substr(start, end - start);"
    )
    assert quoted_version_identifiers == {
        "reads": ["end", "line", "start", "substr"],
        "writes": ["version_id"],
        "language": "cpp",
    }
    _assert_trace_codes(
        quoted_version_trace,
        [
            "version_id = line.substr(start, end - start);",
            "size_t end = line.rfind('\"');",
        ],
    )
    assert plain_version["meta"]["code_on_line"] == (
        "            version_id = line.substr(start, end - start);"
    )
    assert plain_version_identifiers == {
        "reads": ["end", "line", "start", "substr"],
        "writes": ["version_id"],
        "language": "cpp",
    }
    _assert_trace_codes(
        plain_version_trace,
        [
            "version_id = line.substr(start, end - start);",
            "size_t end = line.length();",
        ],
    )


def test_active_finding_go_tls_config_should_keep_factory_trace_context(monkeypatch, tmp_path):
    file_path = "libs/go/tools/network/nxhttpclient/factory.go"
    source = """\
func New(cfg *Config) *HTTPClientFactory {
    var factory HTTPClientFactory
    factory.config = cfg
    if cfg == nil {
        cfg = &Config{Timeout: 10 * time.Second}
    }
    tr := customTransport{}
    if !factory.config.Verify {
        tr.Base.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
    }
    return &factory
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 9)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 9)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 9)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 9, "factory")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        tr.Base.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["InsecureSkipVerify"]
    assert identifiers["writes"] == ["Base", "TLSClientConfig", "tr"]
    assert identifiers["language"] == "go"
    assert trace == [
        {"line": 3, "code": "factory.config = cfg", "writes": ["factory"], "reads": ["cfg"]},
    ]


def test_active_finding_go_http_tls_config_should_keep_receiver_context(monkeypatch, tmp_path):
    file_path = "libs/go/tools/network/nxhttp/http.go"
    source = """\
func (s *Server) updateTLSConfig(config *Config) {
    if s.TLSConfig == nil {
        s.TLSConfig = new(tls.Config)
    }
    _ = config
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 3)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 3)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 3)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 3, "config")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        s.TLSConfig = new(tls.Config)"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["new"]
    assert identifiers["writes"] == ["TLSConfig", "s"]
    assert identifiers["language"] == "go"
    assert trace == []


def test_active_finding_java_digest_should_keep_md5_constructor_context(monkeypatch, tmp_path):
    file_path = "open/vms/client/mobile_client/android.in/src/com/nxvms/mobile/utils/HttpDigestAuth.java"
    source = """\
private static final String kEncoding = "ISO-8859-1";
private static String getHaDigest(String haString)
{
    try
    {
        final MessageDigest md5 = MessageDigest.getInstance("MD5");
        md5.update(haString.getBytes(kEncoding));
        return bytesToHexString(md5.digest());
    }
    catch (Exception e)
    {
        return null;
    }
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 6)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 6)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 6)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 6, "md")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == '        final MessageDigest md5 = MessageDigest.getInstance("MD5");'
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == ["MessageDigest", "getInstance"]
    assert identifiers["writes"] == ["md5"]
    assert identifiers["language"] == "java"
    assert trace == []


def test_active_finding_java_push_message_connection_should_keep_url_and_auth_context(monkeypatch, tmp_path):
    file_path = "open/vms/client/mobile_client/android.in/src/com/nxvms/mobile/push/PushMessageManager.java"
    source = """\
import java.net.URL;
import java.net.HttpURLConnection;
import com.nxvms.mobile.utils.HttpDigestAuth;

class PushMessageManager {
    private Object loadImage(ContextData context, AuthMethod method, UserData data) throws Exception {
        final URL imageUrl = new URL(context.imageUrl);
        HttpURLConnection connection = (HttpURLConnection) imageUrl.openConnection();
        connection.setInstanceFollowRedirects(false);
        if (method == AuthMethod.bearer) {
            return null;
        } else if (!TextUtils.isEmpty(data.password)) {
            connection = HttpDigestAuth.tryAuth(connection, data.user, data.password);
        }
        return connection;
    }
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted_open = mcp_server.extract_function("9ce90895", file_path, 8)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 8)
    identifiers_open = mcp_server.find_identifiers("9ce90895", file_path, 8)
    trace_open = mcp_server.trace_identifier_backward("9ce90895", file_path, 8, "connection")
    extracted_auth = mcp_server.extract_function("9ce90895", file_path, 13)
    identifiers_auth = mcp_server.find_identifiers("9ce90895", file_path, 13)
    trace_auth = mcp_server.trace_identifier_backward("9ce90895", file_path, 13, "connection")

    assert classification["type"] == "production"
    assert extracted_open["meta"]["code_on_line"] == "        HttpURLConnection connection = (HttpURLConnection) imageUrl.openConnection();"
    assert imports == [
        "import java.net.URL;",
        "import java.net.HttpURLConnection;",
        "import com.nxvms.mobile.utils.HttpDigestAuth;",
    ]
    assert decorators == []
    assert identifiers_open["reads"] == ["imageUrl", "openConnection"]
    assert identifiers_open["writes"] == ["connection"]
    assert identifiers_open["language"] == "java"
    assert trace_open == [
        {
            "line": 8,
            "code": "HttpURLConnection connection = (HttpURLConnection) imageUrl.openConnection();",
            "writes": ["connection"],
            "reads": ["imageUrl", "openConnection"],
        },
        {"line": 7, "code": "final URL imageUrl = new URL(context.imageUrl);", "writes": ["imageUrl"], "reads": ["context"]},
    ]
    assert extracted_auth["meta"]["code_on_line"] == "            connection = HttpDigestAuth.tryAuth(connection, data.user, data.password);"
    assert identifiers_auth["reads"] == ["HttpDigestAuth", "connection", "data", "password", "tryAuth", "user"]
    assert identifiers_auth["writes"] == ["connection"]
    assert identifiers_auth["language"] == "java"
    assert trace_auth == [
        {
            "line": 13,
            "code": "connection = HttpDigestAuth.tryAuth(connection, data.user, data.password);",
            "writes": ["connection"],
            "reads": ["HttpDigestAuth", "connection", "data", "password", "tryAuth", "user"],
        }
    ]


def test_active_finding_javascript_browser_window_config_should_keep_object_literal_context(monkeypatch, tmp_path):
    file_path = "open/vms/server/stub_analytics_api_integration/main.js"
    source = """\
const createWindow = () => {
    const window = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            preload: path.resolve(__dirname, "preload.js"),
            nodeIntegration: true,
            contextIsolation: true,
            enableRemoteModule: true,
        }
    });
    return window;
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 7)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 7)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 7)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 7, "window")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "            nodeIntegration: true,"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == [
        "BrowserWindow",
        "__dirname",
        "contextIsolation",
        "enableRemoteModule",
        "height",
        "nodeIntegration",
        "path",
        "preload",
        "resolve",
        "webPreferences",
        "width",
    ]
    assert identifiers["writes"] == ["window"]
    assert identifiers["language"] == "javascript"
    assert trace == [
        {
            "line": 2,
            "code": "const window = new BrowserWindow({",
            "writes": ["window"],
            "reads": [
                "BrowserWindow",
                "__dirname",
                "contextIsolation",
                "enableRemoteModule",
                "height",
                "nodeIntegration",
                "path",
                "preload",
                "resolve",
                "webPreferences",
                "width",
            ],
        }
    ]


def test_active_finding_javascript_event_handlers_should_keep_error_and_channel_context(monkeypatch, tmp_path):
    file_path = "open/vms/server/stub_analytics_api_integration/frontend.js"
    source = """\
function initWebSocket(url) {
      serverConnection = new WebSocket(url);

      serverConnection.onopen = () => {
        console.log('WebSocket connection established');
      };

      serverConnection.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
}

function startSourceBuffer()
{
  mse.sourceBuffer.onerror = event => {
    console.log('ms update error ' + event);
    reconnectHandler(event);
  };
}

function start() {
  webrtc.peerConnection.addEventListener('datachannel', event => {
    webrtc.remoteDataChannel = event.channel;
    webrtc.remoteDataChannel.binaryType = 'arraybuffer';
    webrtc.remoteDataChannel.addEventListener('message', event => {
      if (typeof(event.data) === 'string') {
        var message = JSON.parse(event.data);
        var timestampMs = parseInt(message.timestampMs);
        window.mainProcess.ipc.send("update-timestamp", timestampMs);
        webrtc.lastTimestampMs = timestampMs;
        var currentTimestampMs = Math.floor(Date.now());
        var diff = currentTimestampMs - timestampMs;
        console.log('dc message: ' + event.data + ' timestampMs diff: ' + diff);
        elements.timestamp.textContent = event.data;
      }
    });
  });
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted_error = mcp_server.extract_function("9ce90895", file_path, 8)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators_error = mcp_server.find_decorators("9ce90895", file_path, 8)
    identifiers_error = mcp_server.find_identifiers("9ce90895", file_path, 8)
    trace_error = mcp_server.trace_identifier_backward("9ce90895", file_path, 8, "error")
    extracted_buffer = mcp_server.extract_function("9ce90895", file_path, 15)
    decorators_buffer = mcp_server.find_decorators("9ce90895", file_path, 15)
    identifiers_buffer = mcp_server.find_identifiers("9ce90895", file_path, 15)
    trace_buffer = mcp_server.trace_identifier_backward("9ce90895", file_path, 15, "event")
    extracted_message = mcp_server.extract_function("9ce90895", file_path, 25)
    decorators_message = mcp_server.find_decorators("9ce90895", file_path, 25)
    identifiers_message = mcp_server.find_identifiers("9ce90895", file_path, 25)
    trace_message = mcp_server.trace_identifier_backward("9ce90895", file_path, 25, "event")

    assert classification["type"] == "production"
    assert extracted_error["meta"]["code_on_line"] == "      serverConnection.onerror = (error) => {"
    assert imports == []
    assert decorators_error == []
    assert identifiers_error["reads"] == ["console", "error", "serverConnection"]
    assert identifiers_error["writes"] == ["onerror"]
    assert identifiers_error["language"] == "javascript"
    assert trace_error == []
    assert extracted_buffer["meta"]["code_on_line"] == "  mse.sourceBuffer.onerror = event => {"
    assert decorators_buffer == []
    assert identifiers_buffer["reads"] == ["console", "event", "log", "mse", "reconnectHandler", "sourceBuffer"]
    assert identifiers_buffer["writes"] == ["onerror"]
    assert identifiers_buffer["language"] == "javascript"
    assert trace_buffer == []
    assert extracted_message["meta"]["code_on_line"] == "    webrtc.remoteDataChannel.addEventListener('message', event => {"
    assert decorators_message == []
    assert {
        "Date",
        "JSON",
        "Math",
        "addEventListener",
        "event",
        "mainProcess",
        "parseInt",
        "remoteDataChannel",
        "timestampMs",
        "webrtc",
        "window",
    } <= set(identifiers_message["reads"])
    assert identifiers_message["writes"] == []
    assert identifiers_message["language"] == "javascript"
    assert trace_message == []


def test_active_finding_python_script_invocation_should_keep_argument_and_command_context(monkeypatch, tmp_path):
    run_after_fetch_path = "build_utils/python/run_after_fetch.py"
    run_after_fetch_source = """\
from pathlib import Path
import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    args, _ = parser.parse_known_args()
    Path(args.checker_flag_file).touch()
    sys.path += args.checker_pythonpath
    script = __import__(args.checker_run_script)
    script.main()
"""
    tracker_path = "cloud/ams/utils/tracker_evaluator/scripts/run.py"
    tracker_source = """\
import os
import subprocess

SERVER_CONFIG_PATH = "server.json"


def main(args, benchmark, datasets_folder, output_folder, detector_engine_path, tracker_evaluator_path, tracker):
    serverConfigPath = os.path.join(args.nx_source_folder, SERVER_CONFIG_PATH)
    cmd =[
            tracker_evaluator_path,
            "-d",
            datasets_folder,
            "-o",
            output_folder,
            f"--benchmark={benchmark}",
            f"--server_config={serverConfigPath}",
            f"--detector_engine={detector_engine_path}",
            f"--tracker={tracker}",
    ]
    subprocess.run(cmd)
"""
    ninja_path = "open/build_utils/ninja/ninja_tool.py"
    ninja_source = """\
import subprocess


def run_commands(script_data):
    for command in script_data.commands_to_run:
        print(f"Running {command}...")
        subprocess.call(command)
"""
    qml_path = "open/build_utils/qmldeploy.py"
    qml_source = """\
import subprocess


class Deploy:
    def invoke_qmlimportscanner(self, qml_root):
        command = [self.scanner_path, "-rootPath", qml_root, "-importPath", self.import_path]
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        return process
"""
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import subprocess


def get_lib_dirs_from_compiler(compiler, compiler_flags=""):
    lines = subprocess.check_output(
        "{} --print-search-dirs {}".format(compiler, compiler_flags),
        universal_newlines=True,
        shell=True).split()
    return lines
"""
    _write_source_tree(tmp_path, run_after_fetch_path, run_after_fetch_source)
    _write_source_tree(tmp_path, tracker_path, tracker_source)
    _write_source_tree(tmp_path, ninja_path, ninja_source)
    _write_source_tree(tmp_path, qml_path, qml_source)
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    run_after_fetch_identifiers = mcp_server.find_identifiers("9ce90895", run_after_fetch_path, 11)
    run_after_fetch_trace = mcp_server.trace_identifier_backward("9ce90895", run_after_fetch_path, 11, "args")
    tracker_extracted = mcp_server.extract_function("9ce90895", tracker_path, 9)
    tracker_identifiers = mcp_server.find_identifiers("9ce90895", tracker_path, 9)
    tracker_trace = mcp_server.trace_identifier_backward("9ce90895", tracker_path, 9, "serverConfigPath")
    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 5)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 5, "compiler")
    ninja_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 7)
    ninja_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 7, "command")
    qml_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 6)
    qml_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 6, "command")

    assert run_after_fetch_identifiers["reads"] == ["__import__", "args", "checker_run_script"]
    assert run_after_fetch_identifiers["writes"] == ["script"]
    assert run_after_fetch_identifiers["language"] == "python"
    assert run_after_fetch_trace == [
        {"line": 8, "code": "args, _ = parser.parse_known_args()", "writes": ["args"], "reads": ["parse_known_args", "parser"]},
        {"line": 7, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert tracker_extracted["meta"]["code_on_line"] == "    cmd =["
    assert {
        "benchmark",
        "datasets_folder",
        "detector_engine_path",
        "output_folder",
        "serverConfigPath",
        "tracker",
        "tracker_evaluator_path",
    } <= set(tracker_identifiers["reads"])
    assert tracker_identifiers["writes"] == ["cmd"]
    assert tracker_trace == [
        {
            "line": 8,
            "code": "serverConfigPath = os.path.join(args.nx_source_folder, SERVER_CONFIG_PATH)",
            "writes": ["serverConfigPath"],
            "reads": ["SERVER_CONFIG_PATH", "args", "join", "nx_source_folder", "os", "path"],
        }
    ]
    assert copy_lib_identifiers["reads"] == [
        "check_output",
        "compiler",
        "compiler_flags",
        "format",
        "shell",
        "split",
        "subprocess",
        "universal_newlines",
    ]
    assert copy_lib_identifiers["writes"] == ["lines"]
    assert copy_lib_trace == []
    assert ninja_identifiers["reads"] == ["call", "command", "subprocess"]
    assert ninja_identifiers["writes"] == []
    assert ninja_trace == [
        {
            "line": 5,
            "code": "for command in script_data.commands_to_run:",
            "writes": ["command"],
            "reads": ["call", "commands_to_run", "print", "script_data", "subprocess"],
        }
    ]
    assert qml_identifiers["reads"] == ["import_path", "qml_root", "scanner_path", "self"]
    assert qml_identifiers["writes"] == ["command"]
    assert qml_trace == [
        {
            "line": 6,
            "code": 'command = [self.scanner_path, "-rootPath", qml_root, "-importPath", self.import_path]',
            "writes": ["command"],
            "reads": ["import_path", "qml_root", "scanner_path", "self"],
        }
    ]


def test_active_finding_qmldeploy_plugin_info_should_keep_regex_and_navigation_context(monkeypatch, tmp_path):
    qml_path = "open/build_utils/qmldeploy.py"
    qml_source = """\
import os
import re


class QmlDeployUtil:
    def get_plugin_information(self, plugin_name):
        pri_file_name = os.path.join(self.modules_path, "qt_plugin_{}.pri".format(plugin_name))
        with open(pri_file_name) as pri_file:
            pri_data = pri_file.read()
        re_prefix = "QT_PLUGIN\\." + plugin_name + "\\."
        m = re.search(re_prefix + "TYPE = (.+)", pri_data)
        m = re.search(re_prefix + "CLASS_NAME = (.+)", pri_data)
        return m

    def print_static_plugins(self, additional_plugins):
        for plugin_name in additional_plugins:
            info = self.get_plugin_information(plugin_name)
            print(info)

    def generate_import_cpp(self, additional_plugins):
        for plugin_name in additional_plugins:
            info = self.get_plugin_information(plugin_name)
            print(info)


def main():
    deploy_util = QmlDeployUtil()
    deploy_util.print_static_plugins(["alpha"])
    deploy_util.generate_import_cpp(["beta"])
"""
    _write_source_tree(tmp_path, qml_path, qml_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 136 `m = re.search(re_prefix + "TYPE = (.+)", pri_data)` -> fixture line 11
    # live line 145 `m = re.search(re_prefix + "CLASS_NAME = (.+)", pri_data)` -> fixture line 12
    # live line 214 `info = self.get_plugin_information(plugin_name)` -> fixture line 17
    # live line 242 `info = self.get_plugin_information(plugin_name)` -> fixture line 22
    type_extract = mcp_server.extract_function("9ce90895", qml_path, 11)
    type_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 11)
    type_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 11, "pri_data")
    class_extract = mcp_server.extract_function("9ce90895", qml_path, 12)
    class_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 12)
    class_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 12, "re_prefix")
    plugin_imports = mcp_server.find_imports("9ce90895", qml_path)
    plugin_decorators = mcp_server.find_decorators("9ce90895", qml_path, 11)
    helper_callers = mcp_server.find_callers("9ce90895", qml_path, "get_plugin_information")
    helper_route = mcp_server.find_route_to_function("9ce90895", "get_plugin_information")

    print_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 17)
    print_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 17, "plugin_name")
    print_callers = mcp_server.find_callers("9ce90895", qml_path, "print_static_plugins")
    helper_definition = mcp_server.find_definition("9ce90895", "get_plugin_information")

    generate_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 22)
    generate_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 22, "plugin_name")
    generate_callers = mcp_server.find_callers("9ce90895", qml_path, "generate_import_cpp")
    generate_route = mcp_server.find_route_to_function("9ce90895", "generate_import_cpp")

    assert type_extract["meta"]["code_on_line"] == '        m = re.search(re_prefix + "TYPE = (.+)", pri_data)'
    assert type_identifiers == {
        "reads": ["pri_data", "re", "re_prefix", "search"],
        "writes": ["m"],
        "language": "python",
    }
    _assert_trace_codes(
        type_trace,
        [
            "pri_data = pri_file.read()",
            "with open(pri_file_name) as pri_file:",
            'pri_file_name = os.path.join(self.modules_path, "qt_plugin_{}.pri".format(plugin_name))',
        ],
    )
    assert class_extract["meta"]["code_on_line"] == '        m = re.search(re_prefix + "CLASS_NAME = (.+)", pri_data)'
    assert class_identifiers == {
        "reads": ["pri_data", "re", "re_prefix", "search"],
        "writes": ["m"],
        "language": "python",
    }
    _assert_trace_codes(class_trace, ['re_prefix = "QT_PLUGIN\\." + plugin_name + "\\."'])
    assert plugin_imports == ["import os", "import re"]
    assert plugin_decorators == []
    assert helper_callers == [
        {
            "file": qml_path,
            "line": 17,
            "caller_function": "print_static_plugins",
            "snippet": "       16|         for plugin_name in additional_plugins:\n>>>    17|             info = self.get_plugin_information(plugin_name)\n       18|             print(info)",
        },
        {
            "file": qml_path,
            "line": 22,
            "caller_function": "generate_import_cpp",
            "snippet": "       21|         for plugin_name in additional_plugins:\n>>>    22|             info = self.get_plugin_information(plugin_name)\n       23|             print(info)",
        },
    ]
    assert helper_route == []
    assert print_identifiers == {
        "reads": ["get_plugin_information", "plugin_name", "self"],
        "writes": ["info"],
        "language": "python",
    }
    _assert_trace_codes(print_trace, ["for plugin_name in additional_plugins:"])
    assert print_callers == [
        {
            "file": qml_path,
            "line": 28,
            "caller_function": "main",
            "snippet": '       27|     deploy_util = QmlDeployUtil()\n>>>    28|     deploy_util.print_static_plugins(["alpha"])\n       29|     deploy_util.generate_import_cpp(["beta"])',
        }
    ]
    assert helper_definition == [{"file": qml_path, "line": 6, "kind": "function"}]
    assert generate_identifiers == {
        "reads": ["get_plugin_information", "plugin_name", "self"],
        "writes": ["info"],
        "language": "python",
    }
    _assert_trace_codes(generate_trace, ["for plugin_name in additional_plugins:"])
    assert generate_callers == [
        {
            "file": qml_path,
            "line": 29,
            "caller_function": "main",
            "snippet": '       28|     deploy_util.print_static_plugins(["alpha"])\n>>>    29|     deploy_util.generate_import_cpp(["beta"])',
        }
    ]
    assert generate_route == []


def test_active_finding_python_deploy_subprocess_should_keep_config_classification_and_flag_trace(monkeypatch, tmp_path):
    file_path = "cloud/ams/analytics_server/deploy/build_analytics_model.py"
    source = """\
import os
import subprocess


def build(tensorrt_path, onnx_path, trt_path, calib_dataset=None, calib_cache=None):
    additional_flags = []
    if calib_dataset:
        assert os.path.exists(calib_dataset)
        additional_flags += ["--int8", f"--calibDataset={calib_dataset}"]
    elif calib_cache:
        assert os.path.exists(calib_cache)
        additional_flags += ["--int8", f"--calib={calib_cache}"]

    subprocess.run(
        [
            f"{tensorrt_path}",
            f"--onnx={onnx_path}",
            "--fp16",
            f"--saveEngine={trt_path}",
        ]
        + additional_flags,
        check=True,
    )
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 14)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 14)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 14)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 14, "additional_flags")

    assert classification["type"] == "config"
    assert extracted["meta"]["code_on_line"] == "    subprocess.run("
    assert imports == ["import os", "import subprocess"]
    assert decorators == []
    assert identifiers["reads"] == ["additional_flags", "check", "onnx_path", "run", "subprocess", "tensorrt_path", "trt_path"]
    assert identifiers["writes"] == []
    assert identifiers["language"] == "python"
    assert trace == [
        {
            "line": 12,
            "code": 'additional_flags += ["--int8", f"--calib={calib_cache}"]',
            "writes": ["additional_flags"],
            "reads": ["calib_cache"],
        }
    ]


def test_active_finding_python_pinger_should_keep_executable_and_command_context(monkeypatch, tmp_path):
    file_path = "vms/vms_benchmark/lib/vms_benchmark/pinger.py"
    source = """\
import os
import platform
import subprocess
from pathlib import Path


class Pinger:
    def __init__(self, host):
        if platform.system() == 'Windows':
            _ping_exe = Path(os.environ['WINDIR']).joinpath("System32", "ping.exe")
            self._ping_command = [_ping_exe.as_posix(), "-n", "1", host]

    def ping(self) -> bool:
        completed_proc = subprocess.run(
            self._ping_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        return completed_proc.returncode == 0
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    init_extracted = mcp_server.extract_function("9ce90895", file_path, 11)
    init_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 11)
    init_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 11, "_ping_exe")
    ping_extracted = mcp_server.extract_function("9ce90895", file_path, 14)
    ping_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 14)
    ping_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 14, "self")

    assert init_extracted["meta"]["code_on_line"] == '            self._ping_command = [_ping_exe.as_posix(), "-n", "1", host]'
    assert init_identifiers["reads"] == ["_ping_exe", "as_posix", "host", "self"]
    assert init_identifiers["writes"] == ["_ping_command"]
    assert init_identifiers["language"] == "python"
    assert init_trace == [
        {
            "line": 10,
            "code": '_ping_exe = Path(os.environ[\'WINDIR\']).joinpath("System32", "ping.exe")',
            "writes": ["_ping_exe"],
            "reads": ["Path", "environ", "joinpath", "os"],
        }
    ]
    assert ping_extracted["meta"]["code_on_line"] == "        completed_proc = subprocess.run("
    assert ping_identifiers["reads"] == ["DEVNULL", "_ping_command", "run", "self", "stderr", "stdout", "subprocess"]
    assert ping_identifiers["writes"] == ["completed_proc"]
    assert ping_identifiers["language"] == "python"
    assert ping_trace == []


def test_active_finding_python_file_parsing_helpers_should_keep_path_and_xml_context(monkeypatch, tmp_path):
    deps_path = "open/vms/distribution/common/scripts/generate_deb_dependencies.py"
    deps_source = """\
import argparse
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()
    with open(args.file, "r") as file:
        deps = yaml.load(file, yaml.Loader)
    return deps
"""
    validate_path = "build_utils/translation/validate_translations.py"
    validate_source = """\
import argparse
import xml.etree.ElementTree as ET


def validate_xml(root, path):
    return True


def validate_file(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return validate_xml(root, path)
"""
    merge_wxl_path = "open/vms/distribution/wix/scripts/merge_wxl_files.py"
    merge_wxl_source = """\
from pathlib import Path
import xml.etree.ElementTree as ElementTree


class WxlFile():
    def __init__(self, path):
        self.tree = ElementTree.parse(path)
        self.root = self.tree.getroot()
"""
    team_path = "open/build_utils/macos/team.py"
    team_source = """\
import os
import subprocess
import xml.etree.ElementTree as ET


def parse():
    output = subprocess.check_output(
        ["/usr/libexec/PlistBuddy", "-x", "-c", "print IDEProvisioningTeamByIdentifier",
         f"{os.environ['HOME']}/Library/Preferences/com.apple.dt.Xcode.plist"])
    for e in ET.fromstring(output).findall('dict/array/dict'):
        return e
"""
    axis_path = "vms/server/mediaserver/update_db_scripts/axis_compare.py"
    axis_source = """\
import requests, re, os
import xml.etree.ElementTree as ET

api_key = "apikey example"
headers={"authorization": api_key}
axis_base_url = "https://www.axis.com/api/pia/v2/items"
parameters = ""
axis_url = axis_base_url + parameters
get_list = requests.get(axis_url, headers = headers).json()
f1_path = os.path.abspath(os.getcwd() + "/axis.xml")
tree = ET.parse(f1_path)
"""
    av_path = "vms/server/mediaserver/update_db_scripts/av_compare.py"
    av_source = """\
import re
from xml.dom import minidom

f1_path = "/tmp/av.xml"
arecont_xml = minidom.parse(f1_path)
arecont_xml_models = arecont_xml.getElementsByTagName('resource')
for model in arecont_xml_models:
    match = re.match('\\d+\\w+', model.attributes['name'].value)
"""
    _write_source_tree(tmp_path, deps_path, deps_source)
    _write_source_tree(tmp_path, validate_path, validate_source)
    _write_source_tree(tmp_path, merge_wxl_path, merge_wxl_source)
    _write_source_tree(tmp_path, team_path, team_source)
    _write_source_tree(tmp_path, axis_path, axis_source)
    _write_source_tree(tmp_path, av_path, av_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    deps_identifiers = mcp_server.find_identifiers("9ce90895", deps_path, 10)
    deps_trace = mcp_server.trace_identifier_backward("9ce90895", deps_path, 10, "args")
    validate_identifiers = mcp_server.find_identifiers("9ce90895", validate_path, 10)
    validate_trace = mcp_server.trace_identifier_backward("9ce90895", validate_path, 10, "path")
    merge_identifiers = mcp_server.find_identifiers("9ce90895", merge_wxl_path, 7)
    merge_trace = mcp_server.trace_identifier_backward("9ce90895", merge_wxl_path, 7, "path")
    team_identifiers = mcp_server.find_identifiers("9ce90895", team_path, 10)
    team_trace = mcp_server.trace_identifier_backward("9ce90895", team_path, 10, "output")
    axis_identifiers = mcp_server.find_identifiers("9ce90895", axis_path, 5)
    axis_trace = mcp_server.trace_identifier_backward("9ce90895", axis_path, 5, "api_key")
    av_identifiers = mcp_server.find_identifiers("9ce90895", av_path, 5)
    av_trace = mcp_server.trace_identifier_backward("9ce90895", av_path, 5, "f1_path")

    assert deps_identifiers["reads"] == ["Loader", "file", "load", "yaml"]
    assert deps_identifiers["writes"] == ["deps"]
    assert deps_trace == [
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 6, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert validate_identifiers["reads"] == ["ET", "parse", "path"]
    assert validate_identifiers["writes"] == ["tree"]
    assert validate_trace == []
    assert merge_identifiers["reads"] == ["ElementTree", "parse", "path", "self"]
    assert merge_identifiers["writes"] == ["tree"]
    assert merge_trace == []
    assert team_identifiers["reads"] == ["ET", "findall", "fromstring", "output"]
    assert team_identifiers["writes"] == ["e"]
    assert team_trace == [
        {
            "line": 7,
            "code": "output = subprocess.check_output(",
            "writes": ["output"],
            "reads": ["check_output", "environ", "os", "subprocess"],
        }
    ]
    assert axis_identifiers["reads"] == ["api_key"]
    assert axis_identifiers["writes"] == ["headers"]
    assert axis_trace == [{"line": 4, "code": 'api_key = "apikey example"', "writes": ["api_key"], "reads": []}]
    assert av_identifiers["reads"] == ["f1_path", "minidom", "parse"]
    assert av_identifiers["writes"] == ["arecont_xml"]
    assert av_trace == [{"line": 4, "code": 'f1_path = "/tmp/av.xml"', "writes": ["f1_path"], "reads": []}]


def test_active_finding_python_hash_and_template_helpers_should_keep_content_and_tempfile_context(monkeypatch, tmp_path):
    cache_path = "cloud/storage/analytics_vectorizer/vectorizer/clip_model_cache.py"
    cache_source = """\
import hashlib
import typing
import numpy as np
import PIL.Image


class Cache:
    @staticmethod
    def get_content_hash(content: typing.Union[bytes, str]) -> str:
        if isinstance(content, str):
            return hashlib.md5(content.encode()).hexdigest()
        elif isinstance(content, PIL.Image.Image) or isinstance(content, np.ndarray):
            return hashlib.md5(content.tobytes()).hexdigest()
        else:
            return hashlib.md5(content).hexdigest()
"""
    utils_path = "cloud/ams/model/src/nx/train/utils.py"
    utils_source = """\
import tempfile
import jinja2


def build(datasetRoot):
    with tempfile.NamedTemporaryFile(suffix='.yaml') as data_file:
        with open(data_file.name, mode='w') as f:
            data_conf_str = jinja2.Template(\"\"\"\npath: {{datasetRoot}}\n\"\"\").render({'datasetRoot': datasetRoot})
            f.write(data_conf_str)
"""
    yolov11_path = "cloud/ams/model/src/nx/utils/train/nx_yolov11_train.py"
    yolov11_source = """\
import tempfile
import jinja2

NX_YOLO_MODEL_CONFIG = "model: {{scale}}"


def run(parser, logger):
    args = parser.parse_args()
    with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\
        tempfile.NamedTemporaryFile(suffix='.yaml') as dataFile:
        with open(modelFile.name, mode='w') as f:
            f.write(jinja2.Template(NX_YOLO_MODEL_CONFIG).render({'scale': args.scale}))
        with open(dataFile.name, mode='w') as f:
            dataConfStr = jinja2.Template(\"\"\"\npath: {{datasetRoot}}\nscale: {{scale}}\n\"\"\").render({'datasetRoot': args.dataset_root, 'scale': args.scale})
"""
    _write_source_tree(tmp_path, cache_path, cache_source)
    _write_source_tree(tmp_path, utils_path, utils_source)
    _write_source_tree(tmp_path, yolov11_path, yolov11_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    cache_str_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 11)
    cache_img_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 13)
    cache_bytes_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 15)
    utils_identifiers = mcp_server.find_identifiers("9ce90895", utils_path, 7)
    utils_trace = mcp_server.trace_identifier_backward("9ce90895", utils_path, 7, "data_file")
    model_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 12)
    model_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 12, "f")
    data_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 14)
    data_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 14, "dataFile")

    assert cache_str_identifiers["reads"] == ["content", "encode", "hashlib", "hexdigest", "md5"]
    assert cache_str_identifiers["writes"] == []
    assert cache_img_identifiers["reads"] == ["content", "hashlib", "hexdigest", "md5", "tobytes"]
    assert cache_img_identifiers["writes"] == []
    assert cache_bytes_identifiers["reads"] == ["content", "hashlib", "hexdigest", "md5"]
    assert cache_bytes_identifiers["writes"] == []
    assert utils_identifiers["reads"] == ["Template", "data_conf_str", "data_file", "datasetRoot", "jinja2", "mode", "name", "open", "render", "write"]
    assert utils_identifiers["writes"] == ["f"]
    assert utils_trace == [
        {
            "line": 6,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as data_file:",
            "writes": ["data_file"],
            "reads": ["NamedTemporaryFile", "Template", "data_conf_str", "datasetRoot", "f", "jinja2", "mode", "name", "open", "render", "suffix", "tempfile", "write"],
        }
    ]
    assert model_identifiers["reads"] == ["NX_YOLO_MODEL_CONFIG", "Template", "args", "f", "jinja2", "render", "scale", "write"]
    assert model_identifiers["writes"] == []
    assert model_trace == [
        {
            "line": 11,
            "code": "with open(modelFile.name, mode='w') as f:",
            "writes": ["f"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "Template", "args", "jinja2", "mode", "modelFile", "name", "open", "render", "scale", "write"],
        },
        {
            "line": 9,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\",
            "writes": ["modelFile"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "NamedTemporaryFile", "Template", "args", "dataConfStr", "dataset_root", "f", "jinja2", "mode", "name", "open", "render", "scale", "suffix", "tempfile", "write"],
        },
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert data_identifiers["reads"] == ["Template", "args", "dataset_root", "jinja2", "render", "scale"]
    assert data_identifiers["writes"] == ["dataConfStr"]
    assert data_trace == [
        {
            "line": 9,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\",
            "writes": ["dataFile"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "NamedTemporaryFile", "Template", "args", "dataConfStr", "dataset_root", "f", "jinja2", "mode", "name", "open", "render", "scale", "suffix", "tempfile", "write"],
        },
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]


def test_active_finding_native_crypto_initializers_should_keep_digest_context(monkeypatch, tmp_path):
    node_state_path = "cloud/libs/nx_clusterdb_engine/src/nx/clusterdb/engine/sync/node_state.cpp"
    node_state_source = """\
#include <openssl/md5.h>


std::string hash() {
    MD5_CTX ctx;
    MD5_Init(&ctx);
    return {};
}
"""
    cloud_nonce_path = "open/cloud/cloud_db_client/src/nx/cloud/db/client/cloud_nonce.cpp"
    cloud_nonce_source = """\
#include <openssl/md5.h>


void calcNonceHash() {
    MD5_CTX md5Ctx;
    MD5_Init(&md5Ctx);
}
"""
    crypto_hash_path = "open/libs/nx_utils/src/nx/utils/cryptographic_hash.cpp"
    crypto_hash_source = """\
#include <openssl/md4.h>
#include <openssl/md5.h>
#include <openssl/sha.h>


class QnMd4CryptographicHashPrivate
{
public:
    virtual void init() override { MD4_Init(&ctx); }
};


class QnMd5CryptographicHashPrivate
{
public:
    virtual void init() override { MD5_Init(&ctx); }
};


class QnSha1CryptographicHashPrivate
{
public:
    virtual void init() override { SHA1_Init(&ctx); }
};
"""
    certificate_path = "open/libs/nx_network/src/nx/network/ssl/certificate.cpp"
    certificate_source = """\
void useDigest() {
    const auto digest = EVP_sha1();
}
"""
    auth_utils_path = "open/libs/nx_utils/src/nx/utils/auth/utils.cpp"
    auth_utils_source = """\
void initHmac(Key key) {
    auto ctx = nx::wrapUnique(HMAC_CTX_new(), &HMAC_CTX_free);
    HMAC_Init_ex(ctx.get(), key.data(), key.size(), EVP_sha1(), nullptr);
}
"""
    nxai_crypto_path = "vms/server/plugins/analytics/nx_ai_manager_plugin/plugin/src/nxai_crypto.cpp"
    nxai_crypto_source = """\
FILE* calculate_hash(FILE* file) {
    auto mdctx = EVP_MD_CTX_new();
    if (1 != EVP_DigestInit_ex(mdctx, EVP_md5(), NULL))
    {
        hash_cleanup(file, mdctx);
        return NULL;
    }
    return file;
}
"""
    _write_source_tree(tmp_path, node_state_path, node_state_source)
    _write_source_tree(tmp_path, cloud_nonce_path, cloud_nonce_source)
    _write_source_tree(tmp_path, crypto_hash_path, crypto_hash_source)
    _write_source_tree(tmp_path, certificate_path, certificate_source)
    _write_source_tree(tmp_path, auth_utils_path, auth_utils_source)
    _write_source_tree(tmp_path, nxai_crypto_path, nxai_crypto_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 163 `MD5_Init(&ctx);` -> fixture line 6
    # live line 42 `MD5_Init(&md5Ctx);` -> fixture line 6
    # live line 53 `virtual void init() override { MD5_Init(&ctx); }` -> fixture line 16
    # live line 413 `const auto digest = EVP_sha1();` -> fixture line 2
    # live line 147 `HMAC_Init_ex(ctx.get(), key.data(), key.size(), EVP_sha1(), nullptr);` -> fixture line 3
    # live line 417 `if (1 != EVP_DigestInit_ex(mdctx, EVP_md5(), NULL))` -> fixture line 3
    node_identifiers = mcp_server.find_identifiers("9ce90895", node_state_path, 6)
    node_trace = mcp_server.trace_identifier_backward("9ce90895", node_state_path, 6, "ctx")
    cloud_nonce_identifiers = mcp_server.find_identifiers("9ce90895", cloud_nonce_path, 6)
    cloud_nonce_trace = mcp_server.trace_identifier_backward("9ce90895", cloud_nonce_path, 6, "md5Ctx")
    crypto_md5_identifiers = mcp_server.find_identifiers("9ce90895", crypto_hash_path, 16)
    crypto_md5_trace = mcp_server.trace_identifier_backward("9ce90895", crypto_hash_path, 16, "ctx")
    crypto_sha1_identifiers = mcp_server.find_identifiers("9ce90895", crypto_hash_path, 23)
    crypto_sha1_trace = mcp_server.trace_identifier_backward("9ce90895", crypto_hash_path, 23, "ctx")
    certificate_identifiers = mcp_server.find_identifiers("9ce90895", certificate_path, 2)
    certificate_trace = mcp_server.trace_identifier_backward("9ce90895", certificate_path, 2, "EVP_sha1")
    auth_utils_identifiers = mcp_server.find_identifiers("9ce90895", auth_utils_path, 3)
    auth_utils_trace = mcp_server.trace_identifier_backward("9ce90895", auth_utils_path, 3, "ctx")
    nxai_identifiers = mcp_server.find_identifiers("9ce90895", nxai_crypto_path, 3)
    nxai_file_trace = mcp_server.trace_identifier_backward("9ce90895", nxai_crypto_path, 3, "file")
    nxai_mdctx_trace = mcp_server.trace_identifier_backward("9ce90895", nxai_crypto_path, 3, "mdctx")

    assert node_identifiers == {"reads": ["MD5_Init", "ctx"], "writes": [], "language": "cpp"}
    _assert_trace_codes(node_trace, ["MD5_CTX ctx;"])
    assert cloud_nonce_identifiers == {"reads": ["MD5_Init", "md5Ctx"], "writes": [], "language": "cpp"}
    _assert_trace_codes(cloud_nonce_trace, ["MD5_CTX md5Ctx;"])
    assert crypto_md5_identifiers == {"reads": ["MD5_Init", "ctx"], "writes": ["init"], "language": "cpp"}
    assert crypto_md5_trace == []
    assert crypto_sha1_identifiers == {"reads": ["SHA1_Init", "ctx"], "writes": ["init"], "language": "cpp"}
    assert crypto_sha1_trace == []
    assert certificate_identifiers == {"reads": ["EVP_sha1"], "writes": ["digest"], "language": "cpp"}
    assert certificate_trace == []
    assert auth_utils_identifiers == {
        "reads": ["EVP_sha1", "HMAC_Init_ex", "ctx", "data", "get", "key", "size"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(auth_utils_trace, ["auto ctx = nx::wrapUnique(HMAC_CTX_new(), &HMAC_CTX_free);"])
    assert nxai_identifiers == {
        "reads": ["EVP_DigestInit_ex", "EVP_md5", "file", "hash_cleanup", "mdctx"],
        "writes": [],
        "language": "cpp",
    }
    assert nxai_file_trace == []
    _assert_trace_codes(nxai_mdctx_trace, ["auto mdctx = EVP_MD_CTX_new();"])


def test_active_finding_native_buffer_arithmetic_should_keep_offset_context(monkeypatch, tmp_path):
    buffered_path = "open/libs/nx_network/src/nx/network/buffered_stream_socket.cpp"
    buffered_source = """\
int readSome() {
    const auto internalSize = std::min(m_internalRecvBuffer.size(), bufferLen);
    int recv = m_socket->recv((char*)buffer + internalSize, bufferLen - internalSize, flags);
    return (int) ((recv < 0) ? internalSize : internalSize + recv);
}
"""
    rtsp_path = "open/vms/libs/nx_vms_common/src/nx/streaming/rtsp_client.cpp"
    rtsp_source = """\
bool process() {
    int bytesRead = readSocketWithBuffering(m_responseBuffer+m_responseBufferLen, qMin(1024, RTSP_BUFFER_LEN - m_responseBufferLen), true);
    m_responseBufferLen += bytesRead;
    int maxChannelNumber = m_rtpToTrack.size() - 1;
    const auto messageSize = nextRtspMessage(m_responseBuffer, m_responseBufferLen, maxChannelNumber);
    memmove(m_responseBuffer, m_responseBuffer + messageSize, m_responseBufferLen - messageSize);
    return true;
}
"""
    modbus_path = "vms/server/nx_vms_server/src/modbus/modbus_client.cpp"
    modbus_source = """\
int receive() {
    const auto bytesRead = m_socket->recv(m_recvBuffer + totalBytesRead, kBufferSize - totalBytesRead);
    return bytesRead;
}
"""
    tftp_path = "vms/server/nx_vms_server/src/plugins/resource/arecontvision/tools/simple_tftp_client.cpp"
    tftp_source = """\
void handle() {
    blk_cam_sending = buff_recv[2]*256 + buff_recv[3];
    len_recv = m_sock->recv(buff_recv, sizeof(buff_recv), 0);
    int data_len = len_recv-4;
    data.writeAt((char*)buff_recv+4, data_len, (blk_cam_sending-1)*m_curr_blk_size + data_size0);
}
"""
    proxy_path = "vms/server/nx_vms_server/src/proxy/2wayaudio/proxy_audio_receiver.cpp"
    proxy_source = """\
void parse() {
    static const QByteArray kDelimiter("\\r\\n\\r\\n");
    delimiterPos += kDelimiter.length();
    int bytesLeft = bytesRead - delimiterPos;
    memcpy(outPayloadBuffer->data(), headersBuffer + delimiterPos, bytesLeft);
}
"""
    nxai_socket_path = "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_socket_utils.cpp"
    nxai_socket_source = """\
void read_socket() {
    int flags = 0;
    char* new_pointer = realloc(*message_input_buffer, *message_length);
    *message_input_buffer = new_pointer;
    int num_read = recv(
        connection_fd,
        (*message_input_buffer) + num_read_cumulative,
        *message_length,
        flags);
}
"""
    _write_source_tree(tmp_path, buffered_path, buffered_source)
    _write_source_tree(tmp_path, rtsp_path, rtsp_source)
    _write_source_tree(tmp_path, modbus_path, modbus_source)
    _write_source_tree(tmp_path, tftp_path, tftp_source)
    _write_source_tree(tmp_path, proxy_path, proxy_source)
    _write_source_tree(tmp_path, nxai_socket_path, nxai_socket_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 70 `return (int) ((recv < 0) ? internalSize : internalSize + recv);` -> fixture line 4
    # live line 1284 `memmove(m_responseBuffer, m_responseBuffer + messageSize, m_responseBufferLen - messageSize);` -> fixture line 6
    # live line 150 `const auto bytesRead = m_socket->recv(m_recvBuffer + totalBytesRead, kBufferSize - totalBytesRead);` -> fixture line 2
    # live line 168 `data.writeAt((char*)buff_recv+4, data_len, (blk_cam_sending-1)*m_curr_blk_size + data_size0);` -> fixture line 5
    # live line 54 `memcpy(outPayloadBuffer->data(), headersBuffer + delimiterPos, bytesLeft);` -> fixture line 5
    # live line 402 `(*message_input_buffer) + num_read_cumulative,` -> fixture line 6
    buffered_identifiers = mcp_server.find_identifiers("9ce90895", buffered_path, 4)
    buffered_internal_trace = mcp_server.trace_identifier_backward("9ce90895", buffered_path, 4, "internalSize")
    buffered_recv_trace = mcp_server.trace_identifier_backward("9ce90895", buffered_path, 4, "recv")
    rtsp_identifiers = mcp_server.find_identifiers("9ce90895", rtsp_path, 6)
    rtsp_len_trace = mcp_server.trace_identifier_backward("9ce90895", rtsp_path, 6, "m_responseBufferLen")
    rtsp_size_trace = mcp_server.trace_identifier_backward("9ce90895", rtsp_path, 6, "messageSize")
    modbus_identifiers = mcp_server.find_identifiers("9ce90895", modbus_path, 2)
    tftp_identifiers = mcp_server.find_identifiers("9ce90895", tftp_path, 5)
    tftp_block_trace = mcp_server.trace_identifier_backward("9ce90895", tftp_path, 5, "blk_cam_sending")
    tftp_data_len_trace = mcp_server.trace_identifier_backward("9ce90895", tftp_path, 5, "data_len")
    proxy_identifiers = mcp_server.find_identifiers("9ce90895", proxy_path, 5)
    proxy_bytes_left_trace = mcp_server.trace_identifier_backward("9ce90895", proxy_path, 5, "bytesLeft")
    nxai_identifiers = mcp_server.find_identifiers("9ce90895", nxai_socket_path, 6)
    nxai_flags_trace = mcp_server.trace_identifier_backward("9ce90895", nxai_socket_path, 6, "flags")
    nxai_buffer_trace = mcp_server.trace_identifier_backward("9ce90895", nxai_socket_path, 6, "message_input_buffer")

    assert buffered_identifiers == {"reads": ["internalSize", "recv"], "writes": [], "language": "cpp"}
    _assert_trace_codes(buffered_internal_trace, ["const auto internalSize = std::min(m_internalRecvBuffer.size(), bufferLen);"])
    _assert_trace_codes(
        buffered_recv_trace,
        [
            "int recv = m_socket->recv((char*)buffer + internalSize, bufferLen - internalSize, flags);",
            "const auto internalSize = std::min(m_internalRecvBuffer.size(), bufferLen);",
        ],
    )
    assert rtsp_identifiers == {
        "reads": ["m_responseBuffer", "m_responseBufferLen", "memmove", "messageSize"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(
        rtsp_len_trace,
        [
            "m_responseBufferLen += bytesRead;",
            "int bytesRead = readSocketWithBuffering(m_responseBuffer+m_responseBufferLen, qMin(1024, RTSP_BUFFER_LEN - m_responseBufferLen), true);",
        ],
    )
    _assert_trace_codes(
        rtsp_size_trace,
        [
            "const auto messageSize = nextRtspMessage(m_responseBuffer, m_responseBufferLen, maxChannelNumber);",
            "int maxChannelNumber = m_rtpToTrack.size() - 1;",
        ],
    )
    assert modbus_identifiers == {
        "reads": ["kBufferSize", "m_recvBuffer", "m_socket", "recv", "totalBytesRead"],
        "writes": ["bytesRead"],
        "language": "cpp",
    }
    assert tftp_identifiers == {
        "reads": ["blk_cam_sending", "buff_recv", "data", "data_len", "data_size0", "m_curr_blk_size", "writeAt"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(tftp_block_trace, ["blk_cam_sending = buff_recv[2]*256 + buff_recv[3];"])
    _assert_trace_codes(
        tftp_data_len_trace,
        [
            "int data_len = len_recv-4;",
            "len_recv = m_sock->recv(buff_recv, sizeof(buff_recv), 0);",
        ],
    )
    assert proxy_identifiers == {
        "reads": ["bytesLeft", "data", "delimiterPos", "headersBuffer", "memcpy", "outPayloadBuffer"],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(
        proxy_bytes_left_trace,
        [
            "int bytesLeft = bytesRead - delimiterPos;",
            "delimiterPos += kDelimiter.length();",
            'static const QByteArray kDelimiter("\\r\\n\\r\\n");',
        ],
    )
    assert nxai_identifiers == {
        "reads": ["connection_fd", "flags", "message_input_buffer", "message_length", "num_read_cumulative", "recv"],
        "writes": ["num_read"],
        "language": "cpp",
    }
    _assert_trace_codes(nxai_flags_trace, ["int flags = 0;"])
    _assert_trace_codes(
        nxai_buffer_trace,
        [
            "*message_input_buffer = new_pointer;",
            "char* new_pointer = realloc(*message_input_buffer, *message_length);",
        ],
    )


def test_active_finding_native_multiline_buffer_parser_should_keep_pointer_context(monkeypatch, tmp_path):
    tcp_processor_path = "open/vms/libs/nx_vms_common/src/network/tcp_connection_processor.cpp"
    tcp_processor_source = """\
bool parse(Data* d) {
    size_t bytesParsed = 0;
    if (!d->httpStreamReader.parseBytes(
        nx::ConstBufferRefType(
            d->interleavedMessageData.data() + d->interleavedMessageDataPos,
            d->interleavedMessageData.size() - d->interleavedMessageDataPos),
        &bytesParsed) ||
        (d->httpStreamReader.state() ==
            nx::network::http::HttpStreamReader::ReadState::parseError))
    {
        return false;
    }
    return true;
}
"""
    _write_source_tree(tmp_path, tcp_processor_path, tcp_processor_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 656 `d->interleavedMessageData.data() + d->interleavedMessageDataPos,` -> fixture line 5
    tcp_identifiers = mcp_server.find_identifiers("9ce90895", tcp_processor_path, 5)
    tcp_bytes_parsed_trace = mcp_server.trace_identifier_backward("9ce90895", tcp_processor_path, 5, "bytesParsed")
    tcp_d_trace = mcp_server.trace_identifier_backward("9ce90895", tcp_processor_path, 5, "d")
    tcp_data_trace = mcp_server.trace_identifier_backward("9ce90895", tcp_processor_path, 5, "data")

    assert tcp_identifiers == {
        "reads": [
            "ConstBufferRefType",
            "bytesParsed",
            "d",
            "data",
            "httpStreamReader",
            "interleavedMessageData",
            "interleavedMessageDataPos",
            "parseBytes",
            "parseError",
            "size",
            "state",
        ],
        "writes": [],
        "language": "cpp",
    }
    _assert_trace_codes(tcp_bytes_parsed_trace, ["size_t bytesParsed = 0;"])
    assert tcp_d_trace == []
    assert tcp_data_trace == []


def test_active_finding_python_file_io_and_fallback_paths_should_keep_open_context(monkeypatch, tmp_path):
    monitoring_path = "cloud/infra/monitoring/monitoring_simple/simple.py"
    monitoring_source = """\
import requests
from contextlib import contextmanager
from requests.auth import HTTPDigestAuth

ADMIN_PASS = "admin"
DEFAULT_LOGIN = "admin"


@contextmanager
def run(mediaserver_ip):
    r = requests_retry_session().post('http://{}:7001/api/setupLocalSystem'.format(mediaserver_ip),
                                      params={'systemName': 'monitoring',
                                              'password': ADMIN_PASS},
                                      auth=requests.auth.HTTPDigestAuth(DEFAULT_LOGIN, 'admin'))
    yield r
"""
    embed_path = "build_utils/code_signing/embed_zip_signature.py"
    embed_source = """\
def signature_string_from_file(prefix, file):
    with open(file) as f:
        return prefix + \":\" + f.read()
"""
    preprocess_path = "build_utils/email_templates/preprocess.py"
    preprocess_source = """\
from pathlib import Path


def generate_file(source_file: Path, target_file: Path, transformer):
    text = open(source_file).read()
    if transformer:
        text = transformer.transform(text) + '\\n'
"""
    after_fetch_path = "build_utils/python/run_after_fetch.py"
    after_fetch_source = """\
from pathlib import Path
import re


def have_to_run_script(sources_dir, script_name):
    git_root_path = Path(sources_dir).joinpath('.git')
    with open(git_root_path) as f:
        git_root_path_file_content = f.readline().rstrip()
    git_info_path = Path(sources_dir).joinpath('git_info.txt')
    with open(git_info_path) as f:
        content = f.readlines()
        for line in content:
            match = re.match(r'^fetchTimestampS=(?P<fetch_timestamp>[\\d\\.,]+)', line)
            if match:
                return float(match['fetch_timestamp'].replace(',', '.'))
"""
    replace_path = "build_utils/replace_in_file.py"
    replace_source = """\
import argparse


def main(parser):
    args = parser.parse_args()
    replacement_string = bytes(args.replacement_string)
    for file_name in args.files:
        with open(file_name, 'rb') as f:
            data = f.read()
"""
    deploy_path = "cloud/ams/analytics_server/deploy/build_analytics_model.py"
    deploy_source = """\
import json


def prepare_json_config(config_json: str, output_dir: str) -> dict:
    with open(config_json, 'r') as f:
        config_data = json.load(f)
    return config_data
"""
    _write_source_tree(tmp_path, monitoring_path, monitoring_source)
    _write_source_tree(tmp_path, embed_path, embed_source)
    _write_source_tree(tmp_path, preprocess_path, preprocess_source)
    _write_source_tree(tmp_path, after_fetch_path, after_fetch_source)
    _write_source_tree(tmp_path, replace_path, replace_source)
    _write_source_tree(tmp_path, deploy_path, deploy_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    monitoring_classification = mcp_server.classify_file("9ce90895", monitoring_path)
    monitoring_identifiers = mcp_server.find_identifiers("9ce90895", monitoring_path, 12)
    monitoring_decorators = mcp_server.find_decorators("9ce90895", monitoring_path, 12)
    embed_identifiers = mcp_server.find_identifiers("9ce90895", embed_path, 2)
    preprocess_identifiers = mcp_server.find_identifiers("9ce90895", preprocess_path, 5)
    after_fetch_git_identifiers = mcp_server.find_identifiers("9ce90895", after_fetch_path, 8)
    after_fetch_git_trace = mcp_server.trace_identifier_backward("9ce90895", after_fetch_path, 8, "git_root_path")
    after_fetch_info_identifiers = mcp_server.find_identifiers("9ce90895", after_fetch_path, 10)
    after_fetch_info_trace = mcp_server.trace_identifier_backward("9ce90895", after_fetch_path, 10, "git_info_path")
    replace_identifiers = mcp_server.find_identifiers("9ce90895", replace_path, 7)
    replace_trace = mcp_server.trace_identifier_backward("9ce90895", replace_path, 7, "file_name")
    deploy_classification = mcp_server.classify_file("9ce90895", deploy_path)
    deploy_identifiers = mcp_server.find_identifiers("9ce90895", deploy_path, 5)

    assert monitoring_classification["type"] == "config"
    assert monitoring_decorators == ["@contextmanager"]
    assert monitoring_identifiers["reads"] == [
        "ADMIN_PASS",
        "DEFAULT_LOGIN",
        "HTTPDigestAuth",
        "auth",
        "format",
        "mediaserver_ip",
        "params",
        "post",
        "requests",
        "requests_retry_session",
    ]
    assert monitoring_identifiers["writes"] == ["r"]
    assert embed_identifiers["reads"] == ["file", "open", "prefix", "read"]
    assert embed_identifiers["writes"] == ["f"]
    assert preprocess_identifiers["reads"] == ["open", "read", "source_file"]
    assert preprocess_identifiers["writes"] == ["text"]
    assert after_fetch_git_identifiers["reads"] == ["f", "readline", "rstrip"]
    assert after_fetch_git_identifiers["writes"] == ["git_root_path_file_content"]
    assert after_fetch_git_trace == [
        {"line": 6, "code": "git_root_path = Path(sources_dir).joinpath('.git')", "writes": ["git_root_path"], "reads": ["Path", "joinpath", "sources_dir"]}
    ]
    assert after_fetch_info_identifiers["reads"] == ["content", "float", "git_info_path", "line", "match", "open", "re", "readlines", "replace"]
    assert after_fetch_info_identifiers["writes"] == ["f"]
    assert after_fetch_info_trace == [
        {"line": 9, "code": "git_info_path = Path(sources_dir).joinpath('git_info.txt')", "writes": ["git_info_path"], "reads": ["Path", "joinpath", "sources_dir"]}
    ]
    assert replace_identifiers["reads"] == ["args", "data", "f", "files", "open", "read"]
    assert replace_identifiers["writes"] == ["file_name"]
    assert replace_trace == [
        {"line": 7, "code": "for file_name in args.files:", "writes": ["file_name"], "reads": ["args", "data", "f", "files", "open", "read"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert deploy_classification["type"] == "config"
    assert deploy_identifiers["reads"] == ["config_data", "config_json", "json", "load", "open"]
    assert deploy_identifiers["writes"] == ["f"]


def test_active_finding_python_reader_and_loader_helpers_should_keep_argument_context(monkeypatch, tmp_path):
    tao_path = "cloud/ams/model/src/nx/utils/dataset/converters/tao_to_labelme.py"
    tao_source = """\
import pathlib
import json


def load(images_root, annotations_file, logger, AnnFile):
    files = {}
    for path in pathlib.Path(images_root).rglob('*.jpg'):
        files[str(path)] = AnnFile(image_file=path.relative_to(images_root), segments=[])
        logger.debug("Found image file: " + str(path))
    with open(annotations_file, 'r') as ann_file:
        file_content = ann_file.read()
        annotations_obj = json.loads(file_content)
    return annotations_obj
"""
    profiler_path = "cloud/ams/utils/trtexec/profiler.py"
    profiler_source = """\
import json


def main(args, features, hasNames, mergeHeaders, allFeatures):
    count = args.gp and not hasNames(features)
    profile = None
    reference = None
    with open(args.name) as f:
        profile = json.load(f)
        profileCount = profile[0][\"count\"]
        profile = profile[1:]
    if args.reference:
        with open(args.reference) as f:
            reference = json.load(f)
            referenceCount = reference[0][\"count\"]
            reference = reference[1:]
        allFeatures = mergeHeaders(allFeatures)
"""
    tracer_path = "cloud/ams/utils/trtexec/tracer.py"
    tracer_source = """\
import json


def main(args, pu, allMetrics):
    metrics = args.metrics.split(\",\")
    count = args.gp and (len(metrics) == 1)
    if not args.no_header:
        pu.printHeader(allMetrics, metrics, args.gp, count)
    with open(args.name) as f:
        trace = json.load(f)
    return trace
"""
    _write_source_tree(tmp_path, tao_path, tao_source)
    _write_source_tree(tmp_path, profiler_path, profiler_source)
    _write_source_tree(tmp_path, tracer_path, tracer_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    tao_identifiers = mcp_server.find_identifiers("9ce90895", tao_path, 10)
    tao_trace = mcp_server.trace_identifier_backward("9ce90895", tao_path, 10, "annotations_file")
    profile_identifiers = mcp_server.find_identifiers("9ce90895", profiler_path, 8)
    profile_trace = mcp_server.trace_identifier_backward("9ce90895", profiler_path, 8, "args")
    reference_identifiers = mcp_server.find_identifiers("9ce90895", profiler_path, 13)
    reference_trace = mcp_server.trace_identifier_backward("9ce90895", profiler_path, 13, "args")
    tracer_identifiers = mcp_server.find_identifiers("9ce90895", tracer_path, 9)
    tracer_trace = mcp_server.trace_identifier_backward("9ce90895", tracer_path, 9, "args")

    assert tao_identifiers["reads"] == ["annotations_file", "annotations_obj", "file_content", "json", "loads", "open", "read"]
    assert tao_identifiers["writes"] == ["ann_file"]
    assert tao_trace == []
    assert profile_identifiers["reads"] == ["args", "json", "load", "name", "open", "profile", "profileCount"]
    assert profile_identifiers["writes"] == ["f"]
    assert profile_trace == []
    assert reference_identifiers["reads"] == ["args", "json", "load", "open", "reference", "referenceCount"]
    assert reference_identifiers["writes"] == ["f"]
    assert reference_trace == []
    assert tracer_identifiers["reads"] == ["args", "json", "load", "name", "open", "trace"]
    assert tracer_identifiers["writes"] == ["f"]
    assert tracer_trace == []


def test_active_finding_python_conversion_and_writeback_helpers_should_keep_path_context(monkeypatch, tmp_path):
    json_to_cmake_path = "open/build_utils/json_to_cmake.py"
    json_to_cmake_source = """\
import json


def parse_dict(data, prefix=None):
    return data


def convert_json_file_to_cmake_file(json_file_name, cmake_file_name, prefix=None):
    with open(json_file_name, encoding=\"utf-8\") as json_file:
        variables = parse_dict(json.load(json_file), prefix=prefix)
    with open(cmake_file_name, \"w\", encoding=\"utf-8\") as cmake_file:
        return variables
"""
    replace_qt_path = "open/build_utils/msvc/replace_conan_qt_path.py"
    replace_qt_source = """\
import json
import os
from pathlib import Path


def patch(file, qtdir):
    binaries_dir = (Path(qtdir) / 'bin').as_posix()
    with open(file, 'r', encoding='utf-8-sig') as source:
        json_root = json.load(source)
    return json_root, binaries_dir
"""
    yaml2json_path = "open/build_utils/yaml2json.py"
    yaml2json_source = """\
import argparse
import json
import yaml


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    with open(args.input, 'r') as input:
        with open(args.output, 'w') as output:
            json.dump(yaml.safe_load(input), output, indent=4)
"""
    generate_path = "open/vms/server/plugins/analytics/stub_analytics_plugin/object_streamer_files/generate.py"
    generate_source = """\
import json
from pathlib import Path


def load_config(config_file: Path):
    with open(config_file, encoding='UTF-8') as config:
        return json.load(config)
"""
    preprocess_path = "build_utils/email_templates/preprocess.py"
    preprocess_source = """\
from pathlib import Path


def generate_file(target_file: Path, text):
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, 'w', encoding=\"utf-8\", newline='\\n') as f:
        f.write(text)
"""
    labelme_path = "cloud/ams/model/src/nx/utils/dataset/converters/labelme_to_yolo.py"
    labelme_source = """\
import pathlib


def save(json_file, segments):
    result_yolo_file = str(json_file.parent / pathlib.Path(json_file.stem + \".txt\"))
    with open(result_yolo_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            f.write(str(segment))
"""
    dumpwts_path = "cloud/ams/utils/trtexec/src/dumpTFWts.py"
    dumpwts_source = """\
def main(opt):
    outputbase = opt.output
    outputFileName = outputbase + \".wts2\"
    outputFile = open(outputFileName, \"w\")
    return outputFile
"""
    _write_source_tree(tmp_path, json_to_cmake_path, json_to_cmake_source)
    _write_source_tree(tmp_path, replace_qt_path, replace_qt_source)
    _write_source_tree(tmp_path, yaml2json_path, yaml2json_source)
    _write_source_tree(tmp_path, generate_path, generate_source)
    _write_source_tree(tmp_path, preprocess_path, preprocess_source)
    _write_source_tree(tmp_path, labelme_path, labelme_source)
    _write_source_tree(tmp_path, dumpwts_path, dumpwts_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    json_to_cmake_identifiers = mcp_server.find_identifiers("9ce90895", json_to_cmake_path, 9)
    json_to_cmake_trace = mcp_server.trace_identifier_backward("9ce90895", json_to_cmake_path, 9, "json_file_name")
    replace_qt_identifiers = mcp_server.find_identifiers("9ce90895", replace_qt_path, 8)
    replace_qt_trace = mcp_server.trace_identifier_backward("9ce90895", replace_qt_path, 8, "file")
    yaml2json_identifiers = mcp_server.find_identifiers("9ce90895", yaml2json_path, 9)
    yaml2json_trace = mcp_server.trace_identifier_backward("9ce90895", yaml2json_path, 9, "args")
    generate_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 6)
    generate_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 6, "config_file")
    preprocess_identifiers = mcp_server.find_identifiers("9ce90895", preprocess_path, 6)
    preprocess_trace = mcp_server.trace_identifier_backward("9ce90895", preprocess_path, 6, "target_file")
    labelme_identifiers = mcp_server.find_identifiers("9ce90895", labelme_path, 6)
    labelme_trace = mcp_server.trace_identifier_backward("9ce90895", labelme_path, 6, "result_yolo_file")
    dumpwts_identifiers = mcp_server.find_identifiers("9ce90895", dumpwts_path, 4)
    dumpwts_trace = mcp_server.trace_identifier_backward("9ce90895", dumpwts_path, 4, "outputFileName")

    assert json_to_cmake_identifiers["reads"] == ["encoding", "json", "json_file_name", "load", "open", "parse_dict", "prefix", "variables"]
    assert json_to_cmake_identifiers["writes"] == ["json_file"]
    assert json_to_cmake_trace == []
    assert replace_qt_identifiers["reads"] == ["encoding", "file", "json", "json_root", "load", "open"]
    assert replace_qt_identifiers["writes"] == ["source"]
    assert replace_qt_trace == []
    assert yaml2json_identifiers["reads"] == ["args", "dump", "indent", "json", "open", "output", "safe_load", "yaml"]
    assert yaml2json_identifiers["writes"] == ["input"]
    assert yaml2json_trace == [
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 7, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert generate_identifiers["reads"] == ["config_file", "encoding", "json", "load", "open"]
    assert generate_identifiers["writes"] == ["config"]
    assert generate_trace == []
    assert preprocess_identifiers["reads"] == ["encoding", "newline", "open", "target_file", "text", "write"]
    assert preprocess_identifiers["writes"] == ["f"]
    assert preprocess_trace == []
    assert labelme_identifiers["reads"] == ["encoding", "open", "result_yolo_file", "segment", "segments", "str", "write"]
    assert labelme_identifiers["writes"] == ["f"]
    assert labelme_trace == [{"line": 5, "code": 'result_yolo_file = str(json_file.parent / pathlib.Path(json_file.stem + ".txt"))', "writes": ["result_yolo_file"], "reads": ["Path", "json_file", "parent", "pathlib", "stem", "str"]}]
    assert dumpwts_identifiers["reads"] == ["open", "outputFileName"]
    assert dumpwts_identifiers["writes"] == ["outputFile"]
    assert dumpwts_trace == [
        {"line": 3, "code": 'outputFileName = outputbase + ".wts2"', "writes": ["outputFileName"], "reads": ["outputbase"]},
        {"line": 2, "code": "outputbase = opt.output", "writes": ["outputbase"], "reads": ["opt", "output"]},
    ]


def test_active_finding_python_ninja_and_misc_open_helpers_should_keep_file_binding_context(monkeypatch, tmp_path):
    ninja_path = "open/build_utils/ninja/ninja_tool.py"
    ninja_source = """\
from pathlib import Path

PERSISTENT_KNOWN_FILES_FILE_NAME = "known.txt"


def update_persistent_known_files_file(build_dir, directories):
    persistent_known_files = build_dir / PERSISTENT_KNOWN_FILES_FILE_NAME
    if persistent_known_files.is_file():
        with open(persistent_known_files) as f:
            current_files = [Path(name) for name in f.read().splitlines()]
    else:
        current_files = []
    with open(persistent_known_files, "w") as f:
        f.writelines([])


def generate_list_of_targets_affected_by_listed_files(build_dir, changed_files_list_file_name, affected_targets_list_file_name):
    with open(build_dir / changed_files_list_file_name) as f:
        files = f.read().splitlines()
    try:
        with open(build_dir / affected_targets_list_file_name) as f:
            old_targets = set([l.rstrip() for l in f.readlines()])
    except:
        old_targets = None
    return files, old_targets
"""
    remove_docs_path = "open/build_utils/remove_proprietary_docs.py"
    remove_docs_source = """\
import argparse


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    with open(args.input, "rb") as f:
        data = f.read().decode('utf-8')
    return data
"""
    signtool_path = "open/build_utils/signtool/signtool.py"
    signtool_source = """\
import yaml


def sign_file(config_file):
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config
"""
    signtool_client_path = "build_utils/code_signing/signtool_client.py"
    signtool_client_source = """\
import argparse


def main(client):
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    client.load_arguments(args)
"""
    replace_path = "build_utils/replace_in_file.py"
    replace_source = """\
import argparse


def main(parser):
    args = parser.parse_args()
    replacement_string = bytes(args.replacement_string)
    for file_name in args.files:
        data = b\"payload\"
        with open(file_name, "wb") as f:
            f.write(data)
"""
    _write_source_tree(tmp_path, ninja_path, ninja_source)
    _write_source_tree(tmp_path, remove_docs_path, remove_docs_source)
    _write_source_tree(tmp_path, signtool_path, signtool_source)
    _write_source_tree(tmp_path, signtool_client_path, signtool_client_source)
    _write_source_tree(tmp_path, replace_path, replace_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    ninja_known_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 8)
    ninja_known_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 8, "persistent_known_files")
    ninja_changed_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 17)
    ninja_changed_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 17, "changed_files_list_file_name")
    ninja_affected_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 20)
    ninja_affected_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 20, "affected_targets_list_file_name")
    remove_docs_identifiers = mcp_server.find_identifiers("9ce90895", remove_docs_path, 7)
    remove_docs_trace = mcp_server.trace_identifier_backward("9ce90895", remove_docs_path, 7, "args")
    signtool_identifiers = mcp_server.find_identifiers("9ce90895", signtool_path, 5)
    signtool_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_path, 5, "config_file")
    signtool_client_identifiers = mcp_server.find_identifiers("9ce90895", signtool_client_path, 6)
    signtool_client_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_client_path, 6, "args")
    replace_identifiers = mcp_server.find_identifiers("9ce90895", replace_path, 8)
    replace_trace = mcp_server.trace_identifier_backward("9ce90895", replace_path, 8, "file_name")

    assert ninja_known_identifiers["reads"] == ["Path", "is_file", "name", "open", "persistent_known_files", "read", "splitlines"]
    assert ninja_known_identifiers["writes"] == ["current_files", "f"]
    assert ninja_known_trace == [{"line": 7, "code": "persistent_known_files = build_dir / PERSISTENT_KNOWN_FILES_FILE_NAME", "writes": ["persistent_known_files"], "reads": ["PERSISTENT_KNOWN_FILES_FILE_NAME", "build_dir"]}]
    assert ninja_changed_identifiers["reads"] == ["f", "files", "l", "old_targets", "open", "read", "readlines", "rstrip", "set", "splitlines"]
    assert ninja_changed_identifiers["writes"] == ["affected_targets_list_file_name", "build_dir", "changed_files_list_file_name", "generate_list_of_targets_affected_by_listed_files"]
    assert ninja_changed_trace == []
    assert ninja_affected_identifiers["reads"] == []
    assert ninja_affected_identifiers["writes"] == []
    assert ninja_affected_trace == []
    assert remove_docs_identifiers["reads"] == ["args", "data", "decode", "input", "open", "read"]
    assert remove_docs_identifiers["writes"] == ["f"]
    assert remove_docs_trace == [
        {"line": 6, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 5, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert signtool_identifiers["reads"] == ["config", "config_file", "open", "safe_load", "yaml"]
    assert signtool_identifiers["writes"] == ["f"]
    assert signtool_trace == []
    assert signtool_client_identifiers["reads"] == ["parse_args", "parser"]
    assert signtool_client_identifiers["writes"] == ["args"]
    assert signtool_client_trace == [
        {"line": 6, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 5, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert replace_identifiers["reads"] == []
    assert replace_identifiers["writes"] == ["data"]
    assert replace_trace == [
        {"line": 7, "code": "for file_name in args.files:", "writes": ["file_name"], "reads": ["args", "data", "f", "files", "open", "write"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]


def test_active_finding_python_benchmark_and_manifest_writes_should_keep_context_bindings(monkeypatch, tmp_path):
    benchmark_path = "vms/vms_benchmark/bin/main.py"
    benchmark_source = """\
def _rtsp_perf_frames(output_file_path, report):
    if output_file_path:
        output_file = open(output_file_path, "w")
        report(f"log to {output_file_path!r}")
    else:
        output_file = None
    return output_file


def run(stream_reader_context_manager, ini):
    archive_read_pos_ms_utc = 0
    stream_reader_context = None
    with stream_reader_context_manager as stream_reader_context:
        stream_reader_process = stream_reader_context[0]
        rtsp_perf_frames = _rtsp_perf_frames(
            ini["stdout"],
            ini["rtspPerfLinesOutputFile"])
    return rtsp_perf_frames
"""
    extract_system_path = "build_utils/customization/extract_system_data.py"
    extract_system_source = """\
import json


def main(parser):
    args = parser.parse_args()
    input = json.load(args.source)
    systemData = input['desktop']['systemData']
    json.dump(systemData, args.destination)
"""
    generate_path = "open/vms/server/plugins/analytics/stub_analytics_plugin/object_streamer_files/generate.py"
    generate_source = """\
import json


def main(args, generation_manager, ManifestEncoder, StreamEntryEncoder):
    manifest = generation_manager.generate_manifest()
    with open(args.manifest_file, 'w', encoding='UTF-8') as manifest_file:
        json.dump(manifest, manifest_file, cls=ManifestEncoder, indent=4)
        manifest_file.write(\"\\n\")

    stream = generation_manager.generate_stream()
    with open(args.stream_file, 'w', encoding='UTF-8') as stream_file:
        indent = None if args.compressed_stream else 4
        separators = (\",\", \":\") if args.compressed_stream else (\",\", \": \")
        json.dump(stream, stream_file, cls=StreamEntryEncoder, indent=indent, separators=separators)
        stream_file.write(\"\\n\")
"""
    _write_source_tree(tmp_path, benchmark_path, benchmark_source)
    _write_source_tree(tmp_path, extract_system_path, extract_system_source)
    _write_source_tree(tmp_path, generate_path, generate_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    benchmark_output_identifiers = mcp_server.find_identifiers("9ce90895", benchmark_path, 3)
    benchmark_output_trace = mcp_server.trace_identifier_backward("9ce90895", benchmark_path, 3, "output_file_path")
    benchmark_stream_identifiers = mcp_server.find_identifiers("9ce90895", benchmark_path, 14)
    benchmark_stream_trace = mcp_server.trace_identifier_backward("9ce90895", benchmark_path, 14, "stream_reader_context")
    extract_system_identifiers = mcp_server.find_identifiers("9ce90895", extract_system_path, 7)
    extract_system_trace = mcp_server.trace_identifier_backward("9ce90895", extract_system_path, 7, "systemData")
    manifest_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 6)
    manifest_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 6, "args")
    stream_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 11)
    stream_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 11, "args")
    manifest_file_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 7, "manifest_file")
    stream_file_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 14, "stream_file")

    assert benchmark_output_identifiers["reads"] == ["open", "output_file_path"]
    assert benchmark_output_identifiers["writes"] == ["output_file"]
    assert benchmark_output_trace == []
    assert benchmark_stream_identifiers["reads"] == ["stream_reader_context"]
    assert benchmark_stream_identifiers["writes"] == ["stream_reader_process"]
    assert benchmark_stream_trace == [
        {"line": 13, "code": "with stream_reader_context_manager as stream_reader_context:", "writes": ["stream_reader_context"], "reads": ["_rtsp_perf_frames", "ini", "rtsp_perf_frames", "stream_reader_context_manager", "stream_reader_process"]},
    ]
    assert extract_system_identifiers["reads"] == ["input"]
    assert extract_system_identifiers["writes"] == ["systemData"]
    assert extract_system_trace == [
        {"line": 7, "code": "systemData = input['desktop']['systemData']", "writes": ["systemData"], "reads": ["input"]},
        {"line": 6, "code": "input = json.load(args.source)", "writes": ["input"], "reads": ["args", "json", "load", "source"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert manifest_identifiers["reads"] == ["ManifestEncoder", "args", "cls", "dump", "encoding", "indent", "json", "manifest", "open", "write"]
    assert manifest_identifiers["writes"] == ["manifest_file"]
    assert manifest_trace == []
    assert stream_identifiers["reads"] == ["StreamEntryEncoder", "args", "cls", "compressed_stream", "dump", "encoding", "indent", "json", "open", "separators", "stream", "write"]
    assert stream_identifiers["writes"] == ["stream_file"]
    assert stream_trace == []
    assert manifest_file_trace == [
        {"line": 6, "code": "with open(args.manifest_file, 'w', encoding='UTF-8') as manifest_file:", "writes": ["manifest_file"], "reads": ["ManifestEncoder", "args", "cls", "dump", "encoding", "indent", "json", "manifest", "open", "write"]},
        {"line": 5, "code": "manifest = generation_manager.generate_manifest()", "writes": ["manifest"], "reads": ["generate_manifest", "generation_manager"]},
    ]
    assert stream_file_trace == [
        {"line": 11, "code": "with open(args.stream_file, 'w', encoding='UTF-8') as stream_file:", "writes": ["stream_file"], "reads": ["StreamEntryEncoder", "args", "cls", "compressed_stream", "dump", "encoding", "indent", "json", "open", "separators", "stream", "write"]},
        {"line": 10, "code": "stream = generation_manager.generate_stream()", "writes": ["stream"], "reads": ["generate_stream", "generation_manager"]},
    ]


def test_active_finding_html_inline_script_should_extract_and_trace_like_javascript(monkeypatch, tmp_path):
    file_path = "cloud/storage/analytics_vectorizer/vectorizer/templates/coco_search.html"
    source = """\
<html>
<body>
    <div id="stats"></div>
    <script>
        let searchResults = [];

        function displayResults(data) {
            const statsDiv = document.getElementById('stats');
            searchResults = data.matching_images.sort((a, b) => b.score - a.score);
            statsDiv.innerHTML = `
                <strong>Query:</strong> "${data.query}"<br>
                <strong>Matches:</strong> ${searchResults.length} images<br>
                <strong>Threshold:</strong> ${data.threshold_used.toFixed(3)}<br>
                <strong>Total images searched:</strong> ${data.total_images}<br>
                <strong>Time taken:</strong> ${data.time_taken.toFixed(2)}s
            `;
        }
    </script>
</body>
</html>
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 9)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 9)
    extracted = mcp_server.extract_function("9ce90895", file_path, 9)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 9, "data")

    assert classification["type"] == "production"
    assert imports == []
    assert decorators == []
    assert identifiers["reads"] == [
        "data",
        "length",
        "query",
        "searchResults",
        "statsDiv",
        "threshold_used",
        "time_taken",
        "toFixed",
        "total_images",
    ]
    assert identifiers["writes"] == ["innerHTML"]
    assert identifiers["language"] == "javascript"
    assert extracted["meta"]["code_on_line"] == "            statsDiv.innerHTML = `"
    assert trace == []


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

    original_try_parse = project_analysis._try_parse
    parse_calls: list[str] = []

    def deterministic_iter_source_files(_source_dir: Path):
        yield Path(irrelevant_file)
        yield Path(target_file)

    def counting_try_parse(source: str, filepath: Path):
        parse_calls.append(str(filepath.relative_to(tmp_path)))
        return original_try_parse(source, filepath)

    monkeypatch.setattr(project_analysis_callers, "_iter_source_files", deterministic_iter_source_files)
    monkeypatch.setattr(project_analysis_callers, "_try_parse", counting_try_parse)

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


def test_active_finding_cloud_portal_yaml_should_classify_as_config(monkeypatch, tmp_path):
    source = """\
bucket: 'cloud-portal'

smtp:
    host: 'email-smtp.us-east-1.amazonaws.com'
    user: 'AKIAJ6MLW7ZT7WXXXOIA'
    password: 'AlYDnddPk8mWorQFVogh8sqkQX6Nv01JwxxfMoYJAFeC'
    port: 587
"""
    yaml_dir = tmp_path / "cloud" / "cloud"
    yaml_dir.mkdir(parents=True)
    (yaml_dir / "cloud_portal.yaml").write_text(source, encoding="utf-8")
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)

    classification = mcp_server.classify_file("5a36b942", "cloud/cloud/cloud_portal.yaml")

    assert classification["type"] == "config"


def test_active_finding_flowerconfig_should_classify_as_config(monkeypatch):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("5a36b942", "deploy/cloud_portal/flowerconfig.py")

    assert classification["type"] == "config"


def test_active_finding_flowerconfig_should_keep_secret_assignment_block():
    source = """\
url_prefix = 'flower'
oauth2_key = '867999942165-1q3j5243lqrn5l2mkd9umfeabf03ss07.apps.googleusercontent.com'
oauth2_secret = 'gsZj6yCbhHIZnIeVsfDND8Sf'
oauth2_redirect_uri = 'http://depcon.hdw.mx/flower/login'
auth = '.*@networkoptix\\.com'
"""

    block = extract_config_block(source, Path("deploy/cloud_portal/flowerconfig.py"), 3)

    assert block["block_text"] == "oauth2_secret = 'gsZj6yCbhHIZnIeVsfDND8Sf'"
    assert block["start_line"] == 3
    assert block["end_line"] == 3


def test_active_finding_flowerconfig_should_extract_secret_like_variables(monkeypatch):
    source = """\
url_prefix = 'flower'
oauth2_key = '867999942165-1q3j5243lqrn5l2mkd9umfeabf03ss07.apps.googleusercontent.com'
oauth2_secret = 'gsZj6yCbhHIZnIeVsfDND8Sf'
oauth2_redirect_uri = 'http://depcon.hdw.mx/flower/login'
auth = '.*@networkoptix\\.com'
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "flowerconfig.py"))
    envs = mcp_server.extract_env_variables("5a36b942", "deploy/cloud_portal/flowerconfig.py")

    assert envs[1]["name"] == "oauth2_key"
    assert envs[1]["has_secret_pattern"] is True
    assert envs[2]["name"] == "oauth2_secret"
    assert envs[2]["value"] == "gsZj6yCbhHIZnIeVsfDND8Sf"
    assert envs[2]["has_secret_pattern"] is True


def test_active_finding_jenkins_yaml_should_classify_as_config_and_ci(monkeypatch):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", _stub_resolve_source_dir())

    classification = mcp_server.classify_file("5a36b942", "cloud/cloud_portal.jenkins.yaml")
    environment = mcp_server.classify_environment("5a36b942", "cloud/cloud_portal.jenkins.yaml")

    assert classification["type"] == "config"
    assert environment["environment"] == "ci"


def test_active_finding_cloud_settings_should_keep_rest_framework_assignment_block():
    source = """\
# End SNS Config

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'api.account_backend.BearerAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ),
}
"""

    block = extract_config_block(source, Path("cloud/cloud/settings.py"), 3)

    assert block["block_text"].startswith("REST_FRAMEWORK = {")
    assert block["start_line"] == 3
    assert block["end_line"] == 8


def test_active_finding_oauth2_server_docker_should_keep_cmd_instruction():
    source = """\
ARG DOCKER_REGISTRY=
ARG BASE_VERSION=
ENV QT_PLUGIN_PATH=/opt/networkoptix/oauth2_server/bin
ENV LD_LIBRARY_PATH=/opt/networkoptix/oauth2_server/lib
CMD ["/opt/networkoptix/oauth2_server/bin/entrypoint.sh"]
"""

    block = extract_config_block(source, Path("cloud/auth/deploy/oauth2_server/Dockerfile"), 5)

    assert block["block_text"] == 'CMD ["/opt/networkoptix/oauth2_server/bin/entrypoint.sh"]'
    assert block["block_type"] == "cmd_instruction"
    assert block["start_line"] == 5


def test_active_finding_sso_service_docker_should_keep_cmd_instruction():
    source = """\
ARG DOCKER_REGISTRY=
ARG BASE_VERSION=
ENV DEBIAN_FRONTEND=noninteractive
CMD ["/opt/networkoptix/sso_service/bin/entrypoint.sh"]
"""

    block = extract_config_block(source, Path("cloud/auth/deploy/sso_service/Dockerfile"), 4)

    assert block["block_text"] == 'CMD ["/opt/networkoptix/sso_service/bin/entrypoint.sh"]'
    assert block["block_type"] == "cmd_instruction"
    assert block["start_line"] == 4


def test_active_finding_k8s_fluentd_docker_should_keep_user_instruction():
    source = """\
FROM amazon/aws-for-fluent-bit:stable
COPY extra.conf /fluent-bit/etc/extra.conf
RUN mkdir -p /var/log/fluent
USER root
"""

    block = extract_config_block(source, Path("cloud/infra/deploy/k8s-fluentd-cloudwatch/Dockerfile"), 4)

    assert block["block_text"] == "USER root"
    assert block["block_type"] == "user_instruction"
    assert block["key_path"] == "USER"


def test_active_finding_turn_service_discovery_docker_should_keep_entrypoint_instruction():
    source = """\
FROM ubuntu:22.04
RUN apt-get update
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/app/agent"]
"""

    block = extract_config_block(
        source,
        Path("cloud/connectivity/deploy/turn_service_discovery_agent/Dockerfile"),
        3,
    )

    assert block["block_text"] == 'ENTRYPOINT ["/sbin/tini", "--"]'
    assert block["block_type"] == "entrypoint_instruction"
    assert block["start_line"] == 3


def test_related_configs_monorepo_compose_references_deep_dockerfile_by_path():
    """Compose in project root references a Dockerfile deep in the tree via
    explicit path — should be detected even though they are in different directories."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  api:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: services/api/Dockerfile\n",
            encoding="utf-8",
        )
        api_dir = root / "services" / "api"
        api_dir.mkdir(parents=True)
        (api_dir / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

        related = find_related_configs(root, "services/api/Dockerfile")

    assert {"file": "docker-compose.yml", "relationship": "referenced_by_compose"} in related


def test_related_configs_same_dir_dockerfile_compose_always_linked():
    """Dockerfile and docker-compose.yml in the same directory are always
    related — no content check needed (standard Docker convention)."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM node:20\n", encoding="utf-8")
        (root / "docker-compose.yml").write_text(
            "services:\n  app:\n    build: .\n",
            encoding="utf-8",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == [{"file": "docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_related_configs_unrelated_compose_in_different_tree_ignored():
    """A docker-compose.yml in a completely different directory tree that
    mentions 'Dockerfile' generically should NOT be linked to our Dockerfile."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "backend" / "Dockerfile").parent.mkdir(parents=True)
        (root / "backend" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

        (root / "frontend").mkdir()
        (root / "frontend" / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    build:\n"
            "      dockerfile: Dockerfile\n",
            encoding="utf-8",
        )

        related = find_related_configs(root, "backend/Dockerfile")

    assert related == []


def test_active_finding_python_submodule_and_file_mutation_helpers_should_keep_binding_context(monkeypatch, tmp_path):
    nx_submodule_path = "build_utils/nx_submodule/nx_submodule.py"
    nx_submodule_source = """\
import argparse
from pathlib import Path

import nx_submodule_lib


def _create_arg_parser():
    return argparse.ArgumentParser()


def _get_repo_url(args):
    return args.subrepo_url


def main():
    parser = _create_arg_parser()
    args = parser.parse_args()
    args.git_ref = args.git_ref or args.commit_sha

    if args.action == "create":
        nx_submodule_lib.create_submodule(
            dir=args.submodule_local_dir.resolve(),
            repo_url=_get_repo_url(args),
            repo_dir=args.subrepo_dir,
            git_ref=args.git_ref)
    else:
        if args.submodule_local_dir:
            nx_submodule_lib.update_submodule(
                dir=args.submodule_local_dir.resolve(),
                git_ref=args.git_ref,
                fetch_url=args.fetch_url)
        else:
            repo_url = _get_repo_url(args)
            main_repo_dir = (args.main_repo_dir or Path.cwd()).resolve()
            nx_submodule_lib.find_and_update_submodules(
                main_repo_dir=main_repo_dir,
                git_ref=args.git_ref,
                repo_url=repo_url,
                fetch_url=args.fetch_url)
"""
    clear_cmake_path = "build_utils/python/clear_cmake_build.py"
    clear_cmake_source = """\
import os
import shutil


def delete_path(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
"""
    merge_sync_path = "open/build_utils/merge_and_sync_directories.py"
    merge_sync_source = """\
import os
import shutil
import sys


def merge_and_sync_directories(output_dir):
    unneeded_files = ["old.txt"]
    unneeded_dirs = ["stale/subdir"]

    for f in unneeded_files:
        print(f"Removing {f}", file=sys.stderr)
        os.remove(f)

    for d in reversed(unneeded_dirs):
        print(f"Removing {d}", file=sys.stderr)
        if os.path.isdir(d):
            shutil.rmtree(d)
"""
    pack_path = "open/build_utils/customization/pack.py"
    pack_source = """\
import argparse
import logging
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    if args.log:
        Path(args.log).parent.mkdir(exist_ok=True, parents=True)
        logging.basicConfig(filename=args.log, filemode="w")
"""
    converter_path = "cloud/ams/utils/pytorch_to_onnx_converter/nx_ultralytics_to_onnx_converter.py"
    converter_source = """\
import argparse
import shutil

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    model = YOLO(args.input)
    f = model.export(format="onnx", batch=args.batch)
    shutil.move(f, args.output)
"""
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import os
import shutil


def copy_library(file_name, target_dir):
    real_file = os.path.realpath(file_name)
    real_basename = os.path.basename(real_file)
    target_file_name = os.path.join(target_dir, real_basename)
    if os.path.exists(target_file_name):
        os.remove(target_file_name)
    shutil.copy2(real_file, target_file_name)
"""
    _write_source_tree(tmp_path, nx_submodule_path, nx_submodule_source)
    _write_source_tree(tmp_path, clear_cmake_path, clear_cmake_source)
    _write_source_tree(tmp_path, merge_sync_path, merge_sync_source)
    _write_source_tree(tmp_path, pack_path, pack_source)
    _write_source_tree(tmp_path, converter_path, converter_source)
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    nx_classification = mcp_server.classify_file("9ce90895", nx_submodule_path)
    nx_create_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 19)
    nx_create_trace = mcp_server.trace_identifier_backward("9ce90895", nx_submodule_path, 19, "args")
    nx_update_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 25)
    nx_recurse_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 32)
    nx_recurse_trace = mcp_server.trace_identifier_backward("9ce90895", nx_submodule_path, 32, "main_repo_dir")
    clear_rmtree_identifiers = mcp_server.find_identifiers("9ce90895", clear_cmake_path, 6)
    clear_remove_identifiers = mcp_server.find_identifiers("9ce90895", clear_cmake_path, 8)
    clear_remove_trace = mcp_server.trace_identifier_backward("9ce90895", clear_cmake_path, 8, "path")
    merge_remove_identifiers = mcp_server.find_identifiers("9ce90895", merge_sync_path, 11)
    merge_remove_trace = mcp_server.trace_identifier_backward("9ce90895", merge_sync_path, 11, "f")
    merge_rmtree_identifiers = mcp_server.find_identifiers("9ce90895", merge_sync_path, 15)
    merge_rmtree_trace = mcp_server.trace_identifier_backward("9ce90895", merge_sync_path, 15, "d")
    pack_identifiers = mcp_server.find_identifiers("9ce90895", pack_path, 10)
    pack_trace = mcp_server.trace_identifier_backward("9ce90895", pack_path, 10, "args")
    converter_identifiers = mcp_server.find_identifiers("9ce90895", converter_path, 11)
    converter_trace = mcp_server.trace_identifier_backward("9ce90895", converter_path, 11, "args")
    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 10)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 10, "real_file")

    assert nx_classification["type"] == "production"
    assert {"args", "create_submodule", "nx_submodule_lib", "repo_dir", "repo_url"} <= set(nx_create_identifiers["reads"])
    assert nx_create_identifiers["writes"] == ["args", "git_ref", "main_repo_dir", "parser", "repo_url"]
    assert nx_create_identifiers["language"] == "python"
    _assert_trace_codes(nx_create_trace, ["args = parser.parse_args()", "parser = _create_arg_parser()"])
    assert {"_get_repo_url", "args", "create_submodule", "dir", "git_ref", "nx_submodule_lib", "repo_dir", "repo_url", "resolve", "submodule_local_dir", "subrepo_dir"} <= set(
        nx_update_identifiers["reads"]
    )
    assert nx_update_identifiers["writes"] == []
    assert {"Path", "args", "cwd", "fetch_url", "find_and_update_submodules", "git_ref", "main_repo_dir", "nx_submodule_lib", "repo_url", "resolve"} <= set(
        nx_recurse_identifiers["reads"]
    )
    assert nx_recurse_identifiers["writes"] == ["main_repo_dir", "repo_url"]
    _assert_trace_codes(nx_recurse_trace, ["if args.submodule_local_dir:", "args.git_ref = args.git_ref or args.commit_sha", "args = parser.parse_args()"])
    assert clear_rmtree_identifiers == {"reads": ["isdir", "os", "path", "remove", "rmtree", "shutil"], "writes": [], "language": "python"}
    assert clear_remove_identifiers == {"reads": ["isdir", "os", "path", "remove", "rmtree", "shutil"], "writes": [], "language": "python"}
    assert clear_remove_trace == []
    assert merge_remove_identifiers == {"reads": ["f", "file", "print", "stderr", "sys"], "writes": [], "language": "python"}
    _assert_trace_codes(merge_remove_trace, ["for f in unneeded_files:"])
    assert merge_rmtree_identifiers == {"reads": ["d", "file", "print", "stderr", "sys"], "writes": [], "language": "python"}
    _assert_trace_codes(merge_rmtree_trace, ["for d in reversed(unneeded_dirs):", 'unneeded_dirs = ["stale/subdir"]'])
    assert pack_identifiers["reads"] == ["Path", "args", "exist_ok", "log", "mkdir", "parent", "parents"]
    assert pack_identifiers["writes"] == []
    _assert_trace_codes(pack_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert converter_identifiers["reads"] == ["args", "batch", "export", "format", "model"]
    assert converter_identifiers["writes"] == ["f"]
    _assert_trace_codes(converter_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert copy_lib_identifiers["reads"] == ["os", "remove", "target_file_name"]
    assert copy_lib_identifiers["writes"] == []
    _assert_trace_codes(copy_lib_trace, ["real_file = os.path.realpath(file_name)"])


def test_active_finding_avjpeg_header_should_keep_camera_model_context(monkeypatch, tmp_path):
    file_path = "vms/server/nx_vms_server/src/plugins/resource/arecontvision/tools/AVJpegHeader.cpp"
    source = """\
#include "AVJpegHeader.h"
#include <string>
#include <cstring>

int AVJpeg::Header::GetHeader(unsigned char* pBuffer, unsigned int nWidth, unsigned int nHeight, int iQuality, const char* szCameraModel)
{
#ifndef _countof
#define _countof(_Array) (sizeof(_Array) / sizeof(_Array[0]))
#endif

    memcpy(pBuffer, s_JpegHeaderTemplate, _countof(s_JpegHeaderTemplate));

    if(szCameraModel && *szCameraModel)
    {
        strncpy((char*)(pBuffer + CAMERA_MODEL_OFFSET), szCameraModel, 32);
    }

    return _countof(s_JpegHeaderTemplate);
}
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, 15)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, 15)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, 15)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 15, "szCameraModel")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "        strncpy((char*)(pBuffer + CAMERA_MODEL_OFFSET), szCameraModel, 32);"
    assert imports == ['#include "AVJpegHeader.h"', "#include <string>", "#include <cstring>"]
    assert decorators == []
    assert identifiers == {
        "reads": ["CAMERA_MODEL_OFFSET", "pBuffer", "strncpy", "szCameraModel"],
        "writes": [],
        "language": "cpp",
    }
    assert trace == []


def test_active_finding_python_copy_and_move_helpers_should_keep_path_bindings(monkeypatch, tmp_path):
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import argparse
import os
import shutil
import sys


def find_library(lib, lib_dirs):
    return "/tmp/" + lib


def copy_library(file_name, target_dir, list_files=False):
    real_file = os.path.realpath(file_name)
    real_basename = os.path.basename(real_file)
    target_file_name = os.path.join(target_dir, real_basename)
    if os.path.exists(target_file_name):
        os.remove(target_file_name)
    shutil.copy2(real_file, target_file_name)


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    lib_dirs = []
    libs = []
    for lib in args.libs:
        file_name = find_library(lib, lib_dirs)
        libs.append(file_name)
    for lib in libs:
        copy_library(lib, args.dest_dir, list_files=args.list)
"""
    build_model_path = "cloud/ams/analytics_server/deploy/build_analytics_model.py"
    build_model_source = """\
import os
import shutil

QUANT_CALIB_FILE = "calib.cache"
TRT_CALIB_CACH_FILE_NAME = "tmp.cache"


def build_trt_model(**kwargs):
    return kwargs


def calculate_calib_file(dataset_path, output_dir):
    build_trt_model(output_dir=output_dir, calib_dataset=os.path.join(dataset_path, "images"))
    target_calib_file = os.path.join(output_dir, QUANT_CALIB_FILE)
    shutil.move(TRT_CALIB_CACH_FILE_NAME, target_calib_file)
"""
    yolov11_path = "cloud/ams/model/src/nx/utils/train/nx_yolov11_train.py"
    yolov11_source = """\
import argparse
import shutil


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    for attempt_i in range(args.train_attempts):
        try:
            shutil.move("runs/detect", "runs/attempt_" + str(attempt_i))
        except Exception:
            pass
"""
    pack_server_path = "cloud/ams/analytics_server/deploy/deprecated/pack_server.py"
    pack_server_source = """\
import argparse
import os
import shutil

TARGET_MODELS_FOLDER = "models"
TARGET_MODEL_NAME = "model.bin"
TARGET_MODEL_CONFIG_NAME = "config.json"


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    target_app_path = "/tmp/server"
    deploy_folder_path = "/tmp/deploy"
    target_lib_path = "/tmp/lib"
    shutil.copy(target_app_path, args.pkg_path)
    shutil.copy(os.path.join(deploy_folder_path, "config.json"), args.pkg_path)
    shutil.copy(os.path.join(deploy_folder_path, "entrypoint.sh"), args.pkg_path)
    target_model_folder_path = os.path.join(args.pkg_path, TARGET_MODELS_FOLDER)
    os.makedirs(target_model_folder_path, exist_ok=True)
    target_model_path = os.path.join(target_model_folder_path, TARGET_MODEL_NAME)
    if args.model_path != target_model_path:
        shutil.copy(args.model_path, target_model_path)
    if args.model_config:
        target_model_config_path = os.path.join(target_model_folder_path, TARGET_MODEL_CONFIG_NAME)
        if args.model_config != target_model_config_path:
            shutil.copy(args.model_config, target_model_config_path)
"""
    pack_benchmark_path = "cloud/ams/analytics_server/deploy/pack_benchmark.py"
    pack_benchmark_source = """\
import argparse
import os
import shutil

TARGET_MODELS_FOLDER = "models"
TARGET_MODEL_NAME = "model.bin"
TARGET_MODEL_CONFIG_NAME = "config.json"


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    target_app_path = "/tmp/bench"
    shutil.copy(target_app_path, args.pkg_path)
    shutil.copy(args.file_path, args.pkg_path)
    target_model_folder_path = os.path.join(args.pkg_path, TARGET_MODELS_FOLDER)
    os.makedirs(target_model_folder_path)
    target_model_path = os.path.join(target_model_folder_path, TARGET_MODEL_NAME)
    shutil.copy(args.model_path, target_model_path)
    if args.model_config:
        target_model_config_path = os.path.join(target_model_folder_path, TARGET_MODEL_CONFIG_NAME)
        shutil.copy(args.model_config, target_model_config_path)
"""
    adapt_images_path = "cloud/ams/model/src/nx/utils/dataset/adapters/adapt_images.py"
    adapt_images_source = """\
import pathlib
import shutil


def copy_non_same(src_path, dst_path):
    if src_path != dst_path:
        shutil.copy(src_path, dst_path)


def save_image_as_is(ann_file, target_dir):
    copy_non_same(
        ann_file.parent / (ann_file.stem + ".jpg"),
        pathlib.Path(target_dir) / str(ann_file.stem + ".jpg")
    )
    copy_non_same(
        ann_file.parent / (ann_file.stem + ".json"),
        pathlib.Path(target_dir) / str(ann_file.stem + ".json")
    )


def save_mosaic_candidate(used_files, target_dir):
    result_file = used_files[0].name
    copy_non_same(
        used_files[0].parent / (used_files[0].name + ".jpg"),
        pathlib.Path(target_dir) / str(result_file + ".jpg"),
    )
    copy_non_same(
        used_files[0].parent / (used_files[0].name + ".json"),
        pathlib.Path(target_dir) / str(result_file + ".json"),
    )
"""
    macdeployqt_path = "open/vms/distribution/dmg/client/resources.in/macdeployqt.py"
    macdeployqt_source = """\
import os
import shutil
from os.path import join


def main(app_path, bindir, helpdir):
    resources_dir = "{app_path}/Contents/Resources".format(app_path=app_path)
    help_dir = "{}/help".format(resources_dir)
    shutil.copytree(helpdir, help_dir)
    shutil.copy(join(bindir, "launcher.version"), resources_dir)
"""
    filter_images_path = "cloud/ams/model/src/nx/utils/dataset/adapters/filter_images.py"
    filter_images_source = """\
import pathlib
import shutil


def copy_filtered(file_path, target_dir, copied_files):
    ann_file = file_path.parent / (file_path.stem + ".json")
    if ann_file not in copied_files:
        copied_files[ann_file] = True
        shutil.copy(
            ann_file,
            str(target_dir / (file_path.stem + ".json"))
        )
        shutil.copy(
            str(file_path.parent / (file_path.stem + ".jpg")),
            str(target_dir / (file_path.stem + ".jpg"))
        )
"""
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    _write_source_tree(tmp_path, build_model_path, build_model_source)
    _write_source_tree(tmp_path, yolov11_path, yolov11_source)
    _write_source_tree(tmp_path, pack_server_path, pack_server_source)
    _write_source_tree(tmp_path, pack_benchmark_path, pack_benchmark_source)
    _write_source_tree(tmp_path, adapt_images_path, adapt_images_source)
    _write_source_tree(tmp_path, macdeployqt_path, macdeployqt_source)
    _write_source_tree(tmp_path, filter_images_path, filter_images_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 24)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 24, "lib")
    build_model_classification = mcp_server.classify_file("9ce90895", build_model_path)
    build_model_identifiers = mcp_server.find_identifiers("9ce90895", build_model_path, 14)
    build_model_trace = mcp_server.trace_identifier_backward("9ce90895", build_model_path, 14, "target_calib_file")
    yolov11_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 9)
    yolov11_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 9, "attempt_i")
    pack_server_identifiers = mcp_server.find_identifiers("9ce90895", pack_server_path, 15)
    pack_server_trace = mcp_server.trace_identifier_backward("9ce90895", pack_server_path, 15, "args")
    pack_benchmark_identifiers = mcp_server.find_identifiers("9ce90895", pack_benchmark_path, 14)
    pack_benchmark_trace = mcp_server.trace_identifier_backward("9ce90895", pack_benchmark_path, 14, "args")
    adapt_copy_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 7)
    adapt_copy_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 7, "src_path")
    adapt_save_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 11)
    adapt_save_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 11, "ann_file")
    adapt_mosaic_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 22)
    adapt_mosaic_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 22, "result_file")
    macdeployqt_identifiers = mcp_server.find_identifiers("9ce90895", macdeployqt_path, 10)
    macdeployqt_trace = mcp_server.trace_identifier_backward("9ce90895", macdeployqt_path, 10, "help_dir")
    filter_images_identifiers = mcp_server.find_identifiers("9ce90895", filter_images_path, 9)
    filter_images_trace = mcp_server.trace_identifier_backward("9ce90895", filter_images_path, 9, "ann_file")

    assert copy_lib_identifiers == {"reads": [], "writes": ["libs"], "language": "python"}
    assert copy_lib_trace == []
    assert build_model_classification["type"] == "config"
    assert build_model_identifiers == {
        "reads": ["QUANT_CALIB_FILE", "join", "os", "output_dir", "path"],
        "writes": ["target_calib_file"],
        "language": "python",
    }
    _assert_trace_codes(build_model_trace, ["target_calib_file = os.path.join(output_dir, QUANT_CALIB_FILE)"])
    assert yolov11_identifiers["reads"] == []
    assert yolov11_identifiers["writes"] == []
    _assert_trace_codes(yolov11_trace, ["for attempt_i in range(args.train_attempts):", "args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert pack_server_identifiers["reads"] == []
    assert pack_server_identifiers["writes"] == ["target_lib_path"]
    _assert_trace_codes(pack_server_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert {"args", "copy", "pkg_path", "shutil", "target_app_path"} <= set(pack_benchmark_identifiers["reads"])
    assert pack_benchmark_identifiers["writes"] == []
    _assert_trace_codes(pack_benchmark_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert adapt_copy_identifiers == {"reads": ["copy", "dst_path", "shutil", "src_path"], "writes": [], "language": "python"}
    assert adapt_copy_trace == []
    assert {"Path", "ann_file", "copy_non_same", "parent", "pathlib", "stem", "str", "target_dir"} <= set(adapt_save_identifiers["reads"])
    assert adapt_save_identifiers["writes"] == []
    assert adapt_save_trace == []
    assert adapt_mosaic_identifiers == {"reads": ["name", "used_files"], "writes": ["result_file"], "language": "python"}
    _assert_trace_codes(adapt_mosaic_trace, ["result_file = used_files[0].name"])
    assert macdeployqt_identifiers == {"reads": ["bindir", "copy", "join", "resources_dir", "shutil"], "writes": [], "language": "python"}
    _assert_trace_codes(
        macdeployqt_trace,
        ['help_dir = "{}/help".format(resources_dir)', 'resources_dir = "{app_path}/Contents/Resources".format(app_path=app_path)'],
    )
    assert filter_images_identifiers == {
        "reads": ["ann_file", "copy", "file_path", "shutil", "stem", "str", "target_dir"],
        "writes": [],
        "language": "python",
    }
    _assert_trace_codes(filter_images_trace, ["copied_files[ann_file] = True"])


def test_active_finding_python_converter_and_bundle_helpers_should_keep_copyfile_and_hierarchy_context(monkeypatch, tmp_path):
    crowdhuman_path = "cloud/ams/model/src/nx/utils/dataset/converters/crowdhuman_to_labelme.py"
    crowdhuman_source = """\
import pathlib
import shutil


def save_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / image_file.name)
"""
    mot_path = "cloud/ams/model/src/nx/utils/dataset/converters/mot_to_labelme.py"
    mot_source = """\
import pathlib
import shutil


def save_frame(frame_id, image_file, target_seq_path):
    shutil.copyfile(image_file, target_seq_path / (str(frame_id) + ".jpg"))
"""
    voc_path = "cloud/ams/model/src/nx/utils/dataset/converters/voc_to_labelme.py"
    voc_source = """\
import pathlib
import shutil


def save_voc_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / (image_file.name))
"""
    captcha_path = "cloud/ams/model/src/nx/utils/dataset/converters/filter_google_captcha_set.py"
    captcha_source = """\
import pathlib
import shutil


def save_captcha_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / (image_file.name))
"""
    tao_path = "cloud/ams/model/src/nx/utils/dataset/converters/tao_to_labelme.py"
    tao_source = """\
import os
import pathlib
import shutil


class AnnFile:
    def __init__(self, image_file):
        self.image_file = image_file


def save_tao_image(image_file, ann_file, target_root):
    os.makedirs(str(pathlib.Path(target_root) / ann_file.image_file.parent), exist_ok=True)
    shutil.copyfile(image_file, pathlib.Path(target_root) / ann_file.image_file)
"""
    signtool_path = "open/build_utils/signtool/signtool.py"
    signtool_source = """\
import shutil


def sign(in_file_path, out_file_path):
    if out_file_path and out_file_path != in_file_path:
        shutil.copyfile(in_file_path, out_file_path)
        file_to_sign = out_file_path
    else:
        file_to_sign = in_file_path
    return file_to_sign
"""
    client_macdeployqt_path = "open/vms/distribution/dmg/client/resources.in/macdeployqt.py"
    client_macdeployqt_source = """\
import shutil
from os.path import join


def prepare(build_dir, binary, sbindir, tbindir, applauncher_binary):
    shutil.copyfile(join(sbindir, "@client.binary.name@"), binary)
    shutil.copyfile(join(sbindir, "@applauncher.binary.name@"), applauncher_binary)
    shutil.copyfile(join(build_dir, "qt.conf"), join(tbindir, "qt.conf"))
"""
    server_macdeployqt_path = "vms/distribution/dmg/mediaserver/resources.in/macdeployqt.py"
    server_macdeployqt_source = """\
import shutil
from os.path import join


def prepare(build_dir, binary, sbindir, tbindir):
    shutil.copyfile(join(sbindir, "@server.binary.name@"), binary)
    shutil.copyfile(join(build_dir, "qt.conf"), join(tbindir, "qt.conf"))
"""
    open_images_path = "cloud/ams/model/src/nx/utils/dataset/converters/open_images_parts_to_labelme.py"
    open_images_source = """\
import json
import pathlib


def enrich_class_mapping_with_hierarchy(hierarchy_file, class_mapping):
    file_content = pathlib.Path(hierarchy_file).read_text()
    hierarchy_json = json.loads(file_content)
    result_class_mapping = dict(class_mapping)
    return hierarchy_json, result_class_mapping


def allocate_target_dir(target_root, result_w, result_h, object_image):
    STEP_H = 40
    STEP_W = 40
    round_h = int(result_h / STEP_H) * STEP_H
    round_w = int(result_w / STEP_W) * STEP_W
    target_dir = pathlib.Path(target_root) / (str(round_w) + "x" + str(round_h))
    return target_dir, object_image
"""
    _write_source_tree(tmp_path, crowdhuman_path, crowdhuman_source)
    _write_source_tree(tmp_path, mot_path, mot_source)
    _write_source_tree(tmp_path, voc_path, voc_source)
    _write_source_tree(tmp_path, captcha_path, captcha_source)
    _write_source_tree(tmp_path, tao_path, tao_source)
    _write_source_tree(tmp_path, signtool_path, signtool_source)
    _write_source_tree(tmp_path, client_macdeployqt_path, client_macdeployqt_source)
    _write_source_tree(tmp_path, server_macdeployqt_path, server_macdeployqt_source)
    _write_source_tree(tmp_path, open_images_path, open_images_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    crowdhuman_identifiers = mcp_server.find_identifiers("9ce90895", crowdhuman_path, 5)
    crowdhuman_trace = mcp_server.trace_identifier_backward("9ce90895", crowdhuman_path, 5, "image_file")
    mot_identifiers = mcp_server.find_identifiers("9ce90895", mot_path, 6)
    mot_trace = mcp_server.trace_identifier_backward("9ce90895", mot_path, 6, "image_file")
    voc_identifiers = mcp_server.find_identifiers("9ce90895", voc_path, 5)
    voc_trace = mcp_server.trace_identifier_backward("9ce90895", voc_path, 5, "image_file")
    captcha_identifiers = mcp_server.find_identifiers("9ce90895", captcha_path, 5)
    captcha_trace = mcp_server.trace_identifier_backward("9ce90895", captcha_path, 5, "image_file")
    tao_identifiers = mcp_server.find_identifiers("9ce90895", tao_path, 12)
    tao_trace = mcp_server.trace_identifier_backward("9ce90895", tao_path, 12, "image_file")
    signtool_identifiers = mcp_server.find_identifiers("9ce90895", signtool_path, 5)
    signtool_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_path, 5, "out_file_path")
    client_mac_identifiers = mcp_server.find_identifiers("9ce90895", client_macdeployqt_path, 6)
    client_mac_trace = mcp_server.trace_identifier_backward("9ce90895", client_macdeployqt_path, 6, "binary")
    server_mac_identifiers = mcp_server.find_identifiers("9ce90895", server_macdeployqt_path, 6)
    server_mac_trace = mcp_server.trace_identifier_backward("9ce90895", server_macdeployqt_path, 6, "binary")
    open_images_read_identifiers = mcp_server.find_identifiers("9ce90895", open_images_path, 6)
    open_images_read_trace = mcp_server.trace_identifier_backward("9ce90895", open_images_path, 6, "hierarchy_file")
    open_images_target_identifiers = mcp_server.find_identifiers("9ce90895", open_images_path, 14)
    open_images_target_trace = mcp_server.trace_identifier_backward("9ce90895", open_images_path, 14, "target_dir")

    assert crowdhuman_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_image", "target_root"], "language": "python"}
    assert crowdhuman_trace == []
    assert mot_identifiers == {
        "reads": ["copyfile", "frame_id", "image_file", "shutil", "str", "target_seq_path"],
        "writes": [],
        "language": "python",
    }
    assert mot_trace == []
    assert voc_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_voc_image", "target_root"], "language": "python"}
    assert voc_trace == []
    assert captcha_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_captcha_image", "target_root"], "language": "python"}
    assert captcha_trace == []
    assert {"Path", "ann_file", "exist_ok", "image_file", "makedirs", "os", "parent", "pathlib", "str", "target_root"} == set(tao_identifiers["reads"])
    assert tao_identifiers["writes"] == []
    assert tao_identifiers["language"] == "python"
    assert tao_trace == []
    assert signtool_identifiers == {
        "reads": ["copyfile", "in_file_path", "out_file_path", "shutil"],
        "writes": ["file_to_sign"],
        "language": "python",
    }
    assert signtool_trace == []
    assert client_mac_identifiers == {
        "reads": ["binary", "copyfile", "join", "sbindir", "shutil"],
        "writes": [],
        "language": "python",
    }
    assert client_mac_trace == []
    assert server_mac_identifiers == {
        "reads": ["binary", "copyfile", "join", "sbindir", "shutil"],
        "writes": [],
        "language": "python",
    }
    assert server_mac_trace == []
    assert open_images_read_identifiers == {
        "reads": ["Path", "hierarchy_file", "pathlib", "read_text"],
        "writes": ["file_content"],
        "language": "python",
    }
    assert open_images_read_trace == []
    assert open_images_target_identifiers == {
        "reads": [],
        "writes": ["STEP_W"],
        "language": "python",
    }
    assert open_images_target_trace == []


def test_active_finding_api_session_and_native_path_helpers_should_keep_bindings(monkeypatch, tmp_path):
    vectorizer_path = "cloud/storage/analytics_vectorizer/vectorizer/main.py"
    vectorizer_source = """\
import fastapi


async def search_dataset():
    datasets_to_search = ["coco"]
    if not datasets_to_search:
        return fastapi.responses.JSONResponse(
            content={"error": "No datasets available. Server initialization failed."},
            status_code=503,
        )
"""
    discovery_path = "vms/server/plugins/device/it930x_plugin/src/discovery_manager.cpp"
    discovery_source = """\
#include <string.h>

static const char* getPath(const char* fullName, char* buf, int size)
{
    int len = strlen(fullName);
    int i;
    int newSize = 0;
    return buf;
}

void useConfig(char* buf)
{
    strcat(buf, "it930.conf");
}
"""
    archive_path = "open/vms/server/nx_server_plugin_sdk/build_samples_archive.py"
    archive_source = """\
import zipfile


def build_archive(archive_name, items_to_archive, sample_build_dir):
    with zipfile.ZipFile(archive_name, "w") as archive:
        for file in items_to_archive:
            rel_path = file.relative_to(sample_build_dir)
            print(f"  Adding {file} to archive as {rel_path}")
            archive.write(file, rel_path)
"""
    http_client_path = "vms/server/plugins/analytics/python_app_host_plugin/python_src/util/vms_http_client.py"
    http_client_source = """\
class Client:
    def authenticate(self) -> bool:
        credentials = {'username': self._settings.username, 'password': self._settings.password}
        response = self._session.post(
            f'{self.base_url}/rest/v4/login/sessions', json=credentials, verify=False)
        return response.status_code == 200

    def create_generic_event(self, title: str, message: str) -> bool:
        body = {
            'state': 'instant',
            'caption': title,
            'description': message,
        }
        response = self._session.post(
            f'{self.base_url}/rest/v4/events/generic', json=body, verify=False)
        return response.status_code == 200
"""
    signing_client_path = "build_utils/code_signing/generic_http_signing_client.py"
    signing_client_source = """\
import requests


class SigningClient:
    def send_file(self):
        session = requests.Session()
        response = session.get(self.url)
        with open(self.file, "rb") as file_handle:
            r = session.post(
                self.url,
                params=self.params,
                files={"file": file_handle},
                timeout=self.request_timeout,
            )
        return response, r
"""
    _write_source_tree(tmp_path, vectorizer_path, vectorizer_source)
    _write_source_tree(tmp_path, discovery_path, discovery_source)
    _write_source_tree(tmp_path, archive_path, archive_source)
    _write_source_tree(tmp_path, http_client_path, http_client_source)
    _write_source_tree(tmp_path, signing_client_path, signing_client_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    # Audit trail:
    # live line 201 `int len = strlen(fullName);` -> fixture line 5
    # live line 250 `strcat(buf, "it930.conf");` -> fixture line 13
    # live line 61 `response = session.get(self.url)` -> fixture line 7
    # live line 76 `r = session.post(` -> fixture line 9
    vectorizer_classification = mcp_server.classify_file("9ce90895", vectorizer_path)
    vectorizer_decorators = mcp_server.find_decorators("9ce90895", vectorizer_path, 7)
    vectorizer_identifiers = mcp_server.find_identifiers("9ce90895", vectorizer_path, 7)
    vectorizer_trace = mcp_server.trace_identifier_backward("9ce90895", vectorizer_path, 7, "datasets_to_search")
    discovery_identifiers = mcp_server.find_identifiers("9ce90895", discovery_path, 5)
    discovery_trace = mcp_server.trace_identifier_backward("9ce90895", discovery_path, 5, "fullName")
    discovery_config_identifiers = mcp_server.find_identifiers("9ce90895", discovery_path, 13)
    discovery_config_trace = mcp_server.trace_identifier_backward("9ce90895", discovery_path, 13, "buf")
    archive_identifiers = mcp_server.find_identifiers("9ce90895", archive_path, 5)
    archive_trace = mcp_server.trace_identifier_backward("9ce90895", archive_path, 5, "file")
    auth_identifiers = mcp_server.find_identifiers("9ce90895", http_client_path, 5)
    auth_trace = mcp_server.trace_identifier_backward("9ce90895", http_client_path, 5, "credentials")
    event_identifiers = mcp_server.find_identifiers("9ce90895", http_client_path, 14)
    event_trace = mcp_server.trace_identifier_backward("9ce90895", http_client_path, 14, "body")
    signing_identifiers = mcp_server.find_identifiers("9ce90895", signing_client_path, 7)
    signing_trace = mcp_server.trace_identifier_backward("9ce90895", signing_client_path, 7, "response")
    signing_upload_identifiers = mcp_server.find_identifiers("9ce90895", signing_client_path, 9)
    signing_upload_trace = mcp_server.trace_identifier_backward("9ce90895", signing_client_path, 9, "file_handle")

    assert vectorizer_classification["type"] == "production"
    assert vectorizer_decorators == []
    assert vectorizer_identifiers == {
        "reads": ["JSONResponse", "content", "fastapi", "responses", "status_code"],
        "writes": [],
        "language": "python",
    }
    _assert_trace_codes(vectorizer_trace, ['datasets_to_search = ["coco"]'])
    assert discovery_identifiers == {"reads": ["fullName", "strlen"], "writes": ["len"], "language": "cpp"}
    assert discovery_trace == []
    assert discovery_config_identifiers == {"reads": ["buf", "strcat"], "writes": [], "language": "cpp"}
    assert discovery_config_trace == []
    assert archive_identifiers == {
        "reads": ["ZipFile", "archive_name", "file", "items_to_archive", "print", "rel_path", "relative_to", "sample_build_dir", "write", "zipfile"],
        "writes": ["archive"],
        "language": "python",
    }
    assert archive_trace == []
    assert auth_identifiers == {
        "reads": ["_session", "base_url", "credentials", "json", "post", "self", "verify"],
        "writes": ["response"],
        "language": "python",
    }
    _assert_trace_codes(auth_trace, ["credentials = {'username': self._settings.username, 'password': self._settings.password}"])
    assert event_identifiers == {
        "reads": ["_session", "base_url", "body", "json", "post", "self", "verify"],
        "writes": ["response"],
        "language": "python",
    }
    _assert_trace_codes(event_trace, ["body = {"])
    assert signing_identifiers == {"reads": ["get", "self", "session", "url"], "writes": ["response"], "language": "python"}
    _assert_trace_codes(signing_trace, ["response = session.get(self.url)", "session = requests.Session()"])
    assert signing_upload_identifiers == {
        "reads": ["file_handle", "files", "params", "post", "request_timeout", "self", "session", "timeout", "url"],
        "writes": ["r"],
        "language": "python",
    }
    _assert_trace_codes(
        signing_upload_trace,
        [
            'with open(self.file, "rb") as file_handle:',
            "session = requests.Session()",
        ],
    )
