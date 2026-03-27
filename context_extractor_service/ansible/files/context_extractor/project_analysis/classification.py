from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


FileClassifierPredicate = Callable[["FileClassificationContext"], bool]


@dataclass(frozen=True)
class FileClassification:
    file_type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class FileClassificationRule:
    predicate: FileClassifierPredicate
    result: FileClassification


@dataclass(frozen=True)
class FileClassificationContext:
    file_path: str
    source: str | None
    path: Path
    parts: tuple[str, ...]
    parts_lower: tuple[str, ...]
    name: str
    path_lower: str
    file_ext: str
    stem: str


_KNOWN_VENDORED_LIBS = frozenset({
    "jquery", "bootstrap", "lodash", "underscore", "backbone", "angular",
    "react", "vue", "moment", "tinymce", "ckeditor", "d3", "three",
    "popper", "axios", "zepto", "mootools", "prototype", "dojo",
    "handlebars", "mustache", "knockout", "ember", "highcharts",
    "chartjs", "sweetalert", "select2", "datatables", "codemirror",
})
_CONFIG_CONTENT_RE = re.compile(
    r"(?i)(?:password|passwd|secret|token|api_?key|private_?key|credential|"
    r"smtp|database_url|redis_url|connection_string|bucket|endpoint|"
    r"access_key|auth|oauth|certificate)",
)
_TEST_DIR_PATTERNS = frozenset({
    "test", "tests", "spec", "specs", "__tests__", "test_utils", "testing", "testdata",
})
_TEST_FILE_PATTERNS = (
    "test_*", "*_test.*", "*_spec.*", "*.test.*", "*.spec.*", "conftest.py", "fixtures.*",
)
_MIGRATION_MARKERS = frozenset({
    "migrations", "alembic", "db/migrate", "flyway", "liquibase", "knex/migrations",
})
_VENDORED_ROOTS = frozenset({
    "vendor", "third_party", "node_modules", "packages", "bower_components", "external", "deps",
})
_VENDORED_NESTED = frozenset({
    "vendor", "node_modules", "packages", "bower_components", "external", "deps",
})
_GENERATED_MARKERS = frozenset({"generated", "autogen", "proto", ".gen."})
_CONFIG_NAMES = frozenset({
    "settings.py", "config.py", "config.yaml", "config.yml", "config.json", "config.toml", ".env",
    ".env.example", "webpack.config.js", "tsconfig.json", "pyproject.toml", "setup.cfg", "setup.py",
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "makefile", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
})
_INFRA_CONFIG_EXTS = frozenset({".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env"})
_CONFIG_FILE_PATTERNS = ("*config*", "*settings*", "*.jenkins.*")
_CI_NAMES = frozenset({"jenkinsfile", "vagrantfile", "rakefile", ".travis.yml", "appveyor.yml", ".gitlab-ci.yml"})
_DEPLOY_DIRS = frozenset({"deploy", ".circleci", ".gitlab", "build_scripts", "deploy_scripts", "infra", "infrastructure"})
_TOOLING_PREFIXES = ("etc/scripts", "tools/scripts")
_CONTENT_CHECK_EXTS = frozenset({".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties", ".env"})


def _make_classification_result(result: FileClassification) -> dict[str, Any]:
    return {"type": result.file_type, "confidence": result.confidence, "reason": result.reason}


def _in_parts(ctx: FileClassificationContext, values: frozenset[str]) -> bool:
    return any(part in values for part in ctx.parts_lower)


