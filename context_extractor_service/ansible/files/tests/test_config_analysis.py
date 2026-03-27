"""Tests for context_extractor.config_analysis tools."""
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from context_extractor.config_analysis import (
    classify_environment,
    extract_config_block,
    extract_env_variables,
    find_config_overrides,
    find_related_configs,
)
import context_extractor.config_analysis as config_analysis

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sample_project"


# ── classify_environment ─────────────────────────────────────────

class TestClassifyEnvironment:

    def test_dev_by_filename(self):
        result = classify_environment(".env.dev")
        assert result["environment"] == "dev"

    def test_prod_by_filename(self):
        result = classify_environment("docker-compose.prod.yml")
        assert result["environment"] == "production"

    def test_staging(self):
        result = classify_environment("config.staging.yaml")
        assert result["environment"] == "staging"

    def test_test_env(self):
        result = classify_environment("settings.test.py")
        assert result["environment"] == "test"

    def test_template(self):
        result = classify_environment(".env.example")
        assert result["environment"] == "template"

    def test_override_is_dev(self):
        result = classify_environment("docker-compose.override.yml")
        assert result["environment"] == "dev"

    def test_unknown(self):
        result = classify_environment("docker-compose.yml")
        assert result["environment"] == "unknown"

    def test_directory_indicator(self):
        result = classify_environment("deploy/prod/values.yaml")
        assert result["environment"] == "production"

    def test_k8s_production_namespace_dir(self):
        result = classify_environment("k8s/production/values.yaml")
        assert result["environment"] == "production"

    def test_ci_env_file(self):
        result = classify_environment(".env.ci")
        assert result["environment"] == "ci"

    def test_terraform_prod_vars(self):
        result = classify_environment("terraform.prod.tfvars")
        assert result["environment"] == "production"

    def test_config_analysis_facade_exports_split_module_entrypoints(self):
        assert callable(config_analysis.extract_env_variables)
        assert callable(config_analysis.find_config_overrides)
        assert callable(config_analysis.find_related_configs)


# ── extract_config_block ─────────────────────────────────────────

class TestExtractConfigBlock:

    def test_yaml_block(self):
        source = (FIXTURES / "docker-compose.yml").read_text()
        filepath = FIXTURES / "docker-compose.yml"
        # Line with "privileged: true" (line 12 approx)
        lines = source.splitlines()
        priv_line = next(
            i + 1 for i, l in enumerate(lines) if "privileged" in l
        )
        result = extract_config_block(source, filepath, priv_line)
        assert result["block_text"]
        assert result["start_line"] <= priv_line <= result["end_line"]
        assert result["language"] == "yaml"

    def test_dockerfile_block(self):
        source = (FIXTURES / "Dockerfile").read_text()
        filepath = FIXTURES / "Dockerfile"
        # Find the ENV line
        lines = source.splitlines()
        env_line = next(
            i + 1 for i, l in enumerate(lines) if l.startswith("ENV DD_DEBUG")
        )
        result = extract_config_block(source, filepath, env_line)
        assert result["block_text"]
        assert result["start_line"] <= env_line <= result["end_line"]

    def test_dotenv_block_fallback(self):
        source = (FIXTURES / ".env.dev").read_text()
        filepath = FIXTURES / ".env.dev"
        # .env files don't have tree-sitter grammar → indentation fallback
        result = extract_config_block(source, filepath, 2)
        assert result["block_text"]

    def test_toml_block(self):
        source = (FIXTURES / "config/pyproject.toml").read_text()
        filepath = FIXTURES / "config/pyproject.toml"
        lines = source.splitlines()
        secret_line = next(
            i + 1 for i, l in enumerate(lines) if "secret_key" in l and "changeme" in l
        )
        result = extract_config_block(source, filepath, secret_line)
        assert result["block_text"]
        assert result["language"] == "toml"
        assert "secret_key" in result["block_text"]

    def test_hcl_block(self):
        source = (FIXTURES / "infra/main.tf").read_text()
        filepath = FIXTURES / "infra/main.tf"
        lines = source.splitlines()
        var_line = next(
            i + 1 for i, l in enumerate(lines) if 'variable "db_password"' in l
        )
        result = extract_config_block(source, filepath, var_line)
        assert result["block_text"]
        assert result["language"] == "hcl"
        assert "db_password" in result["block_text"]

    def test_bash_block(self):
        source = (FIXTURES / "scripts/setup.sh").read_text()
        filepath = FIXTURES / "scripts/setup.sh"
        lines = source.splitlines()
        export_line = next(
            i + 1 for i, l in enumerate(lines) if "APP_ENV" in l
        )
        result = extract_config_block(source, filepath, export_line)
        assert result["block_text"]
        assert result["start_line"] <= export_line <= result["end_line"]
        assert result["language"] == "bash"


# ── extract_env_variables ────────────────────────────────────────

