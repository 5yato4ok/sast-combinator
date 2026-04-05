import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config_analysis import (
    extract_config_block,
    extract_env_variables,
    find_config_overrides,
    find_related_configs,
)


def test_extract_config_block_should_keep_exact_privileged_block():
    compose_source = (
        "services:\n"
        "  worker:\n"
        "    privileged: true\n"
        "    environment:\n"
        "      DB_PASSWORD: ${DB_PASSWORD}\n"
    )

    block = extract_config_block(compose_source, Path("docker-compose.dev.yml"), 3)

    assert block == {
        "block_text": "privileged: true",
        "block_type": "block_mapping_pair",
        "key_path": "services.worker.privileged",
        "start_line": 3,
        "end_line": 3,
        "language": "yaml",
    }


def test_extract_env_variables_should_keep_exact_secret_placeholders():
    compose_source = (
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      DB_PASSWORD: ''\n"
        "      API_TOKEN: ${API_TOKEN}\n"
    )

    env_vars = extract_env_variables(compose_source, Path("docker-compose.dev.yml"))

    assert env_vars == [
        {
            "name": "DB_PASSWORD",
            "value": "",
            "source": "yaml_environment",
            "line": 4,
            "has_secret_pattern": True,
        },
        {
            "name": "API_TOKEN",
            "value": "${API_TOKEN}",
            "source": "yaml_environment",
            "line": 5,
            "has_secret_pattern": True,
        },
    ]


def test_find_config_overrides_should_keep_exact_production_override_hit():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.dev").write_text("DB_PASSWORD=devpass\nAPI_TOKEN=\n")
        (root / ".env.prod").write_text("DB_PASSWORD=${DB_PASSWORD}\nAPI_TOKEN=${API_TOKEN}\n")

        db_overrides = find_config_overrides(root, ".env.dev", "DB_PASSWORD")
        api_overrides = find_config_overrides(root, ".env.dev", "API_TOKEN")

    assert db_overrides == [
        {
            "file": ".env.prod",
            "line": 1,
            "value": "DB_PASSWORD=${DB_PASSWORD}",
            "environment": "production",
        }
    ]
    assert api_overrides == [
        {
            "file": ".env.prod",
            "line": 2,
            "value": "API_TOKEN=${API_TOKEN}",
            "environment": "production",
        }
    ]


def test_find_related_configs_should_keep_expected_compose_relationships():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text("services:\n  web:\n    env_file: .env\n")
        (root / ".env").write_text("ADMIN_PASSWORD=${ADMIN_PASSWORD}\n")
        (root / "docker-compose.prod.yml").write_text(
            "services:\n  web:\n    build:\n      context: .\n      dockerfile: Dockerfile\n"
        )
        (root / "Dockerfile").write_text("FROM python:3.11\n")

        related = find_related_configs(root, "docker-compose.yml")

    assert related == [
        {"file": "Dockerfile", "relationship": "builds_dockerfile"},
        {"file": "docker-compose.prod.yml", "relationship": "compose_variant"},
        {"file": ".env", "relationship": "env_file"},
    ]


# ---------------------------------------------------------------------------
# find_config_overrides — classify_environment called once per file (cache)
# ---------------------------------------------------------------------------

def test_find_config_overrides_classify_environment_called_once_per_file(
    tmp_path, monkeypatch
):
    """classify_environment must be called at most once per unique file path."""
    (tmp_path / ".env.dev").write_text("DB_PASSWORD=devpass\nDB_PASSWORD=devpass2\n")
    (tmp_path / ".env.prod").write_text("DB_PASSWORD=${DB_PASSWORD}\n")

    import context_extractor.config_analysis.relations as rel_mod

    calls: list[str] = []
    original = rel_mod.classify_environment

    def tracking_classify(path: str) -> dict:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(rel_mod, "classify_environment", tracking_classify)

    find_config_overrides(tmp_path, ".env.dev", "DB_PASSWORD")

    # Each file path must appear at most once regardless of how many matching lines it has.
    assert calls.count(".env.dev") <= 1
    assert calls.count(".env.prod") <= 1
