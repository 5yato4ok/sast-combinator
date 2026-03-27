import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config_analysis import classify_environment, find_config_overrides, find_related_configs


def test_find_related_configs_should_keep_dockerfile_to_compose_reference():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.11\nCOPY . /app\n")
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == [{"file": "docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_find_related_configs_should_keep_env_and_variant_relationships():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text("services:\n  web:\n    env_file: .env\n")
        (root / ".env").write_text("ADMIN_PASSWORD=${ADMIN_PASSWORD}\n")
        (root / "docker-compose.prod.yml").write_text(
            "services:\n  web:\n    image: app\n",
        )

        related = find_related_configs(root, "docker-compose.yml")

    assert related == [
        {"file": "docker-compose.prod.yml", "relationship": "compose_variant"},
        {"file": ".env", "relationship": "env_file"},
    ]


def test_find_related_configs_should_prefer_compose_specific_relationship_over_generic_reference():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.12\n")
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == [{"file": "docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_find_related_configs_should_prefer_env_variant_over_generic_reference():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.dev").write_text("DB_PASSWORD=dev\n")
        (root / ".env.prod").write_text("DB_PASSWORD=prod\n# docs mention .env.dev\n")

        related = find_related_configs(root, ".env.dev")

    assert related == [{"file": ".env.prod", "relationship": "env_variant"}]


def test_find_config_overrides_should_keep_env_value_override_chain():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.dev").write_text("API_TOKEN=\nDEBUG=true\n")
        (root / ".env.prod").write_text("API_TOKEN=${API_TOKEN}\nDEBUG=false\n")

        overrides = find_config_overrides(root, ".env.dev", "API_TOKEN")

    assert overrides == [
        {
            "file": ".env.prod",
            "line": 1,
            "value": "API_TOKEN=${API_TOKEN}",
            "environment": "production",
        }
    ]


def test_classify_environment_should_keep_ci_and_dev_variants_distinct():
    assert classify_environment("docker-compose.prod.yml")["environment"] == "production"
    assert classify_environment("docker-compose.override.yml")["environment"] == "dev"
    assert classify_environment(".env.local")["environment"] == "dev"