class TestExtractEnvVariables:

    def test_dotenv(self):
        source = (FIXTURES / ".env.dev").read_text()
        filepath = FIXTURES / ".env.dev"
        result = extract_env_variables(source, filepath)
        names = [v["name"] for v in result]
        assert "DD_DEBUG" in names
        assert "DD_SECRET_KEY" in names
        assert "POSTGRES_PASSWORD" in names
        # Secret pattern detection
        secret_vars = [v for v in result if v["has_secret_pattern"]]
        secret_names = [v["name"] for v in secret_vars]
        assert "DD_SECRET_KEY" in secret_names
        assert "POSTGRES_PASSWORD" in secret_names

    def test_dockerfile_env(self):
        source = (FIXTURES / "Dockerfile").read_text()
        filepath = FIXTURES / "Dockerfile"
        result = extract_env_variables(source, filepath)
        names = [v["name"] for v in result]
        assert "DD_DEBUG" in names
        assert "DD_SECRET_KEY" in names
        secret_vars = [v for v in result if v["has_secret_pattern"]]
        assert any(v["name"] == "DD_SECRET_KEY" for v in secret_vars)

    def test_dockerfile_arg_and_quoted_env_values(self):
        source = 'ARG BUILD_MODE=prod\nENV APP_NAME="api service"\nARG EMPTY_ARG\n'

        result = extract_env_variables(source, Path("Dockerfile"))

        assert result == [
            {
                "name": "BUILD_MODE",
                "value": "prod",
                "source": "ARG",
                "line": 1,
                "has_secret_pattern": False,
            },
            {
                "name": "APP_NAME",
                "value": "api service",
                "source": "ENV",
                "line": 2,
                "has_secret_pattern": False,
            },
            {
                "name": "EMPTY_ARG",
                "value": "",
                "source": "ARG",
                "line": 3,
                "has_secret_pattern": False,
            },
        ]

    def test_yaml_environment_section(self):
        source = (FIXTURES / "docker-compose.yml").read_text()
        filepath = FIXTURES / "docker-compose.yml"
        result = extract_env_variables(source, filepath)
        names = [v["name"] for v in result]
        assert "DD_DEBUG" in names or "DD_SECRET_KEY" in names

    def test_yaml_environment_list_style_values(self):
        source = (
            "services:\n"
            "  web:\n"
            "    environment:\n"
            "      - APP_ENV=prod\n"
            "      - API_TOKEN=${API_TOKEN}\n"
        )

        result = extract_env_variables(source, Path("docker-compose.yml"))

        assert result == [
            {
                "name": "APP_ENV",
                "value": "prod",
                "source": "yaml_environment",
                "line": 4,
                "has_secret_pattern": False,
            },
            {
                "name": "API_TOKEN",
                "value": "${API_TOKEN}",
                "source": "yaml_environment",
                "line": 5,
                "has_secret_pattern": True,
            },
        ]

    def test_bash_export_vars(self):
        source = (FIXTURES / "scripts/setup.sh").read_text()
        filepath = FIXTURES / "scripts/setup.sh"
        result = extract_env_variables(source, filepath)
        names = [v["name"] for v in result]
        # Exported variables declared with `export`
        assert "APP_ENV" in names
        assert "DB_PASSWORD" in names
        # Secret pattern detection for sensitive exports
        secret_names = [v["name"] for v in result if v["has_secret_pattern"]]
        assert "DB_PASSWORD" in secret_names
        assert "API_KEY" in secret_names

    def test_bash_assignment_vars(self):
        source = (FIXTURES / "scripts/setup.sh").read_text()
        filepath = FIXTURES / "scripts/setup.sh"
        result = extract_env_variables(source, filepath)
        names = [v["name"] for v in result]
        # Non-exported top-level assignments should also be captured
        assert "DB_HOST" in names or "DB_PORT" in names


# ── find_config_overrides ────────────────────────────────────────

class TestFindConfigOverrides:

    def test_find_dd_debug_override(self):
        results = find_config_overrides(FIXTURES, ".env.dev", "DD_DEBUG")
        files = [r["file"] for r in results]
        # DD_DEBUG should appear in .env.prod, docker-compose.yml,
        # docker-compose.prod.yml, or Dockerfile
        assert len(results) >= 1

    def test_find_secret_key_override(self):
        results = find_config_overrides(FIXTURES, ".env.dev", "DD_SECRET_KEY")
        # Should find it in .env.prod (with vault reference)
        assert len(results) >= 1
        prod_results = [r for r in results if r["environment"] == "production"]
        assert len(prod_results) >= 1

    def test_no_override_for_random_key(self):
        results = find_config_overrides(FIXTURES, ".env.dev", "NONEXISTENT_KEY_XYZ")
        assert len(results) == 0


# ── find_related_configs ─────────────────────────────────────────

class TestFindRelatedConfigs:

    def test_compose_finds_env_files(self):
        results = find_related_configs(FIXTURES, "docker-compose.yml")
        files = [r["file"] for r in results]
        relationships = [r["relationship"] for r in results]
        # Should find .env.dev, .env.prod, docker-compose.prod.yml, Dockerfile
        assert len(results) >= 2
        assert any("env" in rel for rel in relationships)

    def test_dockerfile_finds_compose(self):
        results = find_related_configs(FIXTURES, "Dockerfile")
        relationships = [r["relationship"] for r in results]
        assert any("compose" in rel for rel in relationships)

    def test_env_variants(self):
        results = find_related_configs(FIXTURES, ".env.dev")
        files = [r["file"] for r in results]
        assert any(".env.prod" in f for f in files)

    def test_terraform_module_peers(self):
        # main.tf and variables.tf in the same directory → terraform_module_peer
        results = find_related_configs(FIXTURES, "infra/main.tf")
        relationships = [r["relationship"] for r in results]
        assert any("terraform" in rel for rel in relationships)
        files = [r["file"] for r in results]
        assert any("variables.tf" in f for f in files)

    def test_k8s_peer_resources(self):
        # deployment.yaml and service.yaml in the same k8s/ dir → k8s_peer_resource
        results = find_related_configs(FIXTURES, "k8s/deployment.yaml")
        relationships = [r["relationship"] for r in results]
        assert any("k8s" in rel for rel in relationships)
        files = [r["file"] for r in results]
        assert any("service.yaml" in f for f in files)
