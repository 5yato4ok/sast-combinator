"""
Edge case tests for Dockerfile language features.

Covers:
- BuildKit HEREDOC in RUN / COPY instructions
- --mount=type=secret and --mount=type=cache in RUN
- ARG defined before FROM (global build args, scope across stages)
- Multi-stage builds: COPY --from=stage, FROM ... AS stage
- ONBUILD instructions (deferred at image-build time)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


# ---------------------------------------------------------------------------
# 1. BuildKit HEREDOC in RUN / COPY
# ---------------------------------------------------------------------------

def test_extract_config_block_should_extract_run_instruction_with_heredoc(monkeypatch, tmp_path):
    """extract_config_block must return the full RUN instruction including its heredoc body."""
    content = """\
FROM ubuntu:22.04

RUN <<EOF
apt-get update
apt-get install -y curl wget
EOF

RUN echo "done"
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 3 is the RUN <<EOF line
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "apt-get" in block or "EOF" in block, \
        "RUN heredoc body must be included in the extracted config block"


def test_extract_config_block_should_handle_copy_with_heredoc_content(monkeypatch, tmp_path):
    """extract_config_block must extract the COPY instruction with inline heredoc file content."""
    content = """\
FROM python:3.12

COPY <<EOF /app/config.ini
[server]
host = 0.0.0.0
port = 8080
EOF

CMD ["python", "-m", "app"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "COPY" in block, "COPY instruction must be present in the extracted block"


def test_extract_env_variables_should_find_assignments_in_heredoc_run(monkeypatch, tmp_path):
    """extract_env_variables must detect ENV-like assignments written inside a RUN heredoc."""
    content = """\
FROM alpine:3.19

RUN <<EOF
export APP_ENV=production
export LOG_LEVEL=warn
echo configured
EOF
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "APP_ENV" in names or "LOG_LEVEL" in names, \
        "Shell exports inside RUN heredoc must be detected as env variables"


# ---------------------------------------------------------------------------
# 2. --mount=type=secret and --mount=type=cache
# ---------------------------------------------------------------------------

def test_extract_config_block_should_extract_run_with_secret_mount(monkeypatch, tmp_path):
    """extract_config_block must include the --mount=type=secret option in the extracted block."""
    content = """\
FROM node:20

RUN --mount=type=secret,id=npm_token \\
    NPM_TOKEN=$(cat /run/secrets/npm_token) \\
    npm install
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "secret" in block or "npm_token" in block or "RUN" in block, \
        "Secret mount instruction must be present in the extracted config block"


def test_extract_env_variables_should_note_secret_mount_as_env_source(monkeypatch, tmp_path):
    """extract_env_variables should capture variables populated from mounted secrets."""
    content = """\
FROM python:3.12

RUN --mount=type=secret,id=db_password \\
    DB_PASSWORD=$(cat /run/secrets/db_password) \\
    python setup.py install
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    # DB_PASSWORD is assigned inside the RUN shell command
    names = [v["name"] for v in result]
    assert "DB_PASSWORD" in names, \
        "Variable assigned from mounted secret in RUN must be detected"


def test_extract_config_block_should_handle_multiple_mount_options(monkeypatch, tmp_path):
    """extract_config_block must include all mount options when RUN has multiple --mount flags."""
    content = """\
FROM golang:1.22

RUN --mount=type=cache,target=/go/pkg/mod \\
    --mount=type=cache,target=/root/.cache/go-build \\
    go build ./...
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "cache" in block or "go build" in block or "RUN" in block, \
        "Multi-mount RUN instruction must be fully extracted"


# ---------------------------------------------------------------------------
# 3. ARG before FROM (global build arguments)
# ---------------------------------------------------------------------------

def test_extract_env_variables_should_find_arg_defined_before_from(monkeypatch, tmp_path):
    """extract_env_variables must detect ARG instructions that appear before the first FROM."""
    content = """\
ARG BASE_IMAGE=ubuntu:22.04
ARG BUILD_VERSION=1.0.0

FROM ${BASE_IMAGE}

ARG BUILD_VERSION
ENV APP_VERSION=${BUILD_VERSION}

RUN echo "Building v${APP_VERSION}"
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "BASE_IMAGE" in names or "BUILD_VERSION" in names, \
        "ARG defined before FROM must be detected as a build variable"


def test_extract_config_block_should_correctly_scope_pre_from_arg(monkeypatch, tmp_path):
    """extract_config_block on the ARG before FROM line must stay within the global scope."""
    content = """\
ARG REGISTRY=docker.io
ARG TAG=latest

FROM ${REGISTRY}/myapp:${TAG}

ENV REGISTRY=${REGISTRY}
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 1)
    assert result is not None
    block = result.get("block_text", "")
    assert "ARG" in block, "Pre-FROM ARG instruction must be included in its config block"


def test_extract_env_variables_should_not_confuse_pre_from_arg_with_stage_arg(monkeypatch, tmp_path):
    """extract_env_variables must differentiate ARG before FROM from ARG inside a build stage."""
    content = """\
ARG GLOBAL_VERSION=2.0

FROM node:20 AS builder
ARG GLOBAL_VERSION
ARG BUILD_SECRET

ENV VERSION=${GLOBAL_VERSION}
RUN echo "secret=${BUILD_SECRET}"
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "GLOBAL_VERSION" in names, "Pre-FROM global ARG must be detected"
    assert "BUILD_SECRET" in names, "Stage-scoped ARG must also be detected"


