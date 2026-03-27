from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .classification import classify_file
from .shared import (
    _find_enclosing_function_name,
    _iter_source_files,
    _snippet,
    _try_parse,
    _MAX_RESULTS,
)
from .symbols import _is_definition_site_for_symbol


def find_callers(source_dir: Path, file_path: str, function_name: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(function_name)
        + r"\s*\(",
    )
    results: list[dict[str, Any]] = []
    treat_as_class_like = bool(function_name[:1].isupper())

    for rel in _iter_source_files(source_dir):
        if _should_skip_caller_file(rel):
            continue
        full = source_dir / rel
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not pattern.search(text):
            continue
        lines = text.splitlines()
        cached_tree, cached_lang_key, cached_src_bytes = _try_parse(text, full)
        for line_index in _iter_caller_candidate_lines(lines, pattern):
            if _should_skip_caller_candidate(
                lines[line_index],
                function_name,
                cached_tree,
                cached_lang_key,
                cached_src_bytes,
                line_index + 1,
                treat_as_class_like,
            ):
                continue
            results.append(
                _build_caller_result(
                    rel,
                    lines,
                    line_index,
                    cached_tree,
                    cached_lang_key,
                )
            )
            if len(results) >= _MAX_RESULTS:
                return results
    return results


def _should_skip_caller_file(rel: Path) -> bool:
    file_class = classify_file(str(rel))
    return file_class["type"] in {"vendored", "generated"}


def _iter_caller_candidate_lines(lines: list[str], pattern: re.Pattern[str]):
    for index, line in enumerate(lines):
        if pattern.search(line):
            yield index


def _is_constructor_instantiation(stripped: str, function_name: str) -> bool:
    return bool(re.search(r"\bnew\s+" + re.escape(function_name) + r"\s*\(", stripped))


def _is_function_definition_prefix(stripped: str) -> bool:
    return bool(
        re.match(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?"
            r"(?:def|func|function|fn)\s+",
            stripped,
        )
    )


def _is_cpp_scoped_definition(stripped: str, function_name: str) -> bool:
    return bool(re.search(r"\w+(?:::\w+)*::" + re.escape(function_name) + r"\s*\(", stripped))


def _is_cpp_forward_declaration(stripped: str, function_name: str) -> bool:
    return bool(
        re.search(
            r"(?:^|[\s;{])"
            r"(?:virtual\s+|static\s+|inline\s+)*"
            r"\w[\w\s*&<>,]*\s+"
            + re.escape(function_name) + r"\s*\([^)]*\)\s*"
            r"(?:const\s*)?(?:override\s*)?(?:=\s*0\s*)?;",
            stripped,
        )
    )


def _is_ts_js_method_definition(stripped: str, function_name: str) -> bool:
    return bool(
        re.match(
            r"(?:async\s+)?" + re.escape(function_name) + r"\s*\([^)]*\)\s*"
            r"(?::\s*\w[^{]*)?{",
            stripped,
        )
    )


def _is_ast_definition_site(
    cached_tree,
    cached_lang_key: str | None,
    cached_src_bytes: bytes | None,
    line_number: int,
    function_name: str,
    treat_as_class_like: bool,
) -> bool:
    return bool(
        cached_tree
        and cached_lang_key
        and cached_src_bytes
        and not treat_as_class_like
        and _is_definition_site_for_symbol(
            cached_tree.root_node,
            cached_src_bytes,
            cached_lang_key,
            line_number,
            function_name,
        )
    )


def _should_skip_caller_candidate(
    line: str,
    function_name: str,
    cached_tree,
    cached_lang_key: str | None,
    cached_src_bytes: bytes | None,
    line_number: int,
    treat_as_class_like: bool,
) -> bool:
    stripped = line.lstrip()
    return any(
        (
            _is_constructor_instantiation(stripped, function_name),
            _is_function_definition_prefix(stripped),
            _is_cpp_scoped_definition(stripped, function_name),
            _is_cpp_forward_declaration(stripped, function_name),
            _is_ts_js_method_definition(stripped, function_name),
            _is_ast_definition_site(
                cached_tree,
                cached_lang_key,
                cached_src_bytes,
                line_number,
                function_name,
                treat_as_class_like,
            ),
        )
    )


def _build_caller_result(
    rel: Path,
    lines: list[str],
    line_index: int,
    cached_tree,
    cached_lang_key: str | None,
) -> dict[str, Any]:
    caller = None
    if cached_tree and cached_lang_key:
        caller = _find_enclosing_function_name(
            cached_tree.root_node,
            line_index + 1,
            cached_lang_key,
        )
    return {
        "file": str(rel),
        "line": line_index + 1,
        "caller_function": caller,
        "snippet": _snippet(lines, line_index, ctx=1),
    }
