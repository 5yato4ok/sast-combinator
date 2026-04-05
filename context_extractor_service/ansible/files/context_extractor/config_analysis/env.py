from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .shared import _parse_config_or_none, _try_parse_config
from ..ts_utils import node_text


EnvEntry = dict[str, Any]
AstExtractor = Callable[[Any, bytes], list[EnvEntry]]
FallbackExtractor = Callable[[str], list[EnvEntry]]

_SECRET_PATTERNS = re.compile(
    r"(?i)(?:secret|password|passwd|token|api_?key|private_?key|credential|auth)",
)
_DOTENV_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)",
)
_PROPERTIES_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*[=:]\s*(.*)",
)
_BASH_EXPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=([^\n]*)",
)

_DOCKERFILE_INSTRUCTION_SOURCES = {
    "env_instruction": "ENV",
    "arg_instruction": "ARG",
}
_YAML_ENV_VALUE_NODE_TYPES = {
    "block_node",
    "block_mapping",
    "block_sequence",
    "flow_node",
    "flow_sequence",
}
_YAML_ENV_INLINE_VALUE_TYPES = {
    "block_scalar",
    "flow_node",
}
_BASH_EXPORT_COMMAND_TYPES = {
    "command",
    "declaration_command",
}
# YAML keys that look like secret patterns but are structural (not actual secrets).
_YAML_STRUCTURAL_ENV_KEYS = frozenset({"environment", "env", "envFrom"})


def _is_yaml_scalar_node(node) -> bool:
    """Return True if *node* is a YAML scalar or flow node."""
    return node.type == "flow_node" or node.type.endswith("_scalar")


def extract_env_variables(source: str, filepath: Path) -> list[EnvEntry]:
    tree, lang_key, src_bytes = _parse_config_or_none(source, filepath)

    ast_extractor = _AST_ENV_EXTRACTORS.get(lang_key)
    if ast_extractor and tree and src_bytes:
        return ast_extractor(tree.root_node, src_bytes)

    fallback_extractor = _select_fallback_extractor(filepath)
    return fallback_extractor(source)


def _select_fallback_extractor(filepath: Path) -> FallbackExtractor:
    name_lower = filepath.name.lower()
    for predicate, extractor in _FALLBACK_ENV_EXTRACTORS:
        if predicate(name_lower):
            return extractor
    return _env_from_dotenv


