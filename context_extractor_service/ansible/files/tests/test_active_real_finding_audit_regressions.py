import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
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
