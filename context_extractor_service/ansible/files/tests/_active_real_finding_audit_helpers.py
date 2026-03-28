import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor import project_analysis
from context_extractor.config_analysis import extract_config_block, find_related_configs
from context_extractor.extract import extract_function_from_source
from context_extractor.project_analysis import callers as project_analysis_callers

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

__all__ = [
    "AMS_SERVICE_CRASH_RECEIVER_DOCKERFILE",
    "TemporaryDirectory",
    "Path",
    "extract_config_block",
    "extract_function_from_source",
    "find_related_configs",
    "mcp_server",
    "project_analysis",
    "project_analysis_callers",
    "pytest",
    "_assert_trace_codes",
    "_stub_read_source",
    "_stub_resolve_source_dir",
    "_write_source_tree",
]


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
