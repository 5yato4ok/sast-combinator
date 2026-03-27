from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..config import SKIP_DIRS


_CONFIG_EXTS = frozenset({
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars", ".hcl",
    ".env", ".ini", ".cfg", ".conf", ".properties",
    ".sh", ".bash",
})
_CONFIG_CROSS_REF_EXTS = frozenset({
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars", ".hcl",
    ".env", ".ini", ".cfg", ".conf", ".properties",
})
_ENV_PATTERNS: list[tuple[str, str, str]] = [
    (".env.example", "template", "example env file (not deployed)"),
    (".env.sample", "template", "sample env file (not deployed)"),
    (".env.template", "template", "template env file (not deployed)"),
    ("*.dev", "dev", "filename ends with .dev"),
    ("*.dev.*", "dev", "filename contains .dev."),
    ("*.development", "dev", "filename ends with .development"),
    ("*.development.*", "dev", "filename contains .development."),
    ("*-dev", "dev", "filename ends with -dev"),
    ("*-dev.*", "dev", "filename contains -dev."),
    ("*.local", "dev", "filename ends with .local"),
    ("*.local.*", "dev", "filename contains .local. (local override)"),
    ("docker-compose.override.*", "dev", "docker-compose override (local dev)"),
    ("*.staging", "staging", "filename ends with .staging"),
    ("*.staging.*", "staging", "filename contains .staging."),
    ("*.stg", "staging", "filename ends with .stg"),
    ("*.stg.*", "staging", "filename contains .stg."),
    ("*-staging", "staging", "filename ends with -staging"),
    ("*-staging.*", "staging", "filename contains -staging."),
    ("*.prod", "production", "filename ends with .prod"),
    ("*.prod.*", "production", "filename contains .prod."),
    ("*.production", "production", "filename ends with .production"),
    ("*.production.*", "production", "filename contains .production."),
    ("*-prod", "production", "filename ends with -prod"),
    ("*-prod.*", "production", "filename contains -prod."),
    ("*.test", "test", "filename ends with .test"),
    ("*.test.*", "test", "filename contains .test."),
    ("*-test", "test", "filename ends with -test"),
    ("*-test.*", "test", "filename contains -test."),
    ("*.ci", "ci", "filename ends with .ci"),
    ("*.ci.*", "ci", "filename contains .ci."),
    ("*.jenkins.*", "ci", "filename contains .jenkins."),
]
RelationshipPredicate = Callable[[Path, Path, Path], bool]


def _iter_config_files(source_dir: Path):
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            name_lower = fname.lower()
            if (
                fpath.suffix.lower() in _CONFIG_EXTS
                or name_lower.startswith(("dockerfile", "docker-compose", ".env"))
                or name_lower.endswith(".env")
            ):
                yield fpath.relative_to(source_dir)


def classify_environment(file_path: str) -> dict[str, Any]:
    name = Path(file_path).name.lower()
    for pattern, env, reason in _ENV_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return {"environment": env, "confidence": 0.9, "reason": reason}

    parts_lower = [part.lower() for part in Path(file_path).parts]
    dir_env_map = {
        "dev": "dev", "development": "dev",
        "staging": "staging", "stg": "staging",
        "prod": "production", "production": "production",
        "test": "test", "tests": "test", "ci": "ci",
    }
    for part in parts_lower:
        if part in dir_env_map:
            return {
                "environment": dir_env_map[part],
                "confidence": 0.8,
                "reason": f"directory '{part}' indicates environment",
            }

    return {
        "environment": "unknown",
        "confidence": 0.5,
        "reason": "no environment indicators found — may be shared or production",
    }


def find_config_overrides(
    source_dir: Path, file_path: str, key_or_variable: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    origin = Path(file_path)
    for rel in _iter_config_files(source_dir):
        if rel == origin:
            continue
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines()):
            if _key_regex(key_or_variable).search(line):
                env_info = classify_environment(str(rel))
                results.append({
                    "file": str(rel),
                    "line": i + 1,
                    "value": line.strip(),
                    "environment": env_info["environment"],
                })
                break
        if len(results) >= 30:
            break
    return results


def _key_regex(key_or_variable: str):
    import re
    return re.compile(r"\b" + re.escape(key_or_variable) + r"\b")


@dataclass(frozen=True)
class RelationshipRule:
    relationship: str
    predicate: RelationshipPredicate


def _same_dir(origin: Path, rel: Path, _source_dir: Path) -> bool:
    return origin.parent == rel.parent


def _is_parent_or_child(a: Path, b: Path) -> bool:
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


