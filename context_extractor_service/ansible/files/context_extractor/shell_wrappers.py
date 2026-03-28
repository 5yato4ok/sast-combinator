from __future__ import annotations

from tree_sitter import Node

from .ts_utils import node_text

_BASH_REDIRECT_OPERATOR_TYPES = frozenset({
    ">", ">>", "<", "<<", "<<-", "<>", ">&", "<&", ">|",
})
_BASH_OUTPUT_REDIRECT_OPERATOR_TYPES = frozenset({">", ">>", "<>", ">&", ">|"})
_BASH_INPUT_REDIRECT_OPERATOR_TYPES = frozenset({"<", "<<", "<<-", "<&"})
_SHELL_COMMAND_NAMES = frozenset({"sh", "bash", "dash", "zsh", "ksh"})
_FORWARDING_WRAPPER_PATTERNS = (
    ("docker", "exec"),
    ("docker", "compose", "exec"),
    ("docker", "container", "exec"),
    ("podman", "exec"),
)
_LAST_ARG_COMMAND_WRAPPERS = frozenset({"ssh"})
_PREFIX_WRAPPER_NAMES = frozenset({"env", "sudo"})
_SUDO_OPTION_TAKES_VALUE = frozenset({"-C", "-D", "-g", "-h", "-p", "-R", "-r", "-t", "-T", "-u"})


def normalize_shell_word_text(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def normalize_shell_node_text(node: Node, source_bytes: bytes) -> str:
    return normalize_shell_word_text(node_text(node, source_bytes))


def is_shell_exec_flag(text: str) -> bool:
    return text.startswith("-") and "c" in text[1:]


def is_bash_redirect_operator(node_type: str) -> bool:
    return node_type in _BASH_REDIRECT_OPERATOR_TYPES


def is_input_redirect_operator(node_type: str | None) -> bool:
    return node_type in _BASH_INPUT_REDIRECT_OPERATOR_TYPES


def is_output_redirect_operator(node_type: str | None) -> bool:
    return node_type in _BASH_OUTPUT_REDIRECT_OPERATOR_TYPES


def command_name_text(node: Node, source_bytes: bytes) -> str | None:
    name = next((child for child in node.children if child.type == "command_name"), None)
    if name is None:
        return None
    return normalize_shell_node_text(name, source_bytes)


def command_argument_nodes(node: Node) -> list[Node]:
    return [child for child in node.children if child.type != "command_name"]


def _extract_direct_shell_command(argv: list[str]) -> str | None:
    for index, text in enumerate(argv[:-1]):
        if text not in _SHELL_COMMAND_NAMES:
            continue
        for flag_index in range(index + 1, len(argv) - 1):
            if is_shell_exec_flag(argv[flag_index]):
                return argv[flag_index + 1]
    return None


def _strip_env_prefix(argv: list[str]) -> list[str]:
    index = 1
    while index < len(argv):
        text = argv[index]
        if text == "--":
            return argv[index + 1:]
        if text.startswith("-"):
            index += 1
            continue
        if "=" in text and not text.startswith("="):
            index += 1
            continue
        return argv[index:]
    return []


def _strip_sudo_prefix(argv: list[str]) -> list[str]:
    index = 1
    while index < len(argv):
        text = argv[index]
        if text == "--":
            return argv[index + 1:]
        if text in _SUDO_OPTION_TAKES_VALUE:
            index += 2
            continue
        if text.startswith("-"):
            index += 1
            continue
        return argv[index:]
    return []


def _strip_prefix_wrapper(argv: list[str]) -> list[str]:
    if not argv:
        return []
    if argv[0] == "env":
        return _strip_env_prefix(argv)
    if argv[0] == "sudo":
        return _strip_sudo_prefix(argv)
    return argv


def _unwrap_prefix_wrappers(argv: list[str]) -> list[str]:
    current = argv
    while current and current[0] in _PREFIX_WRAPPER_NAMES:
        next_argv = _strip_prefix_wrapper(current)
        if next_argv == current:
            break
        current = next_argv
    return current


def _extract_forwarded_shell_command(argv: list[str]) -> str | None:
    for pattern in _FORWARDING_WRAPPER_PATTERNS:
        if len(argv) <= len(pattern) or tuple(argv[: len(pattern)]) != pattern:
            continue
        return _extract_direct_shell_command(argv[len(pattern):])
    return None


def find_shell_wrapper_command_text(node: Node, source_bytes: bytes) -> str | None:
    command_name = command_name_text(node, source_bytes)
    if command_name is None:
        return None

    args = command_argument_nodes(node)
    arg_texts = [normalize_shell_node_text(arg, source_bytes) for arg in args]
    argv = _unwrap_prefix_wrappers([command_name, *arg_texts])
    if not argv:
        return None
    command_name = argv[0]

    direct_shell = _extract_direct_shell_command(argv)
    if direct_shell is not None:
        return direct_shell

    forwarded_shell = _extract_forwarded_shell_command(argv)
    if forwarded_shell is not None:
        return forwarded_shell

    if command_name in _LAST_ARG_COMMAND_WRAPPERS and len(argv) >= 3:
        return argv[-1]

    return None
