from _active_real_finding_audit_helpers import *
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