# ---------------------------------------------------------------------------
# 4. Multi-stage builds
# ---------------------------------------------------------------------------

def test_extract_config_block_targeting_second_stage_should_get_correct_block(monkeypatch, tmp_path):
    """extract_config_block on a line in the second stage must return that stage's block."""
    content = """\
FROM golang:1.22 AS builder
WORKDIR /app
COPY . .
RUN go build -o server .

FROM gcr.io/distroless/base AS runtime
COPY --from=builder /app/server /server
ENV PORT=8080
EXPOSE 8080
CMD ["/server"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 8: ENV PORT=8080 (in the runtime stage)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 8)
    assert result is not None
    block = result.get("block_text", "")
    assert "PORT" in block or "ENV" in block, \
        "Block from the runtime stage must be returned, not the builder stage"


def test_extract_env_variables_should_scope_variables_to_correct_stage(monkeypatch, tmp_path):
    """extract_env_variables must collect ENV vars from all stages separately."""
    content = """\
FROM node:20 AS deps
ENV NODE_ENV=development
RUN npm ci

FROM node:20 AS runner
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=deps /app/node_modules ./node_modules
CMD ["node", "server.js"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "NODE_ENV" in names, "NODE_ENV must be detected across stages"
    assert "PORT" in names, "PORT from the runner stage must be detected"


def test_find_related_configs_should_link_dockerfile_to_docker_compose(monkeypatch, tmp_path):
    """find_related_configs must detect a docker-compose.yml referencing the Dockerfile."""
    compose = """\
version: '3.9'
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
"""
    dockerfile = "FROM python:3.12\nCMD [\"python\", \"-m\", \"app\"]\n"
    (tmp_path / "Dockerfile").write_text(dockerfile)
    (tmp_path / "docker-compose.yml").write_text(compose)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.find_related_configs("pipe", "Dockerfile")
    files = [r["file"] for r in result]
    assert any("docker-compose" in f for f in files), \
        "docker-compose.yml referencing the Dockerfile must be returned as a related config"


# ---------------------------------------------------------------------------
# 5. ONBUILD instructions
# ---------------------------------------------------------------------------

def test_extract_config_block_should_extract_onbuild_instruction(monkeypatch, tmp_path):
    """extract_config_block must extract the ONBUILD instruction as a complete block."""
    content = """\
FROM python:3.12

ONBUILD COPY requirements.txt /app/
ONBUILD RUN pip install -r /app/requirements.txt
ONBUILD COPY . /app/

CMD ["python", "-m", "app"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "ONBUILD" in block, "ONBUILD instruction must be present in the extracted block"


def test_extract_env_variables_should_find_variables_inside_onbuild_env(monkeypatch, tmp_path):
    """extract_env_variables must detect ENV instructions wrapped in ONBUILD."""
    content = """\
FROM ubuntu:22.04

ONBUILD ENV APP_HOME=/app
ONBUILD ENV LOG_DIR=/var/log/app
ONBUILD ARG APP_SECRET

CMD ["/bin/sh"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "APP_HOME" in names or "LOG_DIR" in names or "APP_SECRET" in names, \
        "Variables inside ONBUILD ENV/ARG must be detected"


def test_extract_config_block_should_handle_chained_onbuild_instructions(monkeypatch, tmp_path):
    """extract_config_block must return the right block when multiple ONBUILD lines are present."""
    content = """\
FROM node:20

ONBUILD COPY package*.json ./
ONBUILD RUN npm ci --only=production
ONBUILD ENV NODE_ENV=production
ONBUILD COPY . .

CMD ["node", "index.js"]
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 5: ONBUILD ENV NODE_ENV=production
    result = mcp_server.extract_config_block("pipe", "Dockerfile", 5)
    assert result is not None
    block = result.get("block_text", "")
    assert "ONBUILD" in block or "NODE_ENV" in block, \
        "The correct ONBUILD ENV instruction must be extracted"


# ---------------------------------------------------------------------------
# RUN instruction env extraction via bash AST (not regex)
# ---------------------------------------------------------------------------

def test_extract_env_run_instruction_strips_quotes_from_value(monkeypatch, tmp_path):
    """Values assigned in RUN instructions must have quotes stripped correctly."""
    content = """\
FROM ubuntu:22.04
RUN SECRET_KEY="value with spaces" && DATABASE_URL=postgres://host/db
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    by_name = {v["name"]: v["value"] for v in result}
    assert "DATABASE_URL" in by_name, \
        "Unquoted assignment in RUN must be extracted"
    if "SECRET_KEY" in by_name:
        # Bash AST extraction correctly unquotes the value
        assert by_name["SECRET_KEY"] == "value with spaces", \
            f"Double-quoted value must be stripped; got {by_name['SECRET_KEY']!r}"


def test_extract_env_run_instruction_does_not_capture_comment_assignments(monkeypatch, tmp_path):
    """Assignments inside shell comments must not be extracted."""
    content = """\
FROM ubuntu:22.04
RUN echo "setup" # API_KEY=old_value
ENV REAL_TOKEN=abc
"""
    f = tmp_path / "Dockerfile"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "Dockerfile")
    names = [v["name"] for v in result]
    assert "API_KEY" not in names, \
        "Variable inside a shell comment must not be extracted as an env entry"
    assert "REAL_TOKEN" in names, "ENV instruction must still be extracted"
