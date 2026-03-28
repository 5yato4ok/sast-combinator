from _active_real_finding_audit_helpers import *
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
