"""
Configuration file analysis utilities for MCP tools.

Provides AST-based analysis of YAML, Dockerfile, HCL/Terraform, TOML, and JSON
config files — used by the AI triage agent to assess misconfiguration findings.

All parsing uses tree-sitter grammars (no regex fallback for structure extraction).
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .ts_utils import (
    create_parser,
    detect_language,
    line_range,
    node_text,
)

# ── Shared constants ─────────────────────────────────────────────

_CONFIG_EXTS = frozenset({
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars", ".hcl",
    ".env", ".ini", ".cfg", ".conf", ".properties",
    ".sh", ".bash",
})

_SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg", "node_modules", "__pycache__",
    "vendor", "third_party", ".tox", ".mypy_cache",
})

# Extensions considered "config" for the cross-reference relationship check.
# Scripts (.sh, .bash) and source code are excluded to avoid false positives
# from plain-text mentions of config filenames.
_CONFIG_CROSS_REF_EXTS = frozenset({
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars", ".hcl",
    ".env", ".ini", ".cfg", ".conf", ".properties",
})

_SECRET_PATTERNS = re.compile(
    r"(?i)(?:secret|password|passwd|token|api_?key|private_?key|credential|auth)",
)


def _iter_config_files(source_dir: Path):
    """Yield relative paths for config files (including Dockerfile)."""
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            name_lower = fname.lower()
            if (fpath.suffix.lower() in _CONFIG_EXTS
                    or name_lower.startswith(("dockerfile", "docker-compose", ".env"))
                    or name_lower.endswith(".env")):
                yield fpath.relative_to(source_dir)


def _try_parse_config(source: str, filepath: Path):
    """Parse with tree-sitter if a grammar is available."""
    try:
        lang, lang_key = detect_language(filepath)
    except ValueError:
        return None, None, None
    parser = create_parser(lang)
    src_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(src_bytes)
    return tree, lang_key, src_bytes


# ── 1. extract_config_block ──────────────────────────────────────


def extract_config_block(
    source: str, filepath: Path, line_number: int,
) -> dict[str, Any]:
    """
    Extract the logical config block containing *line_number*.

    Works via tree-sitter for YAML, Dockerfile, HCL, TOML, JSON.
    Returns ``{block_text, block_type, key_path, start_line, end_line}``.
    """
    tree, lang_key, src_bytes = _try_parse_config(source, filepath)
    if not tree or not src_bytes:
        return _extract_block_text_fallback(source, line_number)

    target = _find_deepest_node_at_line(tree.root_node, line_number)
    if not target:
        return _extract_block_text_fallback(source, line_number)

    # Walk up to find a meaningful block boundary
    block = _find_block_ancestor(target, lang_key)
    s, e = line_range(block)
    block_text = node_text(block, src_bytes)
    key_path = _build_key_path(block, lang_key, src_bytes)

    return {
        "block_text": block_text,
        "block_type": block.type,
        "key_path": key_path,
        "start_line": s + 1,
        "end_line": e + 1,
        "language": lang_key,
    }


def _find_deepest_node_at_line(node, line_number: int):
    """Find the deepest AST node that contains *line_number* (1-based)."""
    s = node.start_point[0] + 1
    e = node.end_point[0] + 1
    if not (s <= line_number <= e):
        return None
    for ch in node.children:
        hit = _find_deepest_node_at_line(ch, line_number)
        if hit:
            return hit
    return node


# Node types that represent meaningful "blocks" per config language.
_BLOCK_TYPES: dict[str, set[str]] = {
    "yaml": {
        "block_mapping_pair", "block_mapping", "block_sequence",
        "flow_mapping", "document",
    },
    "dockerfile": {
        "run_instruction", "copy_instruction", "add_instruction",
        "env_instruction", "expose_instruction", "from_instruction",
        "cmd_instruction", "entrypoint_instruction", "arg_instruction",
        "label_instruction", "volume_instruction", "user_instruction",
        "workdir_instruction", "healthcheck_instruction",
    },
    "hcl": {
        "block", "attribute", "object",
    },
    "toml": {
        "table", "pair", "array",
    },
    "json": {
        "pair", "object", "array",
    },
    "bash": {
        "command", "if_statement", "for_statement", "function_definition",
        "pipeline", "variable_assignment",
    },
}


def _find_block_ancestor(node, lang_key: str):
    """Walk up the AST to find the nearest meaningful block node."""
    types = _BLOCK_TYPES.get(lang_key, set())
    current = node
    while current.parent:
        if current.type in types:
            return current
        current = current.parent
    return node  # fallback: return the node itself


def _build_key_path(node, lang_key: str, src_bytes: bytes) -> str:
    """Build a dotted key path from root to *node* for YAML/TOML/JSON/HCL."""
    parts: list[str] = []
    current = node
    while current.parent:
        key = _extract_key_from_node(current, lang_key, src_bytes)
        if key:
            parts.append(key)
        current = current.parent
    parts.reverse()
    return ".".join(parts)


def _extract_key_from_node(node, lang_key: str, src_bytes: bytes) -> str:
    """Extract the key name from a mapping pair / attribute / etc."""
    if lang_key == "yaml" and node.type == "block_mapping_pair":
        for ch in node.children:
            if ch.type == "flow_node" or ch.type.endswith("_scalar"):
                return node_text(ch, src_bytes).strip().strip('"').strip("'")
    if lang_key in {"toml", "json"} and node.type == "pair":
        for ch in node.children:
            if ch.type in {"bare_key", "string", "property_identifier"}:
                return node_text(ch, src_bytes).strip().strip('"').strip("'")
    if lang_key == "hcl" and node.type in {"block", "attribute"}:
        for ch in node.children:
            if ch.type in {"identifier", "string_lit"}:
                return node_text(ch, src_bytes).strip().strip('"')
    if lang_key == "dockerfile":
        return node.type.replace("_instruction", "").upper()
    return ""


def _extract_block_text_fallback(
    source: str, line_number: int,
) -> dict[str, Any]:
    """Fallback: extract lines at the same or deeper indentation level."""
    lines = source.splitlines()
    if line_number < 1 or line_number > len(lines):
        return {"block_text": "", "block_type": "unknown", "key_path": "",
                "start_line": line_number, "end_line": line_number}

    idx = line_number - 1
    target_indent = len(lines[idx]) - len(lines[idx].lstrip())

    # Expand upward to find block start
    start = idx
    while start > 0:
        prev = lines[start - 1]
        if not prev.strip() or prev.strip().startswith("#"):
            start -= 1
            continue
        prev_indent = len(prev) - len(prev.lstrip())
        if prev_indent < target_indent:
            break
        start -= 1

    # Expand downward
    end = idx
    while end < len(lines) - 1:
        nxt = lines[end + 1]
        if not nxt.strip() or nxt.strip().startswith("#"):
            end += 1
            continue
        nxt_indent = len(nxt) - len(nxt.lstrip())
        if nxt_indent < target_indent:
            break
        end += 1

    block_text = "\n".join(lines[start:end + 1])
    return {
        "block_text": block_text,
        "block_type": "indented_block",
        "key_path": "",
        "start_line": start + 1,
        "end_line": end + 1,
    }


# ── 2. classify_environment ──────────────────────────────────────

_ENV_PATTERNS: list[tuple[str, str, str]] = [
    # (glob_pattern, environment, reason)
    # Templates first (most specific)
    (".env.example", "template", "example env file (not deployed)"),
    (".env.sample", "template", "sample env file (not deployed)"),
    (".env.template", "template", "template env file (not deployed)"),
    # Dev patterns (with and without trailing extension)
    ("*.dev", "dev", "filename ends with .dev"),
    ("*.dev.*", "dev", "filename contains .dev."),
    ("*.development", "dev", "filename ends with .development"),
    ("*.development.*", "dev", "filename contains .development."),
    ("*-dev", "dev", "filename ends with -dev"),
    ("*-dev.*", "dev", "filename contains -dev."),
    ("*.local", "dev", "filename ends with .local"),
    ("*.local.*", "dev", "filename contains .local. (local override)"),
    ("docker-compose.override.*", "dev", "docker-compose override (local dev)"),
    # Staging
    ("*.staging", "staging", "filename ends with .staging"),
    ("*.staging.*", "staging", "filename contains .staging."),
    ("*.stg", "staging", "filename ends with .stg"),
    ("*.stg.*", "staging", "filename contains .stg."),
    ("*-staging", "staging", "filename ends with -staging"),
    ("*-staging.*", "staging", "filename contains -staging."),
    # Production
    ("*.prod", "production", "filename ends with .prod"),
    ("*.prod.*", "production", "filename contains .prod."),
    ("*.production", "production", "filename ends with .production"),
    ("*.production.*", "production", "filename contains .production."),
    ("*-prod", "production", "filename ends with -prod"),
    ("*-prod.*", "production", "filename contains -prod."),
    # Test / CI
    ("*.test", "test", "filename ends with .test"),
    ("*.test.*", "test", "filename contains .test."),
    ("*-test", "test", "filename ends with -test"),
    ("*-test.*", "test", "filename contains -test."),
    ("*.ci", "ci", "filename ends with .ci"),
    ("*.ci.*", "ci", "filename contains .ci."),
]


def classify_environment(file_path: str) -> dict[str, Any]:
    """
    Determine the target environment from file path heuristics.

    Returns ``{environment, confidence, reason}`` where *environment* is one of
    ``"dev"``, ``"staging"``, ``"production"``, ``"test"``, ``"ci"``,
    ``"template"``, or ``"unknown"``.
    """
    name = Path(file_path).name.lower()

    for pattern, env, reason in _ENV_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return {"environment": env, "confidence": 0.9, "reason": reason}

    # Check directory names
    parts_lower = [p.lower() for p in Path(file_path).parts]
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

    return {"environment": "unknown", "confidence": 0.5,
            "reason": "no environment indicators found — may be shared or production"}


# ── 3. find_config_overrides ─────────────────────────────────────


def find_config_overrides(
    source_dir: Path, file_path: str, key_or_variable: str,
) -> list[dict[str, Any]]:
    """
    Search the project for the same config key/variable in other files.

    Returns a list of ``{file, line, value, environment}`` dicts — one per
    file where *key_or_variable* appears (first match per file).
    """
    results: list[dict[str, Any]] = []
    origin = Path(file_path)
    key_re = re.compile(r"\b" + re.escape(key_or_variable) + r"\b")

    for rel in _iter_config_files(source_dir):
        if rel == origin:
            continue
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if key_re.search(line):
                env_info = classify_environment(str(rel))
                results.append({
                    "file": str(rel),
                    "line": i + 1,
                    "value": line.strip(),
                    "environment": env_info["environment"],
                })
                break  # one match per file is enough
        if len(results) >= 30:
            break
    return results


# ── 4. extract_env_variables ─────────────────────────────────────


def extract_env_variables(
    source: str, filepath: Path,
) -> list[dict[str, Any]]:
    """
    Extract environment variable definitions from a config file.

    Returns a list of ``{name, value, source, line, has_secret_pattern}``
    dicts.  *source* indicates where the variable was found (e.g. ``"ENV"``,
    ``"ARG"``, ``"yaml_environment"``, ``"dotenv"``).
    """
    tree, lang_key, src_bytes = _try_parse_config(source, filepath)

    if lang_key == "dockerfile" and tree and src_bytes:
        return _env_from_dockerfile_ast(tree.root_node, src_bytes)
    if lang_key == "yaml" and tree and src_bytes:
        return _env_from_yaml_ast(tree.root_node, src_bytes, source)
    if lang_key == "bash" and tree and src_bytes:
        return _env_from_bash_ast(tree.root_node, src_bytes)

    # Dockerfile without AST grammar — regex fallback
    name_lower = filepath.name.lower()
    if name_lower.startswith("dockerfile"):
        return _env_from_dockerfile_regex(source)

    # .env files and other formats — line-based parsing
    if name_lower.startswith(".env") or name_lower.endswith(".env"):
        return _env_from_dotenv(source)

    # Generic: try dotenv-style parsing for unknown formats
    return _env_from_dotenv(source)


def _env_from_dockerfile_ast(root, src_bytes: bytes) -> list[dict[str, Any]]:
    """Extract ENV and ARG instructions from Dockerfile AST."""
    results: list[dict[str, Any]] = []
    for child in root.children:
        if child.type == "env_instruction":
            pairs = _extract_dockerfile_pairs(child, src_bytes)
            for name, value in pairs:
                results.append({
                    "name": name,
                    "value": value,
                    "source": "ENV",
                    "line": child.start_point[0] + 1,
                    "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                })
        elif child.type == "arg_instruction":
            pairs = _extract_dockerfile_pairs(child, src_bytes)
            for name, value in pairs:
                results.append({
                    "name": name,
                    "value": value,
                    "source": "ARG",
                    "line": child.start_point[0] + 1,
                    "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                })
    return results


_DOCKERFILE_ENV_RE = re.compile(
    r"^\s*(?:ENV|ARG)\s+(.+)",
    re.MULTILINE,
)


def _env_from_dockerfile_regex(source: str) -> list[dict[str, Any]]:
    """Fallback: extract ENV/ARG from Dockerfile via regex (when AST is unavailable)."""
    results: list[dict[str, Any]] = []
    for i, line in enumerate(source.splitlines()):
        m = _DOCKERFILE_ENV_RE.match(line)
        if not m:
            continue
        instruction = "ENV" if line.strip().startswith("ENV") else "ARG"
        body = m.group(1)
        if "=" in body:
            for segment in _split_env_pairs(body):
                if "=" in segment:
                    k, _, v = segment.partition("=")
                    name = k.strip()
                    value = v.strip().strip('"').strip("'")
                    results.append({
                        "name": name,
                        "value": value,
                        "source": instruction,
                        "line": i + 1,
                        "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                    })
        else:
            # ARG NAME (no default)
            results.append({
                "name": body.strip(),
                "value": "",
                "source": instruction,
                "line": i + 1,
                "has_secret_pattern": bool(_SECRET_PATTERNS.search(body.strip())),
            })
    return results


def _extract_dockerfile_pairs(
    node, src_bytes: bytes,
) -> list[tuple[str, str]]:
    """Extract NAME=VALUE pairs from a Dockerfile ENV/ARG node."""
    text = node_text(node, src_bytes)
    # Remove the instruction keyword (ENV / ARG)
    parts = text.split(None, 1)
    if len(parts) < 2:
        return []
    body = parts[1]
    pairs: list[tuple[str, str]] = []
    if "=" in body:
        for segment in _split_env_pairs(body):
            if "=" in segment:
                k, _, v = segment.partition("=")
                pairs.append((k.strip(), v.strip().strip('"').strip("'")))
    else:
        # ARG NAME (no default)
        pairs.append((body.strip(), ""))
    return pairs


def _split_env_pairs(text: str) -> list[str]:
    """Split 'A=1 B=2' respecting quotes."""
    result: list[str] = []
    current: list[str] = []
    in_quote = ""
    for ch in text:
        if ch in {'"', "'"} and not in_quote:
            in_quote = ch
            current.append(ch)
        elif ch == in_quote:
            in_quote = ""
            current.append(ch)
        elif ch == " " and not in_quote and current:
            token = "".join(current).strip()
            if token:
                result.append(token)
            current = []
        else:
            current.append(ch)
    if current:
        token = "".join(current).strip()
        if token:
            result.append(token)
    return result


def _env_from_yaml_ast(
    root, src_bytes: bytes, source: str,
) -> list[dict[str, Any]]:
    """Extract environment variables from docker-compose YAML via AST."""
    results: list[dict[str, Any]] = []
    _walk_yaml_for_env(root, src_bytes, results)
    return results


def _walk_yaml_for_env(node, src_bytes: bytes, results: list):
    """Recursively walk YAML AST looking for 'environment:' blocks."""
    if node.type == "block_mapping_pair":
        key_node = None
        value_node = None
        for ch in node.children:
            if ch.type == "flow_node" or ch.type.endswith("_scalar"):
                if key_node is None:
                    key_node = ch
            elif ch.type in {"block_node", "flow_node", "block_mapping",
                             "block_sequence", "flow_sequence"}:
                value_node = ch
        if key_node:
            key_text = node_text(key_node, src_bytes).strip()
            if key_text == "environment" and value_node:
                _collect_yaml_env_pairs(value_node, src_bytes, results)
                return
    for ch in node.children:
        _walk_yaml_for_env(ch, src_bytes, results)


def _collect_yaml_env_pairs(node, src_bytes: bytes, results: list):
    """Collect env vars from a YAML 'environment:' value node."""
    for ch in node.children:
        if ch.type == "block_mapping_pair":
            text = node_text(ch, src_bytes).strip()
            if ":" in text:
                k, _, v = text.partition(":")
                name = k.strip()
                value = v.strip().strip('"').strip("'")
                results.append({
                    "name": name,
                    "value": value,
                    "source": "yaml_environment",
                    "line": ch.start_point[0] + 1,
                    "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                })
        elif ch.type in {"flow_node", "block_scalar"}:
            text = node_text(ch, src_bytes).strip().strip("- ")
            if "=" in text:
                k, _, v = text.partition("=")
                name = k.strip()
                value = v.strip().strip('"').strip("'")
                results.append({
                    "name": name,
                    "value": value,
                    "source": "yaml_environment",
                    "line": ch.start_point[0] + 1,
                    "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                })
        _collect_yaml_env_pairs(ch, src_bytes, results)


def _env_from_bash_ast(root, src_bytes: bytes) -> list[dict[str, Any]]:
    """Extract export/variable assignments from bash scripts."""
    results: list[dict[str, Any]] = []
    for child in root.children:
        if child.type == "variable_assignment":
            text = node_text(child, src_bytes)
            if "=" in text:
                k, _, v = text.partition("=")
                name = k.strip().lstrip("export").strip()
                value = v.strip().strip('"').strip("'")
                results.append({
                    "name": name,
                    "value": value,
                    "source": "bash_assignment",
                    "line": child.start_point[0] + 1,
                    "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
                })
        # `export VAR=value` is a declaration_command in tree-sitter-bash.
        # Older grammars may produce a plain `command` node — handle both.
        elif child.type in {"declaration_command", "command"}:
            cmd_text = node_text(child, src_bytes).strip()
            if cmd_text.startswith("export "):
                # Walk direct children looking for variable_assignment nodes
                for sub in child.children:
                    if sub.type == "variable_assignment":
                        sub_text = node_text(sub, src_bytes)
                        if "=" in sub_text:
                            k, _, v = sub_text.partition("=")
                            results.append({
                                "name": k.strip(),
                                "value": v.strip().strip('"').strip("'"),
                                "source": "bash_export",
                                "line": child.start_point[0] + 1,
                                "has_secret_pattern": bool(_SECRET_PATTERNS.search(k.strip())),
                            })
    return results


_DOTENV_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)",
)


def _env_from_dotenv(source: str) -> list[dict[str, Any]]:
    """Parse .env-style files (KEY=VALUE lines)."""
    results: list[dict[str, Any]] = []
    for i, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _DOTENV_RE.match(stripped)
        if m:
            name = m.group(1)
            value = m.group(2).strip().strip('"').strip("'")
            results.append({
                "name": name,
                "value": value,
                "source": "dotenv",
                "line": i + 1,
                "has_secret_pattern": bool(_SECRET_PATTERNS.search(name)),
            })
    return results


# ── 5. find_related_configs ──────────────────────────────────────


def find_related_configs(
    source_dir: Path, file_path: str,
) -> list[dict[str, Any]]:
    """
    Find config files related to *file_path*.

    Returns a list of ``{file, relationship}`` dicts.  *relationship* describes
    the connection (e.g. ``"compose_variant"``, ``"env_file"``,
    ``"terraform_module_peer"``, ``"k8s_peer_resource"``).
    """
    results: list[dict[str, Any]] = []
    origin = Path(file_path)
    origin_name = origin.name.lower()

    for rel in _iter_config_files(source_dir):
        if rel == origin:
            continue
        rel_name = rel.name.lower()
        relationship = _detect_relationship(origin_name, rel_name, source_dir,
                                            origin, rel)
        if relationship:
            results.append({
                "file": str(rel),
                "relationship": relationship,
            })
        if len(results) >= 30:
            break
    return results


def _detect_relationship(
    origin_name: str, rel_name: str,
    source_dir: Path, origin: Path, rel: Path,
) -> str | None:
    """Detect the relationship between two config files."""
    # Dockerfile ↔ docker-compose
    if origin_name.startswith("dockerfile") and rel_name.startswith("docker-compose"):
        return "referenced_by_compose"
    if origin_name.startswith("docker-compose") and rel_name.startswith("dockerfile"):
        return "builds_dockerfile"

    # docker-compose variants (override, dev, prod)
    if (origin_name.startswith("docker-compose")
            and rel_name.startswith("docker-compose")):
        return "compose_variant"

    # .env family
    if origin_name.startswith(".env") and rel_name.startswith(".env"):
        return "env_variant"
    if origin_name.startswith("docker-compose") and rel_name.startswith(".env"):
        return "env_file"

    # Same directory, related config types
    if origin.parent == rel.parent:
        # Terraform: main.tf ↔ variables.tf ↔ terraform.tfvars
        tf_names = {"main.tf", "variables.tf", "outputs.tf", "providers.tf",
                     "terraform.tfvars", "backend.tf"}
        if origin_name in tf_names and rel_name in tf_names:
            return "terraform_module_peer"

        # K8s: deployment ↔ service ↔ configmap ↔ ingress in same dir
        k8s_markers = {"deployment", "service", "configmap", "ingress",
                       "secret", "statefulset", "daemonset", "cronjob",
                       "namespace", "pvc", "hpa"}
        if any(m in origin_name for m in k8s_markers):
            if any(m in rel_name for m in k8s_markers):
                return "k8s_peer_resource"

        # Helm: values.yaml ↔ templates/ files
        if "values" in origin_name and "templates" in str(rel):
            return "helm_values_for_template"
        if "templates" in str(origin) and "values" in rel_name:
            return "helm_template_uses_values"

    # Cross-reference check — only between config files (not scripts/source code)
    # to avoid false positives from plain-text mentions of filenames.
    rel_ext = rel.suffix.lower()
    rel_is_config = (
        rel_ext in _CONFIG_CROSS_REF_EXTS
        or rel_name.startswith(("dockerfile", "docker-compose", ".env"))
    )
    if rel_is_config:
        try:
            text = (source_dir / rel).read_text(encoding="utf-8", errors="replace")
            if origin.name in text:
                return "references_origin"
        except OSError:
            pass

    return None
