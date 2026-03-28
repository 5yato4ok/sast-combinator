from _active_real_finding_audit_helpers import *
def test_active_finding_cpp_fopen_branches_should_keep_sink_lines_and_navigation_context(
    monkeypatch,
    tmp_path,
):
    """Audit trail:
    live line 304 `out = fopen(filename, "wb");` -> fixture line 16 via extract_function.
    live line 308 `out = fopen(filename, "ab");` -> fixture line 20 via extract_function.
    tool under test: extract_function/find_identifiers/trace_identifier_backward/find_callers/find_definition/find_route_to_function.
    """
    target_path = "open/libs/nx_media_core/src/nx/media/ffmpeg/frame_info.cpp"
    caller_path = "open/libs/nx_media_core/src/nx/media/ffmpeg/frame_writer.cpp"
    header_path = "open/libs/nx_media_core/src/nx/media/ffmpeg/frame_info.h"
    source = """\
#include <cstdio>

class CLVideoDecoderOutput {
public:
    void saveToFile(const char* filename);
};

void CLVideoDecoderOutput::saveToFile(const char* filename)
{

    static bool first_time  = true;
    FILE * out = 0;

    if (first_time)
    {
        out = fopen(filename, "wb");
        first_time = false;
    }
    else
        out = fopen(filename, "ab");

    if (!out) return;
}
"""
    caller_source = """\
#include "frame_info.h"
void writeFrame(CLVideoDecoderOutput& output, const char* path)
{
    output.saveToFile(path);
}
"""
    header_source = "class CLVideoDecoderOutput { public: void saveToFile(const char* filename); };\n"

    _write_source_tree(tmp_path, target_path, source)
    _write_source_tree(tmp_path, caller_path, caller_source)
    _write_source_tree(tmp_path, header_path, header_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target_path)
    imports = mcp_server.find_imports("9ce90895", target_path)
    extract_write = mcp_server.extract_function("9ce90895", target_path, 16)
    extract_append = mcp_server.extract_function("9ce90895", target_path, 20)
    identifiers_write = mcp_server.find_identifiers("9ce90895", target_path, 16)
    identifiers_append = mcp_server.find_identifiers("9ce90895", target_path, 20)
    trace_write = mcp_server.trace_identifier_backward("9ce90895", target_path, 16, "filename")
    trace_append = mcp_server.trace_identifier_backward("9ce90895", target_path, 20, "filename")
    callers = mcp_server.find_callers("9ce90895", target_path, "saveToFile")
    definition = mcp_server.find_definition("9ce90895", "saveToFile")
    route = mcp_server.find_route_to_function("9ce90895", "saveToFile")

    assert classification["type"] == "production"
    assert '#include <cstdio>' in imports
    assert mcp_server.find_decorators("9ce90895", target_path, 16) == []
    assert mcp_server.find_decorators("9ce90895", target_path, 20) == []

    assert extract_write["meta"]["code_on_line"] == '        out = fopen(filename, "wb");'
    assert extract_append["meta"]["code_on_line"] == '        out = fopen(filename, "ab");'
    assert identifiers_write == {"reads": ["filename", "fopen"], "writes": ["out"], "language": "cpp"}
    assert identifiers_append == {"reads": ["filename", "fopen"], "writes": ["first_time", "out"], "language": "cpp"}
    assert trace_write == []
    assert trace_append == []

    assert callers == [
        {
            "file": caller_path,
            "line": 4,
            "caller_function": "writeFrame",
            "snippet": '        3| {\n>>>     4|     output.saveToFile(path);\n        5| }',
        }
    ]
    assert definition == [{"file": target_path, "line": 8, "kind": "function"}]
    assert route == []