def _matches_any_pattern(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _has_test_dir(ctx: FileClassificationContext) -> bool:
    return _in_parts(ctx, _TEST_DIR_PATTERNS)


def _has_test_filename(ctx: FileClassificationContext) -> bool:
    return _matches_any_pattern(ctx.name, _TEST_FILE_PATTERNS)


def _has_migration_marker(ctx: FileClassificationContext) -> bool:
    return any(marker in ctx.path_lower for marker in _MIGRATION_MARKERS)


def _is_vendored_root(ctx: FileClassificationContext) -> bool:
    return bool(ctx.parts_lower and ctx.parts_lower[0] in _VENDORED_ROOTS)


def _is_vendored_nested(ctx: FileClassificationContext) -> bool:
    return _in_parts(ctx, _VENDORED_NESTED)


def _has_generated_marker(ctx: FileClassificationContext) -> bool:
    return any(marker in ctx.path_lower for marker in _GENERATED_MARKERS)


def _is_known_config_name(ctx: FileClassificationContext) -> bool:
    return ctx.name in _CONFIG_NAMES


def _matches_config_filename_pattern(ctx: FileClassificationContext) -> bool:
    return ctx.file_ext in _INFRA_CONFIG_EXTS and _matches_any_pattern(ctx.name, _CONFIG_FILE_PATTERNS)


def _is_ci_name(ctx: FileClassificationContext) -> bool:
    return ctx.name in _CI_NAMES


def _is_docker_compose_variant(ctx: FileClassificationContext) -> bool:
    return ctx.name.startswith("docker-compose")


def _is_deploy_dir(ctx: FileClassificationContext) -> bool:
    return _in_parts(ctx, _DEPLOY_DIRS)


def _is_github_workflow(ctx: FileClassificationContext) -> bool:
    return ".github/workflows" in ctx.path_lower or ".github\\workflows" in ctx.path_lower


def _is_tooling_script(ctx: FileClassificationContext) -> bool:
    return any(ctx.path_lower.startswith(prefix) for prefix in _TOOLING_PREFIXES)


def _is_minified_asset(ctx: FileClassificationContext) -> bool:
    return ".min." in ctx.name


def _is_known_vendored_lib(ctx: FileClassificationContext) -> bool:
    return ctx.stem in _KNOWN_VENDORED_LIBS


def _is_known_vendored_static_path(ctx: FileClassificationContext) -> bool:
    return "static" in ctx.parts_lower and any(part in _KNOWN_VENDORED_LIBS for part in ctx.parts_lower)


def _has_config_like_content(ctx: FileClassificationContext) -> bool:
    return bool(
        ctx.source
        and ctx.file_ext in _CONTENT_CHECK_EXTS
        and _CONFIG_CONTENT_RE.search(ctx.source)
    )


_CLASSIFY_FILE_RULES = (
    FileClassificationRule(_has_test_dir, FileClassification("test", 0.95, "directory name indicates test code")),
    FileClassificationRule(_has_test_filename, FileClassification("test", 0.95, "filename indicates test code")),
    FileClassificationRule(_has_migration_marker, FileClassification("migration", 0.9, "path contains migration directory")),
    FileClassificationRule(_is_vendored_root, FileClassification("vendored", 0.95, "path starts in a vendored/third-party root")),
    FileClassificationRule(_is_vendored_nested, FileClassification("vendored", 0.95, "path indicates vendored/third-party code")),
    FileClassificationRule(_has_generated_marker, FileClassification("generated", 0.8, "path or name suggests generated code")),
    FileClassificationRule(_is_known_config_name, FileClassification("config", 0.9, "filename is a known configuration file")),
    FileClassificationRule(_matches_config_filename_pattern, FileClassification("config", 0.85, "filename matches configuration pattern")),
    FileClassificationRule(_is_ci_name, FileClassification("config", 0.9, "filename is a CI/build pipeline file")),
    FileClassificationRule(_is_docker_compose_variant, FileClassification("config", 0.9, "docker-compose variant file")),
    FileClassificationRule(_is_deploy_dir, FileClassification("config", 0.85, "path is in a deploy/infrastructure directory")),
    FileClassificationRule(_is_github_workflow, FileClassification("config", 0.9, "GitHub Actions workflow file")),
    FileClassificationRule(_is_tooling_script, FileClassification("config", 0.85, "path is in a tooling/build scripts directory")),
    FileClassificationRule(_is_minified_asset, FileClassification("generated", 0.85, "minified asset (contains .min. in filename)")),
    FileClassificationRule(_is_known_vendored_lib, FileClassification("vendored", 0.85, "well-known third-party library")),
    FileClassificationRule(_is_known_vendored_static_path, FileClassification("vendored", 0.8, "static directory contains known third-party library path")),
    FileClassificationRule(_has_config_like_content, FileClassification("config", 0.75, "file content contains configuration/secret patterns")),
)


def classify_file(file_path: str, source: str | None = None) -> dict[str, Any]:
    path = Path(file_path)
    ctx = FileClassificationContext(
        file_path=file_path,
        source=source,
        path=path,
        parts=path.parts,
        parts_lower=tuple(part.lower() for part in path.parts),
        name=path.name.lower(),
        path_lower=file_path.lower(),
        file_ext=path.suffix.lower(),
        stem=path.name.lower().split(".")[0],
    )

    for rule in _CLASSIFY_FILE_RULES:
        if rule.predicate(ctx):
            result = rule.result
            if result.reason == "well-known third-party library":
                return {
                    "type": result.file_type,
                    "confidence": result.confidence,
                    "reason": f"{result.reason}: {ctx.stem}",
                }
            return _make_classification_result(result)

    return {
        "type": "production",
        "confidence": 0.7,
        "reason": "no test/migration/vendor/config indicators found",
    }