def _normalize_env_value(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _has_secret_pattern(name: str) -> bool:
    return bool(_SECRET_PATTERNS.search(name))


def _build_env_entry(name: str, value: str, source_name: str, line: int) -> EnvEntry:
    normalized_name = name.strip()
    return {
        "name": normalized_name,
        "value": _normalize_env_value(value),
        "source": source_name,
        "line": line,
        "has_secret_pattern": _has_secret_pattern(normalized_name),
    }


def _split_key_value(text: str, separator: str) -> tuple[str, str] | None:
    if separator not in text:
        return None
    key, _, value = text.partition(separator)
    return key.strip(), value


def _iter_dockerfile_pairs(body: str) -> Iterable[tuple[str, str]]:
    if "=" not in body:
        yield body.strip(), ""
        return
    for segment in _split_env_pairs(body):
        pair = _split_key_value(segment, "=")
        if not pair:
            continue
        name, value = pair
        yield name, value


def _extract_dockerfile_pairs(node, src_bytes: bytes) -> list[tuple[str, str]]:
    text = node_text(node, src_bytes)
    parts = text.split(None, 1)
    if len(parts) < 2:
        return []
    return list(_iter_dockerfile_pairs(parts[1]))


def _collect_run_bash_assignments(root, src_bytes: bytes) -> list[EnvEntry]:
    """Walk a bash AST tree and collect all variable_assignment and export entries.

    Unlike _env_from_bash_ast this recurses into compound constructs (list,
    subshell, pipeline, if_statement, …) so that assignments chained with &&,
    ||, or ; are all captured.  Function definitions are skipped to avoid
    collecting assignments from helper functions that run in a different scope.
    """
    results: list[EnvEntry] = []
    seen_names: set[str] = set()
    stack = list(root.children)
    while stack:
        current = stack.pop()
        if current.type == "function_definition":
            continue  # skip function bodies — different scope
        if current.type == "variable_assignment":
            entry = _extract_bash_assignment_entry(current, src_bytes)
            if entry and entry["name"] not in seen_names:
                results.append(entry)
                seen_names.add(entry["name"])
            continue
        if current.type == "declaration_command":
            # export VAR=val — handled by the dedicated extractor
            for e in _extract_bash_export_entries(current, src_bytes):
                if e["name"] not in seen_names:
                    results.append(e)
                    seen_names.add(e["name"])
            continue
        if current.type == "heredoc_body":
            line_offset = current.start_point[0] + 1
            for i, line in enumerate(node_text(current, src_bytes).splitlines()):
                match = _DOTENV_RE.match(line)
                if match:
                    name, value = match.groups()
                    if name not in seen_names:
                        results.append(_build_env_entry(name, value, "bash_heredoc", line_offset + i))
                        seen_names.add(name)
            continue
        # Pick up command-level env assignments: ``VAR=val command args``
        # These are variable_assignment children of a command node that appear
        # before the command name.
        if current.type == "command":
            for child in current.children:
                if child.type == "variable_assignment":
                    entry = _extract_bash_assignment_entry(child, src_bytes)
                    if entry and entry["name"] not in seen_names:
                        entry["source"] = "run_command_env"
                        results.append(entry)
                        seen_names.add(entry["name"])
                elif child.is_named and child.type != "variable_assignment":
                    break
        stack.extend(current.children)
    return results


def _env_from_run_instruction(node, src_bytes: bytes) -> list[EnvEntry]:
    """Extract env assignments from a Dockerfile RUN instruction shell body.

    Re-parses the shell command using tree-sitter-bash so that quoted values,
    heredocs, and multi-line continuations are handled correctly — avoiding the
    false-positives and missed values that come from regex over raw text.
    """
    run_text = node_text(node, src_bytes)
    # Strip the leading instruction keyword (RUN …) to isolate the shell body
    parts = run_text.split(None, 1)
    if len(parts) < 2:
        return []
    shell_body = parts[1]
    # Parse with tree-sitter-bash (Path("_run.sh") selects the bash grammar)
    tree, lang_key, shell_bytes = _try_parse_config(shell_body, Path("_run.sh"))
    if tree is None or lang_key != "bash":
        return []
    base_line = node.start_point[0] + 1
    entries = _collect_run_bash_assignments(tree.root_node, shell_bytes)
    # Line numbers from the sub-parse are relative to the shell body; reset to
    # the RUN instruction line so callers get a meaningful file-level line number.
    for entry in entries:
        entry["line"] = base_line
    return entries


def _env_from_dockerfile_ast(root, src_bytes: bytes) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    stack = list(root.children)
    while stack:
        child = stack.pop(0)
        # Standard ENV / ARG instructions
        source_name = _DOCKERFILE_INSTRUCTION_SOURCES.get(child.type)
        if source_name:
            for name, value in _extract_dockerfile_pairs(child, src_bytes):
                results.append(
                    _build_env_entry(name, value, source_name, child.start_point[0] + 1),
                )
            continue
        # ONBUILD wraps another instruction — recurse into its child instruction
        if child.type == "onbuild_instruction":
            for sub in child.children:
                sub_source = _DOCKERFILE_INSTRUCTION_SOURCES.get(sub.type)
                if sub_source:
                    for name, value in _extract_dockerfile_pairs(sub, src_bytes):
                        results.append(
                            _build_env_entry(name, value, f"onbuild_{sub_source}", child.start_point[0] + 1),
                        )
        # RUN instructions may contain shell variable assignments (heredoc or plain)
        if child.type in {"run_instruction", "run_instruction_expression"}:
            results.extend(_env_from_run_instruction(child, src_bytes))
    return results


def _split_env_pairs(text: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    in_quote = ""
    for char in text:
        if char in {'"', "'"} and not in_quote:
            in_quote = char
            current.append(char)
        elif char == in_quote:
            in_quote = ""
            current.append(char)
        elif char == " " and not in_quote and current:
            token = "".join(current).strip()
            if token:
                result.append(token)
            current = []
        else:
            current.append(char)
    if current:
        token = "".join(current).strip()
        if token:
            result.append(token)
    return result


def _env_from_yaml_ast(root, src_bytes: bytes) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    _walk_yaml_for_env(root, src_bytes, results)
    return results


def _walk_yaml_for_env(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        # Standard Ansible/Docker Compose `environment:` key
        env_value_node = _find_yaml_environment_value_node(current, src_bytes)
        if env_value_node:
            _collect_yaml_env_pairs(env_value_node, src_bytes, results)
            continue
        # GitHub Actions / Kubernetes `env:` key (different name, same structure)
        gh_env_node = _find_yaml_env_key_value_node(current, src_bytes)
        if gh_env_node:
            _collect_yaml_env_pairs(gh_env_node, src_bytes, results)
            continue
        # Kubernetes container spec: env list with name/value items
        k8s_env_node = _find_yaml_k8s_env_list_node(current, src_bytes)
        if k8s_env_node:
            _collect_yaml_k8s_env_list(k8s_env_node, src_bytes, results)
            continue
        # Secret-pattern keys anywhere in the YAML (Helm values, etc.)
        _maybe_collect_yaml_secret_pair(current, src_bytes, results)
        # Block scalars may contain shell assignments
        _maybe_collect_bash_in_block_scalar(current, src_bytes, results)
        stack.extend(reversed(current.children))


def _find_yaml_environment_value_node(node, src_bytes: bytes):
    if node.type != "block_mapping_pair":
        return None

    key_node = None
    value_node = None
    for child in node.children:
        if key_node is None and _is_yaml_scalar_node(child):
            key_node = child
            continue
        if child.type in _YAML_ENV_VALUE_NODE_TYPES:
            value_node = child

    if not key_node or node_text(key_node, src_bytes).strip() != "environment":
        return None
    return value_node


def _find_yaml_env_key_value_node(node, src_bytes: bytes):
    """Find block_mapping_pair nodes with key 'env' (GitHub Actions / K8s simple env map).

    Excludes sequence values (K8s list format) — those are handled by _find_yaml_k8s_env_list_node.
    """
    if node.type != "block_mapping_pair":
        return None
    key_node = None
    value_node = None
    for child in node.children:
        if key_node is None and _is_yaml_scalar_node(child):
            key_text = node_text(child, src_bytes).strip()
            if key_text == "env":
                key_node = child
            continue
        if child.type in _YAML_ENV_VALUE_NODE_TYPES:
            value_node = child
    if not key_node or not value_node:
        return None
    # Exclude K8s list format (sequence) — handled by _find_yaml_k8s_env_list_node
    if _yaml_node_is_sequence(value_node):
        return None
    return value_node


def _yaml_node_is_sequence(node) -> bool:
    """Return True if the YAML node is or wraps a block_sequence."""
    if node.type == "block_sequence":
        return True
    if node.type == "block_node":
        return any(child.type == "block_sequence" for child in node.children)
    return False


def _find_yaml_k8s_env_list_node(node, src_bytes: bytes):
    """Find the value node of a 'env:' key whose value is a block_sequence (K8s list format)."""
    if node.type != "block_mapping_pair":
        return None
    key_node = None
    value_node = None
    for child in node.children:
        if key_node is None and _is_yaml_scalar_node(child):
            key_text = node_text(child, src_bytes).strip()
            if key_text == "env":
                key_node = child
            continue
        if child.type in {"block_node", "block_sequence"}:
            value_node = child
    if not key_node or not value_node:
        return None
    return value_node


def _collect_yaml_k8s_env_list(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    """Parse K8s env list: [{name: VAR, value: val}, {name: VAR, valueFrom: ...}]."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "block_mapping":
            pairs = {
                _first_scalar_text(child, src_bytes): child
                for child in current.children
                if child.type == "block_mapping_pair"
            }
            name_pair = pairs.get("name")
            value_pair = pairs.get("value")
            value_from_pair = pairs.get("valueFrom")
            if name_pair:
                name_val = _second_scalar_text(name_pair, src_bytes)
                if name_val:
                    source = "k8s_env"
                    if value_from_pair:
                        source = "k8s_secretKeyRef"
                    value = _second_scalar_text(value_pair, src_bytes) if value_pair else ""
                    results.append(
                        _build_env_entry(name_val, value, source, current.start_point[0] + 1),
                    )
        stack.extend(reversed(current.children))


def _first_scalar_text(pair_node, src_bytes: bytes) -> str:
    for child in pair_node.children:
        if _is_yaml_scalar_node(child):
            return node_text(child, src_bytes).strip()
    return ""


def _second_scalar_text(pair_node, src_bytes: bytes) -> str:
    found_first = False
    for child in pair_node.children:
        if _is_yaml_scalar_node(child):
            if found_first:
                return node_text(child, src_bytes).strip().strip('"').strip("'")
            found_first = True
    return ""


def _maybe_collect_yaml_secret_pair(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    """Extract any block_mapping_pair whose key matches a secret pattern.

    Skips entries whose value is a block_scalar (e.g. SSH key PEM content) or
    a block_node wrapping a block_scalar — those are multi-line file contents,
    not simple config values.
    """
    if node.type != "block_mapping_pair":
        return
    key_node = None
    value_text = ""
    for child in node.children:
        if key_node is None and _is_yaml_scalar_node(child):
            key_node = child
            continue
        # block_scalar (or block_node wrapping one) holds raw multi-line content — skip
        if child.type == "block_scalar":
            return
        if child.type == "block_node":
            for sub in child.children:
                if sub.type == "block_scalar":
                    return
        if _is_yaml_scalar_node(child):
            value_text = node_text(child, src_bytes).strip().strip('"').strip("'")
    if key_node is None:
        return
    key_text = node_text(key_node, src_bytes).strip()
    if _has_secret_pattern(key_text) and key_text not in _YAML_STRUCTURAL_ENV_KEYS:
        results.append(_build_env_entry(key_text, value_text, "yaml_key", node.start_point[0] + 1))


def _maybe_collect_bash_in_block_scalar(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    """If a YAML block_scalar value contains shell export statements, extract them."""
    if node.type != "block_scalar":
        return
    scalar_text = node_text(node, src_bytes)
    for match in _BASH_EXPORT_RE.finditer(scalar_text):
        name = match.group(1).strip()
        value = _normalize_env_value(match.group(2))
        results.append(_build_env_entry(name, value, "yaml_block_scalar_export", node.start_point[0] + 1))


def _collect_yaml_env_pairs(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    stack = [node]
    while stack:
        current = stack.pop()
        entry = _extract_yaml_env_entry(current, src_bytes)
        if entry:
            results.append(entry)
        stack.extend(reversed(current.children))


def _extract_yaml_env_entry(node, src_bytes: bytes) -> EnvEntry | None:
    if node.type == "block_mapping_pair":
        text = node_text(node, src_bytes).strip()
        pair = _split_key_value(text, ":")
        if not pair:
            return None
        name, value = pair
        return _build_env_entry(
            name,
            value,
            "yaml_environment",
            node.start_point[0] + 1,
        )

    if node.type not in _YAML_ENV_INLINE_VALUE_TYPES:
        return None

    text = node_text(node, src_bytes).strip().strip("- ")
    pair = _split_key_value(text, "=")
    if not pair:
        return None
    name, value = pair
    return _build_env_entry(
        name,
        value,
        "yaml_environment",
        node.start_point[0] + 1,
    )


def _env_from_bash_ast(root, src_bytes: bytes) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    for child in root.children:
        assignment = _extract_bash_assignment_entry(child, src_bytes)
        if assignment:
            results.append(assignment)
            continue

        if child.type in _BASH_EXPORT_COMMAND_TYPES:
            results.extend(_extract_bash_export_entries(child, src_bytes))
            continue

        # Scan for heredoc bodies nested anywhere in the subtree (e.g. cat <<EOF ... EOF)
        _collect_heredoc_env_entries(child, src_bytes, results)
    return results


def _collect_heredoc_env_entries(node, src_bytes: bytes, results: list[EnvEntry]) -> None:
    """Recursively find heredoc_body nodes and parse their content as KEY=VALUE pairs."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "heredoc_body":
            text = node_text(current, src_bytes)
            line_offset = current.start_point[0] + 1
            for i, line in enumerate(text.splitlines()):
                match = _DOTENV_RE.match(line)
                if match:
                    name, value = match.groups()
                    results.append(_build_env_entry(name, value, "bash_heredoc", line_offset + i))
        else:
            stack.extend(current.children)


def _extract_bash_assignment_entry(node, src_bytes: bytes) -> EnvEntry | None:
    if node.type != "variable_assignment":
        return None
    text = node_text(node, src_bytes)
    pair = _split_key_value(text, "=")
    if not pair:
        return None
    name, value = pair
    return _build_env_entry(
        name.removeprefix("export").strip(),
        value,
        "bash_assignment",
        node.start_point[0] + 1,
    )


def _extract_bash_export_entries(node, src_bytes: bytes) -> list[EnvEntry]:
    command_text = node_text(node, src_bytes).strip()
    if not command_text.startswith("export "):
        return []

    results: list[EnvEntry] = []
    for child in node.children:
        if child.type != "variable_assignment":
            continue
        text = node_text(child, src_bytes)
        pair = _split_key_value(text, "=")
        if not pair:
            continue
        name, value = pair
        results.append(
            _build_env_entry(name, value, "bash_export", node.start_point[0] + 1),
        )
    return results


def _env_from_properties(source: str) -> list[EnvEntry]:
    """Extract key=value pairs from Java .properties files (Spring application.properties, etc.)."""
    results: list[EnvEntry] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!")):
            continue
        match = _PROPERTIES_RE.match(stripped)
        if not match:
            continue
        name, value = match.groups()
        results.append(_build_env_entry(name, value.strip(), "properties", line_number))
    return results


def _env_from_json(source: str) -> list[EnvEntry]:
    """Extract secret-pattern keys from nested JSON (appsettings.json, etc.)."""
    try:
        data = json.loads(source)
    except (json.JSONDecodeError, ValueError):
        return []
    results: list[EnvEntry] = []
    _walk_json_for_secrets(data, results, line=1)
    return results


def _walk_json_for_secrets(obj: Any, results: list[EnvEntry], line: int) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, str) and _has_secret_pattern(key):
                results.append(_build_env_entry(key, val, "json_key", line))
            elif isinstance(val, (dict, list)):
                _walk_json_for_secrets(val, results, line)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_secrets(item, results, line)


def _env_from_dotenv(source: str) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _DOTENV_RE.match(stripped)
        if not match:
            continue
        name, value = match.groups()
        results.append(_build_env_entry(name, value, "dotenv", line_number))
    return results


def _is_dotenv_name(name_lower: str) -> bool:
    return name_lower.startswith(".env") or name_lower.endswith(".env")


def _is_properties_name(name_lower: str) -> bool:
    return name_lower.endswith(".properties")


def _is_json_name(name_lower: str) -> bool:
    return name_lower.endswith(".json")


_AST_ENV_EXTRACTORS: dict[str, AstExtractor] = {
    "bash": _env_from_bash_ast,
    "dockerfile": _env_from_dockerfile_ast,
    "yaml": _env_from_yaml_ast,
}

_FALLBACK_ENV_EXTRACTORS: tuple[tuple[Callable[[str], bool], FallbackExtractor], ...] = (
    (_is_dotenv_name, _env_from_dotenv),
    (_is_properties_name, _env_from_properties),
    (_is_json_name, _env_from_json),
)
