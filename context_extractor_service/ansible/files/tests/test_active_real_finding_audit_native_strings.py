from _active_real_finding_audit_helpers import *
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
