from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .shared import _try_parse_config
from ..ts_utils import node_text


EnvEntry = dict[str, Any]
AstExtractor = Callable[[Any, bytes], list[EnvEntry]]
FallbackExtractor = Callable[[str], list[EnvEntry]]

_SECRET_PATTERNS = re.compile(
    r"(?i)(?:secret|password|passwd|token|api_?key|private_?key|credential|auth)",
)
_DOCKERFILE_ENV_RE = re.compile(r"^\s*(ENV|ARG)\s+(.+)", re.MULTILINE)
_DOTENV_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)",
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


def extract_env_variables(source: str, filepath: Path) -> list[EnvEntry]:
    tree, lang_key, src_bytes = _try_parse_config(source, filepath)

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


def _env_from_dockerfile_ast(root, src_bytes: bytes) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    for child in root.children:
        source_name = _DOCKERFILE_INSTRUCTION_SOURCES.get(child.type)
        if not source_name:
            continue
        for name, value in _extract_dockerfile_pairs(child, src_bytes):
            results.append(
                _build_env_entry(name, value, source_name, child.start_point[0] + 1),
            )
    return results


def _env_from_dockerfile_regex(source: str) -> list[EnvEntry]:
    results: list[EnvEntry] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        match = _DOCKERFILE_ENV_RE.match(line)
        if not match:
            continue
        instruction, body = match.groups()
        for name, value in _iter_dockerfile_pairs(body):
            results.append(_build_env_entry(name, value, instruction, line_number))
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
        env_value_node = _find_yaml_environment_value_node(current, src_bytes)
        if env_value_node:
            _collect_yaml_env_pairs(env_value_node, src_bytes, results)
            continue
        stack.extend(reversed(current.children))


def _find_yaml_environment_value_node(node, src_bytes: bytes):
    if node.type != "block_mapping_pair":
        return None

    key_node = None
    value_node = None
    for child in node.children:
        if key_node is None and (child.type == "flow_node" or child.type.endswith("_scalar")):
            key_node = child
            continue
        if child.type in _YAML_ENV_VALUE_NODE_TYPES:
            value_node = child

    if not key_node or node_text(key_node, src_bytes).strip() != "environment":
        return None
    return value_node


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

        if child.type not in _BASH_EXPORT_COMMAND_TYPES:
            continue
        results.extend(_extract_bash_export_entries(child, src_bytes))
    return results


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


def _is_dockerfile_name(name_lower: str) -> bool:
    return name_lower.startswith("dockerfile")


def _is_dotenv_name(name_lower: str) -> bool:
    return name_lower.startswith(".env") or name_lower.endswith(".env")


_AST_ENV_EXTRACTORS: dict[str, AstExtractor] = {
    "bash": _env_from_bash_ast,
    "dockerfile": _env_from_dockerfile_ast,
    "yaml": _env_from_yaml_ast,
}

_FALLBACK_ENV_EXTRACTORS: tuple[tuple[Callable[[str], bool], FallbackExtractor], ...] = (
    (_is_dockerfile_name, _env_from_dockerfile_regex),
    (_is_dotenv_name, _env_from_dotenv),
)
