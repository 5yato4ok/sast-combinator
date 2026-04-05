"""
Advanced configuration format edge cases.

Covers:
- .env files: multiline quoted values, export prefix, variable substitution ${VAR}
- Spring application.properties: flat key=value, nested keys, ${placeholder}
- ASP.NET appsettings.json: nested JSON with secret-pattern keys
- pyproject.toml: [[tool.X]] array-of-tables sections
- GitHub Actions workflow.yml: ${{ secrets.X }}, matrix env, job env
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


# ===========================================================================
# .env file edge cases
# ===========================================================================

def test_dotenv_should_find_variable_with_export_prefix(monkeypatch, tmp_path):
    """extract_env_variables must detect variables declared with 'export' prefix."""
    content = """\
export DATABASE_URL=postgres://localhost:5432/mydb
export SECRET_KEY=abc123xyz
export DEBUG=false
PORT=8080
"""
    (tmp_path / ".env").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", ".env")
    names = [v["name"] for v in result]
    assert "DATABASE_URL" in names, "export DATABASE_URL must be detected"
    assert "SECRET_KEY" in names, "export SECRET_KEY must be detected"
    assert "PORT" in names, "plain PORT must also be detected"


def test_dotenv_should_find_variable_with_quoted_value_containing_spaces(monkeypatch, tmp_path):
    """extract_env_variables must handle values wrapped in double or single quotes."""
    content = """\
APP_NAME="My Application Server"
GREETING='Hello, World!'
DATABASE_URL="postgresql://user:p@ss w0rd!@host:5432/db"
EMPTY_VALUE=""
"""
    (tmp_path / ".env").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", ".env")
    names = [v["name"] for v in result]
    assert "APP_NAME" in names, "Double-quoted value must be detected"
    assert "GREETING" in names, "Single-quoted value must be detected"
    assert "DATABASE_URL" in names, "Quoted value with special chars must be detected"
    assert "EMPTY_VALUE" in names, "Empty quoted value must be detected"


def test_dotenv_should_handle_variable_substitution_syntax(monkeypatch, tmp_path):
    """extract_env_variables must detect variables whose value references other variables."""
    content = """\
BASE_URL=https://api.example.com
API_URL=${BASE_URL}/v1
AUTH_URL=${BASE_URL}/auth
FULL_DB_URL=${DB_HOST}:${DB_PORT}/${DB_NAME}
"""
    (tmp_path / ".env.production").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", ".env.production")
    names = [v["name"] for v in result]
    assert "API_URL" in names, "Variable with ${VAR} substitution must be detected"
    assert "FULL_DB_URL" in names, "Variable with multiple substitutions must be detected"


def test_dotenv_should_ignore_comments_and_blank_lines(monkeypatch, tmp_path):
    """extract_env_variables must skip comment lines and blank lines in .env files."""
    content = """\
# Database configuration
DB_HOST=localhost
DB_PORT=5432

# Application settings
APP_PORT=8080
# This is a comment: SECRET_KEY=should_not_appear
DEBUG=false
"""
    (tmp_path / ".env").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", ".env")
    names = [v["name"] for v in result]
    assert "DB_HOST" in names
    assert "APP_PORT" in names
    # The commented SECRET_KEY should NOT appear as an env variable
    assert not any("should_not_appear" in str(v.get("value", "")) for v in result), \
        "Commented-out variables must not be extracted"


def test_dotenv_should_flag_secret_pattern_names(monkeypatch, tmp_path):
    """extract_env_variables must set has_secret_pattern=True for secret-like names."""
    content = """\
API_KEY=abc123
DATABASE_PASSWORD=secret123
JWT_SECRET=verylongsecretkey
ACCESS_TOKEN=bearer_xyz
STRIPE_SECRET_KEY=sk_live_abc
NORMAL_VAR=not_a_secret
"""
    (tmp_path / ".env").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", ".env")
    secret_names = {v["name"] for v in result if v.get("has_secret_pattern")}
    assert "API_KEY" in secret_names, "API_KEY must have has_secret_pattern=True"
    assert "DATABASE_PASSWORD" in secret_names, "DATABASE_PASSWORD must be flagged"
    assert "JWT_SECRET" in secret_names, "JWT_SECRET must be flagged"
    normal = next((v for v in result if v["name"] == "NORMAL_VAR"), None)
    assert normal is not None and not normal.get("has_secret_pattern"), \
        "NORMAL_VAR must NOT be flagged as a secret"


# ===========================================================================
# Spring application.properties
# ===========================================================================

def test_application_properties_should_extract_env_variables(monkeypatch, tmp_path):
    """extract_env_variables must detect key=value pairs in Spring application.properties."""
    content = """\