def test_active_finding_cpp_server_db_parameter_slices_should_keep_conversion_context(
    monkeypatch,
    tmp_path,
):
    """Audit trail:
    live line 229 `QByteArray field(value.data() + prevPos + 1, nextPos - prevPos - 1);` -> fixture line 36.
    live line 520 `value.data() + prevPos + 1, nextPos - prevPos - 1);` -> fixture line 66.
    tool under test: extract_function/find_identifiers/trace_identifier_backward/find_callers/find_definition/find_route_to_function.
    """
    target_path = "vms/server/nx_vms_server/src/database/server_db.cpp"
    source = """\
struct QByteArray
{
    static QByteArray fromRawData(const char* data, int size);
    const char* data() const;
    int size() const;
    int indexOf(char value, int start) const;
    bool isEmpty() const;
};

namespace vms::event {
struct ActionParameters {};
struct EventParameters {};
}

vms::event::ActionParameters convertOldActionParameters(const QByteArray& value)
{
    enum Param
    {
        UrlParam,
        ParamCount
    };

    vms::event::ActionParameters result;

    if (value.isEmpty())
        return result;

    int i = 0;
    int prevPos = -1;
    while (prevPos < value.size() && i < ParamCount)
    {
        int nextPos = value.indexOf('|', prevPos + 1);
        if (nextPos == -1)
            nextPos = value.size();

        QByteArray field(value.data() + prevPos + 1, nextPos - prevPos - 1);
        prevPos = nextPos;
        i++;
    }

    return result;
}

vms::event::EventParameters convertOldEventParameters(const QByteArray& value, int* actionResourceId)
{
    enum Param
    {
        EventTypeParam,
        ParamCount
    };

    vms::event::EventParameters result;

    if (value.isEmpty())
        return result;

    int i = 0;
    int prevPos = -1;
    while (prevPos < value.size() && i < ParamCount)
    {
        int nextPos = value.indexOf('|', prevPos + 1);
        if (nextPos == -1)
            nextPos = value.size();

        QByteArray field = QByteArray::fromRawData(
            value.data() + prevPos + 1, nextPos - prevPos - 1);
        if (!field.isEmpty())
            *actionResourceId = i;

        ++i;
        prevPos = nextPos;
    }

    return result;
}

void serializeLegacyAction(const QByteArray& packed)
{
    auto ap = convertOldActionParameters(packed);
    (void) ap;
}

void serializeLegacyEvent(const QByteArray& packed, int* actionResourceId)
{
    auto rp = convertOldEventParameters(packed, actionResourceId);
    (void) rp;
}
"""
    _write_source_tree(tmp_path, target_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("9ce90895", target_path)
    imports = mcp_server.find_imports("9ce90895", target_path)
    extract_action = mcp_server.extract_function("9ce90895", target_path, 36)
    extract_event = mcp_server.extract_function("9ce90895", target_path, 66)
    identifiers_action = mcp_server.find_identifiers("9ce90895", target_path, 36)
    identifiers_event = mcp_server.find_identifiers("9ce90895", target_path, 66)
    trace_action = mcp_server.trace_identifier_backward("9ce90895", target_path, 36, "value")
    trace_event = mcp_server.trace_identifier_backward("9ce90895", target_path, 66, "value")
    callers_action = mcp_server.find_callers("9ce90895", target_path, "convertOldActionParameters")
    callers_event = mcp_server.find_callers("9ce90895", target_path, "convertOldEventParameters")
    definition_action = mcp_server.find_definition("9ce90895", "convertOldActionParameters")
    definition_event = mcp_server.find_definition("9ce90895", "convertOldEventParameters")
    route_action = mcp_server.find_route_to_function("9ce90895", "convertOldActionParameters")
    route_event = mcp_server.find_route_to_function("9ce90895", "convertOldEventParameters")

    assert classification["type"] == "production"
    assert imports == []
    assert mcp_server.find_decorators("9ce90895", target_path, 36) == []
    assert mcp_server.find_decorators("9ce90895", target_path, 66) == []

    assert extract_action["meta"]["code_on_line"] == "        QByteArray field(value.data() + prevPos + 1, nextPos - prevPos - 1);"
    assert extract_event["meta"]["code_on_line"] == "            value.data() + prevPos + 1, nextPos - prevPos - 1);"
    assert identifiers_action == {"reads": ["data", "nextPos", "prevPos", "value"], "writes": ["field"], "language": "cpp"}
    assert identifiers_event == {
        "reads": ["data", "fromRawData", "nextPos", "prevPos", "value"],
        "writes": ["field"],
        "language": "cpp",
    }
    assert trace_action == []
    assert trace_event == []
    assert callers_action == [
        {
            "file": target_path,
            "line": 79,
            "caller_function": "serializeLegacyAction",
            "snippet": "       78| {\n>>>    79|     auto ap = convertOldActionParameters(packed);\n       80|     (void) ap;",
        }
    ]
    assert callers_event == [
        {
            "file": target_path,
            "line": 85,
            "caller_function": "serializeLegacyEvent",
            "snippet": "       84| {\n>>>    85|     auto rp = convertOldEventParameters(packed, actionResourceId);\n       86|     (void) rp;",
        }
    ]
    assert definition_action == [{"file": target_path, "line": 15, "kind": "function"}]
    assert definition_event == [{"file": target_path, "line": 44, "kind": "function"}]
    assert route_action == []
    assert route_event == []


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
