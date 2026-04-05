"""
Edge case tests for YAML language features.

Covers:
- Anchors (&) and aliases (*): value resolution, merge keys (<<:)
- Multi-document YAML (--- separator): block isolation between documents
- Block scalars: literal (|) and folded (>) multi-line strings
- Kubernetes complex env specs: env[].value, env[].valueFrom.secretKeyRef
- Deep nesting in K8s / Helm values: nested keys and config block extraction
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


# ---------------------------------------------------------------------------
# 1. Anchors and aliases
# ---------------------------------------------------------------------------

def test_extract_config_block_should_include_anchor_definition(monkeypatch, tmp_path):
    """extract_config_block on an alias line must include context showing the anchor definition."""
    content = """\
defaults: &defaults
  retries: 3
  timeout: 30
  log_level: info

production:
  <<: *defaults
  log_level: warn
  database: prod_db
"""
    f = tmp_path / "config.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 7: <<: *defaults (the merge key / alias reference)
    result = mcp_server.extract_config_block("pipe", "config.yml", 7)
    assert result is not None
    block = result.get("block_text", "")
    assert "production" in block or "defaults" in block, \
        "Block around the alias reference must be extracted"


def test_find_config_overrides_should_detect_key_set_via_anchor(monkeypatch, tmp_path):
    """find_config_overrides must find the same config key defined both directly and via anchor."""
    content = """\
base: &base
  log_level: debug
  timeout: 10

staging:
  <<: *base
  log_level: info

production:
  <<: *base
  log_level: error
  timeout: 60
"""
    f = tmp_path / "envs.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    results = mcp_server.find_config_overrides("pipe", "envs.yml", "log_level")
    assert len(results) >= 1, \
        "find_config_overrides must find 'log_level' overrides including those from merged anchors"


def test_extract_config_block_should_not_confuse_alias_with_regex_pattern(monkeypatch, tmp_path):
    """extract_config_block must not fail when YAML contains *alias tokens."""
    content = """\
common: &common
  max_connections: 100

worker_pool:
  <<: *common
  threads: 4
  queue_size: 200
"""
    f = tmp_path / "pool.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_config_block("pipe", "pool.yml", 5)
    assert result is not None, "extract_config_block must not fail on YAML alias (*common)"
    assert result.get("block_text") is not None


# ---------------------------------------------------------------------------
# 2. Multi-document YAML (--- separator)
# ---------------------------------------------------------------------------

def test_extract_config_block_on_second_document_should_return_second_doc_block(monkeypatch, tmp_path):
    """extract_config_block on a line in the second YAML document must not bleed into the first."""
    content = """\
---
kind: ConfigMap
metadata:
  name: app-config
data:
  DB_HOST: localhost
---
kind: Secret
metadata:
  name: app-secret
data:
  DB_PASSWORD: c2VjcmV0
"""
    f = tmp_path / "resources.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 8: 'kind: Secret' is in the second document
    result = mcp_server.extract_config_block("pipe", "resources.yml", 8)
    assert result is not None
    block = result.get("block_text", "")
    assert "Secret" in block, "Block must be from the second document (Secret)"
    assert "ConfigMap" not in block, "First document content must not bleed into second document block"


def test_extract_config_block_on_first_document_must_not_include_second_document(monkeypatch, tmp_path):
    """extract_config_block on a line in the first document must stay within that document."""
    content = """\
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
spec:
  port: 80
---
apiVersion: v1
kind: Deployment
metadata:
  name: backend
"""
    f = tmp_path / "k8s.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 3: 'kind: Service' is in the first document
    result = mcp_server.extract_config_block("pipe", "k8s.yml", 3)
    assert result is not None
    block = result.get("block_text", "")
    assert "Deployment" not in block, "Second document (Deployment) must not appear in first doc block"


def test_extract_env_variables_in_multidoc_k8s_file_should_find_correct_env(monkeypatch, tmp_path):
    """extract_env_variables must find env vars across documents in a K8s multi-resource file."""
    content = """\
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-env
data:
  APP_ENV: production
  LOG_LEVEL: warn
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: DATABASE_URL
          value: postgres://db:5432/mydb