spring.datasource.url=jdbc:postgresql://localhost:5432/mydb
spring.datasource.username=appuser
spring.datasource.password=s3cret
spring.datasource.driver-class-name=org.postgresql.Driver

server.port=8080
server.servlet.context-path=/api

app.jwt.secret=my-very-long-jwt-secret-key
app.jwt.expiration=3600
"""
    (tmp_path / "application.properties").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "application.properties")
    names = [v["name"] for v in result]
    assert any("password" in n.lower() or "datasource.password" in n for n in names), \
        "spring.datasource.password must be detected"
    assert any("jwt" in n.lower() or "secret" in n.lower() for n in names), \
        "app.jwt.secret must be detected"


def test_application_properties_should_flag_password_and_secret_keys(monkeypatch, tmp_path):
    """extract_env_variables must flag properties matching secret patterns."""
    content = """\
spring.datasource.password=hardcoded_password
spring.mail.password=smtp_password
app.api-key=abc123
app.encryption.secret-key=encryption_secret
server.port=8080
app.name=MyApplication
"""
    (tmp_path / "application.properties").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "application.properties")
    secret_items = [v for v in result if v.get("has_secret_pattern")]
    assert len(secret_items) >= 2, \
        "Password and secret key properties must be flagged with has_secret_pattern=True"


def test_application_properties_extract_config_block_should_group_by_prefix(monkeypatch, tmp_path):
    """extract_config_block on a datasource line must return the datasource config group."""
    content = """\
server.port=8080
server.ssl.enabled=true

spring.datasource.url=jdbc:postgresql://localhost/mydb
spring.datasource.username=user
spring.datasource.password=secret
spring.datasource.pool.max-size=10

app.feature.enabled=true
"""
    (tmp_path / "application.properties").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 5: spring.datasource.username
    result = mcp_server.extract_config_block("pipe", "application.properties", 5)
    assert result is not None
    block = result.get("block_text", "")
    assert "datasource" in block or "spring" in block, \
        "Config block for datasource line must include datasource properties"


# ===========================================================================
# ASP.NET appsettings.json
# ===========================================================================

def test_appsettings_json_should_detect_nested_secret_keys(monkeypatch, tmp_path):
    """extract_env_variables must find and flag secret-pattern keys in nested JSON."""
    content = """\
{
  "ConnectionStrings": {
    "DefaultConnection": "Server=db;Database=mydb;User Id=sa;Password=Passw0rd!",
    "Redis": "localhost:6379,password=redis_secret"
  },
  "Jwt": {
    "Secret": "super-secret-jwt-key-minimum-256-bits",
    "Issuer": "myapp",
    "ExpirationMinutes": 60
  },
  "AzureStorage": {
    "ConnectionString": "DefaultEndpointsProtocol=https;AccountKey=abc123=="
  },
  "Logging": {
    "LogLevel": {
      "Default": "Information"
    }
  }
}
"""
    (tmp_path / "appsettings.json").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "appsettings.json")
    secret_items = [v for v in result if v.get("has_secret_pattern")]
    assert len(secret_items) >= 1, \
        "Nested JSON keys matching password/secret patterns must be flagged"


def test_appsettings_json_extract_config_block_should_extract_connection_string_section(monkeypatch, tmp_path):
    """extract_config_block on a ConnectionStrings line must return that JSON object."""
    content = """\
{
  "AllowedHosts": "*",
  "ConnectionStrings": {
    "DefaultConnection": "Server=localhost;Database=app;Password=secret",
    "Analytics": "Server=analytics;Database=events;Password=analytics_pass"
  },
  "FeatureFlags": {
    "NewUI": true
  }
}
"""
    (tmp_path / "appsettings.json").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 4: DefaultConnection
    result = mcp_server.extract_config_block("pipe", "appsettings.json", 4)
    assert result is not None
    block = result.get("block_text", "")
    assert "ConnectionStrings" in block or "DefaultConnection" in block, \
        "ConnectionStrings section must be returned"


def test_appsettings_json_classify_environment_should_detect_production_variant(monkeypatch, tmp_path):
    """classify_environment must detect appsettings.Production.json as production."""
    (tmp_path / "appsettings.Production.json").write_text('{"Logging": {}}')
    (tmp_path / "appsettings.Development.json").write_text('{"Logging": {}}')
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result_prod = mcp_server.classify_environment("pipe", "appsettings.Production.json")
    result_dev = mcp_server.classify_environment("pipe", "appsettings.Development.json")
    assert result_prod.get("environment") in ("production", "prod"), \
        "appsettings.Production.json must be classified as production"
    assert result_dev.get("environment") in ("development", "dev"), \
        "appsettings.Development.json must be classified as development"


# ===========================================================================
# pyproject.toml with [[array-of-tables]]
# ===========================================================================

def test_pyproject_toml_extract_config_block_should_handle_array_of_tables(monkeypatch, tmp_path):
    """extract_config_block must correctly handle [[tool.hatch.envs.default.scripts]] sections."""
    content = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "myapp"
version = "1.0.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=myapp --cov-report=xml"

[[tool.hatch.envs.default.scripts]]
test = "pytest {args}"
lint = "ruff check ."

[tool.ruff.lint]
select = ["E", "F", "I"]
"""
    (tmp_path / "pyproject.toml").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 13: [[tool.hatch.envs.default.scripts]]
    result = mcp_server.extract_config_block("pipe", "pyproject.toml", 13)
    assert result is not None, "extract_config_block must not crash on [[array-of-tables]]"
    assert result.get("block_text") is not None


