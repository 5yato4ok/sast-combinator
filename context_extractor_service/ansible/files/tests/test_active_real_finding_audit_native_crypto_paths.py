from _active_real_finding_audit_helpers import *
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