def _file_references_path(source_dir: Path, rel: Path, origin: Path) -> bool:
    try:
        text = (source_dir / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    origin_name = origin.name
    if str(origin) in text:
        return True
    try:
        rel_path = os.path.relpath(origin, rel.parent)
        if rel_path in text:
            return True
    except ValueError:
        pass
    if origin_name in text:
        if origin.parent == rel.parent or _is_parent_or_child(origin.parent, rel.parent):
            return True
    return False


def _dockerfile_compose_linked(origin: Path, rel: Path, source_dir: Path) -> bool:
    return (
        origin.name.lower().startswith("dockerfile")
        and rel.name.lower().startswith("docker-compose")
        and (_same_dir(origin, rel, source_dir) or _file_references_path(source_dir, rel, origin))
    )


def _compose_dockerfile_linked(origin: Path, rel: Path, source_dir: Path) -> bool:
    return (
        origin.name.lower().startswith("docker-compose")
        and rel.name.lower().startswith("dockerfile")
        and (_same_dir(origin, rel, source_dir) or _file_references_path(source_dir, rel, origin))
    )


def _compose_variant(origin: Path, rel: Path, source_dir: Path) -> bool:
    return (
        origin.name.lower().startswith("docker-compose")
        and rel.name.lower().startswith("docker-compose")
        and _same_dir(origin, rel, source_dir)
    )


def _env_variant(origin: Path, rel: Path, _source_dir: Path) -> bool:
    return origin.name.lower().startswith(".env") and rel.name.lower().startswith(".env")


def _compose_env_file(origin: Path, rel: Path, _source_dir: Path) -> bool:
    return origin.name.lower().startswith("docker-compose") and rel.name.lower().startswith(".env")


def _terraform_module_peer(origin: Path, rel: Path, source_dir: Path) -> bool:
    tf_names = {"main.tf", "variables.tf", "outputs.tf", "providers.tf", "terraform.tfvars", "backend.tf"}
    return _same_dir(origin, rel, source_dir) and origin.name.lower() in tf_names and rel.name.lower() in tf_names


def _k8s_peer_resource(origin: Path, rel: Path, source_dir: Path) -> bool:
    markers = {"deployment", "service", "configmap", "ingress", "secret", "statefulset", "daemonset", "cronjob", "namespace", "pvc", "hpa"}
    origin_name = origin.name.lower()
    rel_name = rel.name.lower()
    return _same_dir(origin, rel, source_dir) and any(m in origin_name for m in markers) and any(m in rel_name for m in markers)


def _helm_values_for_template(origin: Path, rel: Path, source_dir: Path) -> bool:
    return _same_dir(origin, rel, source_dir) and "values" in origin.name.lower() and "templates" in str(rel)


def _helm_template_uses_values(origin: Path, rel: Path, source_dir: Path) -> bool:
    return _same_dir(origin, rel, source_dir) and "templates" in str(origin) and "values" in rel.name.lower()


def _config_reference(origin: Path, rel: Path, source_dir: Path) -> bool:
    rel_name = rel.name.lower()
    rel_ext = rel.suffix.lower()
    rel_is_config = rel_ext in _CONFIG_CROSS_REF_EXTS or rel_name.startswith(("dockerfile", "docker-compose", ".env"))
    return rel_is_config and _file_references_path(source_dir, rel, origin)


_RELATIONSHIP_RULES = (
    RelationshipRule("referenced_by_compose", _dockerfile_compose_linked),
    RelationshipRule("builds_dockerfile", _compose_dockerfile_linked),
    RelationshipRule("compose_variant", _compose_variant),
    RelationshipRule("env_variant", _env_variant),
    RelationshipRule("env_file", _compose_env_file),
    RelationshipRule("terraform_module_peer", _terraform_module_peer),
    RelationshipRule("k8s_peer_resource", _k8s_peer_resource),
    RelationshipRule("helm_values_for_template", _helm_values_for_template),
    RelationshipRule("helm_template_uses_values", _helm_template_uses_values),
    RelationshipRule("references_origin", _config_reference),
)


def find_related_configs(source_dir: Path, file_path: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    origin = Path(file_path)
    for rel in _iter_config_files(source_dir):
        if rel == origin:
            continue
        relationship = _detect_relationship(source_dir, origin, rel)
        if relationship:
            results.append({"file": str(rel), "relationship": relationship})
        if len(results) >= 30:
            break
    results.sort(key=lambda item: (item["relationship"], item["file"]))
    return results


def _detect_relationship(source_dir: Path, origin: Path, rel: Path) -> str | None:
    for rule in _RELATIONSHIP_RULES:
        if rule.predicate(origin, rel, source_dir):
            return rule.relationship
    return None