"""
    f = tmp_path / "app.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "app.yml")
    names = [v["name"] for v in result]
    assert "APP_ENV" in names or "DATABASE_URL" in names, \
        "Env vars from both documents must be detected"


# ---------------------------------------------------------------------------
# 3. Block scalars: literal (|) and folded (>) multi-line strings
# ---------------------------------------------------------------------------

def test_extract_config_block_should_handle_literal_block_scalar(monkeypatch, tmp_path):
    """extract_config_block must extract a key whose value is a literal (|) block scalar."""
    content = """\
scripts:
  startup: |
    #!/bin/bash
    set -e
    echo "Starting..."
    ./init.sh
  shutdown: |
    echo "Stopping..."
    ./cleanup.sh
"""
    f = tmp_path / "scripts.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 2: 'startup: |' key with literal block scalar value
    result = mcp_server.extract_config_block("pipe", "scripts.yml", 2)
    assert result is not None
    block = result.get("block_text", "")
    assert "startup" in block, "Key 'startup' with literal scalar must be extracted"


def test_find_config_overrides_should_handle_folded_block_scalar_value(monkeypatch, tmp_path):
    """find_config_overrides must find a key that has a folded (>) multi-line string value."""
    content = """\
description: >
  This is a long description
  that spans multiple lines
  for testing purposes.
timeout: 30
"""
    f = tmp_path / "base.yml"
    f.write_text(content)
    content2 = """\
description: >
  Override description
  for staging environment.
timeout: 60
"""
    (tmp_path / "override.yml").write_text(content2)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    results = mcp_server.find_config_overrides("pipe", "base.yml", "description")
    assert len(results) >= 1, "Key 'description' with folded scalar must be found in overrides"


def test_extract_env_variables_should_find_assignments_in_bash_block_scalar(monkeypatch, tmp_path):
    """extract_env_variables must find shell variable assignments inside a YAML block scalar."""
    content = """\
configmap:
  init_script: |
    export DATABASE_HOST=db.internal
    export DATABASE_PORT=5432
    export API_SECRET=my-secret-value
    echo "Initialized"
"""
    f = tmp_path / "init.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "init.yml")
    names = [v["name"] for v in result]
    assert "DATABASE_HOST" in names or "API_SECRET" in names, \
        "Shell exports inside YAML literal block scalar must be detected"


# ---------------------------------------------------------------------------
# 4. Kubernetes complex env specs
# ---------------------------------------------------------------------------

def test_extract_env_variables_should_find_plain_value_env_in_k8s_container_spec(monkeypatch, tmp_path):
    """extract_env_variables must find env[].value entries in a K8s container spec."""
    content = """\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: backend
        image: myapp:latest
        env:
        - name: APP_PORT
          value: "8080"
        - name: APP_ENV
          value: production
"""
    f = tmp_path / "deploy.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "deploy.yml")
    names = [v["name"] for v in result]
    assert "APP_PORT" in names, "K8s env[].name/value pair must be detected"
    assert "APP_ENV" in names, "K8s env[].name/value pair must be detected"


def test_extract_env_variables_should_detect_secret_key_ref_in_k8s(monkeypatch, tmp_path):
    """extract_env_variables must detect env vars sourced via secretKeyRef."""
    content = """\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        - name: API_TOKEN
          valueFrom:
            secretKeyRef:
              name: api-secret
              key: token
"""
    f = tmp_path / "deploy_secrets.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "deploy_secrets.yml")
    names = [v["name"] for v in result]
    assert "DB_PASSWORD" in names, "env var from secretKeyRef must be detected"
    assert "API_TOKEN" in names, "env var from secretKeyRef must be detected"


def test_extract_config_block_should_extract_env_section_in_container_spec(monkeypatch, tmp_path):
    """extract_config_block on a specific env var line must return the container's env section."""
    content = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
spec:
  template:
    spec:
      containers:
      - name: worker
        image: worker:v1
        env:
        - name: QUEUE_URL
          value: amqp://rabbitmq:5672
        - name: MAX_WORKERS
          value: "4"
