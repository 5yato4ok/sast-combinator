from _active_real_finding_audit_helpers import *
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