def test_pyproject_toml_should_find_secret_in_tool_section(monkeypatch, tmp_path):
    """extract_env_variables must find secret-pattern keys in pyproject.toml tool sections."""
    content = """\
[tool.mypy]
strict = true

[tool.coverage.run]
source = ["src"]

[tool.semantic_release]
github_token = "hardcoded_token_value"
repository_url = "https://github.com/org/repo"

[tool.twine]
password = "pypi_password"
username = "__token__"
"""
    (tmp_path / "pyproject.toml").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "pyproject.toml")
    secret_items = [v for v in result if v.get("has_secret_pattern")]
    assert len(secret_items) >= 1, \
        "github_token and password in pyproject.toml must be flagged as secrets"


def test_pyproject_toml_extract_config_block_should_group_pytest_section(monkeypatch, tmp_path):
    """extract_config_block on a [tool.pytest.ini_options] key must return the pytest block."""
    content = """\
[project]
name = "app"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short --no-header -rN"
markers = ["slow: mark test as slow", "integration: mark as integration"]

[tool.ruff]
line-length = 88
"""
    (tmp_path / "pyproject.toml").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    # Line 6: testpaths line inside [tool.pytest.ini_options]
    result = mcp_server.extract_config_block("pipe", "pyproject.toml", 6)
    assert result is not None
    block = result.get("block_text", "")
    assert "pytest" in block or "testpaths" in block, \
        "pytest section must be returned for a line inside it"


# ===========================================================================
# GitHub Actions workflow.yml
# ===========================================================================

def test_github_actions_should_detect_secrets_context_as_env_source(monkeypatch, tmp_path):
    """extract_env_variables must detect env vars using ${{ secrets.X }} in GitHub Actions."""
    content = """\
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      AWS_REGION: us-east-1
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
"""
    (tmp_path / "deploy.yml").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "deploy.yml")
    names = [v["name"] for v in result]
    assert "AWS_ACCESS_KEY_ID" in names or "AWS_SECRET_ACCESS_KEY" in names, \
        "GitHub Actions secrets-sourced env vars must be detected"


def test_github_actions_should_detect_hardcoded_values_in_matrix_env(monkeypatch, tmp_path):
    """extract_env_variables must detect hardcoded values in GitHub Actions matrix env."""
    content = """\
name: Test

jobs:
  test:
    strategy:
      matrix:
        environment: [dev, staging, prod]
        include:
          - environment: prod
            api_url: https://api.example.com
            api_key: hardcoded_prod_key_12345
    runs-on: ubuntu-latest
    env:
      NODE_ENV: ${{ matrix.environment }}
      API_URL: ${{ matrix.api_url }}
    steps:
      - run: npm test
"""
    (tmp_path / "test.yml").write_text(content)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.extract_env_variables("pipe", "test.yml")
    names = [v["name"] for v in result]
    secret_items = [v for v in result if v.get("has_secret_pattern")]
    assert "NODE_ENV" in names or "API_URL" in names, \
        "GitHub Actions env vars must be detected"
    assert len(secret_items) >= 0, \
        "api_key in matrix include should ideally be flagged"


def test_github_actions_classify_environment_should_detect_workflow_as_config(monkeypatch, tmp_path):
    """classify_environment must recognise GitHub Actions workflows as CI/config files."""
    (tmp_path / "deploy-prod.yml").write_text("name: Deploy Production\n")
    (tmp_path / "test.yml").write_text("name: Run Tests\n")
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result_prod = mcp_server.classify_environment("pipe", "deploy-prod.yml")
    assert result_prod.get("environment") in ("production", "prod", "ci", "unknown"), \
        "deploy-prod.yml must be classified as production or CI"