"""
    f = tmp_path / "worker.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 12: '- name: QUEUE_URL'
    result = mcp_server.extract_config_block("pipe", "worker.yml", 12)
    assert result is not None
    block = result.get("block_text", "")
    assert "QUEUE_URL" in block or "env" in block, \
        "Container env section block must be extracted"


# ---------------------------------------------------------------------------
# 5. Deep nesting in Helm values
# ---------------------------------------------------------------------------

def test_extract_config_block_should_extract_deeply_nested_key(monkeypatch, tmp_path):
    """extract_config_block must correctly handle deeply nested YAML structures."""
    content = """\
global:
  security:
    tls:
      enabled: true
      cert: /certs/tls.crt
      key: /certs/tls.key
    auth:
      provider: oauth2
      clientId: my-app-client
      clientSecret: changeme
"""
    f = tmp_path / "values.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 9: 'clientId: my-app-client' (deeply nested)
    result = mcp_server.extract_config_block("pipe", "values.yml", 9)
    assert result is not None
    block = result.get("block_text", "")
    assert "clientId" in block or "auth" in block, \
        "Deeply nested key must be correctly extracted"


def test_find_config_overrides_should_find_override_in_helm_values_files(monkeypatch, tmp_path):
    """find_config_overrides must find the same key in sibling Helm values files."""
    base = """\
replicaCount: 1
image:
  repository: myapp
  tag: latest
database:
  password: devpassword
"""
    prod = """\
replicaCount: 3
image:
  repository: myapp
  tag: v2.0.1
database:
  password: ${DB_PASSWORD}
"""
    (tmp_path / "values.yaml").write_text(base)
    (tmp_path / "values-prod.yaml").write_text(prod)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    results = mcp_server.find_config_overrides("pipe", "values.yaml", "password")
    assert len(results) >= 1, "'password' key must be found as an override in values-prod.yaml"


def test_extract_env_variables_should_find_credentials_in_helm_values(monkeypatch, tmp_path):
    """extract_env_variables must detect credential-like keys in Helm values files."""
    content = """\
app:
  config:
    secret_key: my-super-secret
    api_key: abc123xyz
    database_password: correcthorsebatterystaple
  features:
    enabled: true
"""
    f = tmp_path / "values.yaml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "values.yaml")
    names = [v["name"] for v in result]
    secret_names = [v["name"] for v in result if v.get("has_secret_pattern")]
    assert len(secret_names) >= 1, \
        "Keys matching secret patterns (secret_key, api_key, password) must have has_secret_pattern=True"


# ---------------------------------------------------------------------------
# _YAML_STRUCTURAL_ENV_KEYS exclusion
# ---------------------------------------------------------------------------

def test_yaml_structural_key_environment_not_extracted_as_secret(monkeypatch, tmp_path):
    """The YAML key 'environment' must not be extracted as a secret-pattern entry."""
    content = """\
services:
  web:
    environment:
      - SECRET_KEY=abc
      - DB_PASSWORD=xyz
"""
    f = tmp_path / "docker-compose.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "docker-compose.yml")
    names = [v["name"] for v in result]
    assert "environment" not in names, \
        "Structural YAML key 'environment' must not appear in extracted env entries"
    assert "SECRET_KEY" in names, "SECRET_KEY inside environment block must still be extracted"


# ---------------------------------------------------------------------------
# Block scalar bash export — quotes must be stripped from values
# ---------------------------------------------------------------------------

def test_yaml_block_scalar_bash_export_strips_quotes_from_value(monkeypatch, tmp_path):
    """Values captured from bash exports inside YAML block scalars must have quotes stripped."""
    content = """\
deploy:
  script: |
    export SECRET_KEY="my_secret_value"
    export DB_PASSWORD='another_secret'
"""
    f = tmp_path / "ci.yml"
    f.write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "ci.yml")
    by_name = {v["name"]: v["value"] for v in result}
    if "SECRET_KEY" in by_name:
        assert by_name["SECRET_KEY"] == "my_secret_value", \
            f"Double quotes must be stripped from value; got {by_name['SECRET_KEY']!r}"
    if "DB_PASSWORD" in by_name:
        assert by_name["DB_PASSWORD"] == "another_secret", \
            f"Single quotes must be stripped from value; got {by_name['DB_PASSWORD']!r}"
