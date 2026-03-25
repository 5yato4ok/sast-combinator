"""
MCP server exposing context-extractor tools for AI agent integration.

Provides smart code analysis tools (function extraction, identifier analysis,
data-flow tracing, project search) that resolve source paths via the AIST API.

External AI agents connect over Streamable HTTP and call tools lazily —
requesting only the context they actually need for TP/FP triage.
"""
import hmac
import logging
import os
import re
import time
from functools import wraps
from pathlib import Path

import httpx
from context_extractor import extract_function_from_source
from context_extractor.config import LANG_NODESETS
from context_extractor.config_analysis import (
    classify_environment as _classify_env,
)
from context_extractor.config_analysis import (
    extract_config_block as _extract_config_block,
)
from context_extractor.config_analysis import (
    extract_env_variables as _extract_env_vars,
)
from context_extractor.config_analysis import (
    find_config_overrides as _find_config_overrides,
)
from context_extractor.config_analysis import (
    find_related_configs as _find_related_configs,
)
from context_extractor.debug_ast import function_ast_to_string
from context_extractor.identifiers import split_reads_writes
from context_extractor.project_analysis import (
    classify_file as _classify_file,
)
from context_extractor.project_analysis import (
    find_callers as _find_callers,
)
from context_extractor.project_analysis import (
    find_decorators as _find_decorators,
)
from context_extractor.project_analysis import (
    find_definition as _find_definition,
)
from context_extractor.project_analysis import (
    find_imports as _find_imports,
)
from context_extractor.project_analysis import (
    find_route_to_function as _find_route,
)
from context_extractor.project_analysis import (
    get_file_structure as _get_file_structure,
)
from context_extractor.project_analysis import (
    trace_identifier_backward as _trace_backward,
)
from context_extractor.ts_utils import create_parser, detect_language
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# ── Configuration ────────────────────────────────────────────────
AIST_API_URL = os.environ.get("AIST_API_URL", "http://nginx:8080")
AIST_API_TOKEN = os.environ.get("AIST_API_TOKEN", "")
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

_http = httpx.Client(
    base_url=AIST_API_URL,
    headers={"Authorization": f"Token {AIST_API_TOKEN}"},
    timeout=10,
)


# ── Tool call logger ─────────────────────────────────────────────

def _log_tool(fn):
    """Decorator: log tool name, key args, duration, and any exceptions."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        name = fn.__name__
        pipeline_id = kwargs.get("pipeline_id") or (args[0] if args else "?")
        extra = kwargs.get("file_path") or kwargs.get("function_name") or kwargs.get("symbol_name") or ""
        label = f"{name}(pipeline={pipeline_id}" + (f", {extra}" if extra else "") + ")"
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            logger.info("%s → ok (%.2fs)", label, time.monotonic() - t0)
            return result
        except Exception as exc:
            logger.error("%s → error (%.2fs): %s", label, time.monotonic() - t0, exc)
            raise
    return wrapper


# ── Auth middleware ──────────────────────────────────────────────


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):

    """
    Reject requests without a valid Bearer token.

    When ``MCP_AUTH_TOKEN`` is set, every request must carry
    ``Authorization: Bearer <token>`` with a matching value.
    If the env var is empty the middleware is permissive (allows all) —
    useful for local development, but must be set in production.
    """

    async def dispatch(self, request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        logger.info("%s %s from %s", request.method, request.url.path, client)

        if not MCP_AUTH_TOKEN:
            # No token configured — skip auth (development mode)
            response = await call_next(request)
            logger.info("%s %s → %s", request.method, request.url.path, response.status_code)
            return response

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("Missing Authorization header from %s", client)
            return JSONResponse(
                {"error": "Missing Authorization header"},
                status_code=401,
            )

        provided = auth_header[7:]  # strip "Bearer "
        if not hmac.compare_digest(provided, MCP_AUTH_TOKEN):
            logger.warning("MCP auth failed from %s", client)
            return JSONResponse(
                {"error": "Invalid token"},
                status_code=403,
            )

        response = await call_next(request)
        logger.debug("%s %s → %s", request.method, request.url.path, response.status_code)
        return response


def _resolve_source_dir(pipeline_id: str) -> Path:
    """Resolve pipeline_id to source directory via AIST API."""
    logger.info("Resolving source dir for pipeline %s", pipeline_id)
    resp = _http.get(f"/api/v2/aist/pipelines/{pipeline_id}/source-info/")
    if resp.status_code == 409:
        data = resp.json()
        detail = data.get("detail", "Sources not available")
        logger.warning("Pipeline %s sources not available: %s", pipeline_id, detail)
        raise ValueError(detail)
    resp.raise_for_status()
    source_dir = Path(resp.json()["project_path"])
    if not source_dir.is_dir():
        msg = f"Source directory not found: {source_dir}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    logger.info("Pipeline %s → %s", pipeline_id, source_dir)
    return source_dir


def _read_source(pipeline_id: str, file_path: str) -> tuple[str, Path]:
    """Read a source file for a given pipeline, with path traversal guard."""
    source_dir = _resolve_source_dir(pipeline_id)
    full_path = (source_dir / file_path).resolve()
    if not str(full_path).startswith(str(source_dir.resolve())):
        msg = "Path traversal detected"
        raise ValueError(msg)
    if not full_path.is_file():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)
    return full_path.read_text(encoding="utf-8", errors="replace"), full_path


def _find_node_at_line(node, line_number: int):
    """Find the smallest AST node covering the given 1-based line number."""
    start = node.start_point[0] + 1
    end = node.end_point[0] + 1
    if not (start <= line_number <= end):
        return None
    for child in node.children:
        hit = _find_node_at_line(child, line_number)
        if hit:
            return hit
    return node


# ── MCP Server ───────────────────────────────────────────────────

mcp = FastMCP(
    name="ContextExtractor",
    host="0.0.0.0",  # noqa: S104
    port=8000,
    stateless_http=True,
)

# ── Existing tools ───────────────────────────────────────────────


@mcp.tool()
@_log_tool
def extract_function(pipeline_id: str, file_path: str, line_number: int) -> dict:
    """
    Extract the full function/method containing the given line number.

    Returns the function source code plus metadata: language, line range,
    the exact code on the target line. Use this as the first step to
    understand a vulnerability before making a TP/FP verdict.

    Args:
        pipeline_id: AIST pipeline ID (e.g. "a1b2c3d4")
        file_path: Relative path within the project (e.g. "src/auth/login.py")
        line_number: 1-based line number where the vulnerability was reported

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return extract_function_from_source(source, full_path.name, line_number, max_lines=200)


@mcp.tool()
@_log_tool
def find_identifiers(pipeline_id: str, file_path: str, line_number: int) -> dict:
    """
    Analyze which variables are read and written on the given line.

    Returns {reads: [...], writes: [...]}. Use this to trace data flow:
    understand where tainted input comes from and where it flows to.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project
        line_number: 1-based line number to analyze

    """
    source, full_path = _read_source(pipeline_id, file_path)
    lang, lang_key = detect_language(full_path)
    parser = create_parser(lang)
    source_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)

    nodeset = LANG_NODESETS[lang_key]
    target_node = _find_node_at_line(tree.root_node, line_number)
    if not target_node:
        return {"reads": [], "writes": [], "error": "No node found at line"}

    reads, writes = split_reads_writes(target_node, source_bytes, lang_key, nodeset)
    return {"reads": sorted(reads), "writes": sorted(writes), "language": lang_key}


@mcp.tool()
@_log_tool
def dump_ast(pipeline_id: str, file_path: str, line_number: int) -> str:
    """
    Show the AST structure of the function containing the given line.

    Useful for understanding code structure in unfamiliar languages
    or when extract_function does not provide enough structural context.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project
        line_number: 1-based line number

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return function_ast_to_string(source, full_path.name, line_number)


@mcp.tool()
@_log_tool
def list_supported_languages() -> list[str]:
    """List all programming languages supported by smart code analysis tools."""
    return sorted(LANG_NODESETS.keys())


# ── Data flow tools ──────────────────────────────────────────────


@mcp.tool()
@_log_tool
def find_callers(pipeline_id: str, file_path: str, function_name: str) -> list[dict]:
    """
    Search the entire project for call sites of a given function.

    Returns a list of locations where the function is called, with the
    surrounding code snippet and the name of the calling function.
    Use this to understand how a vulnerable function is invoked and
    whether user-controlled data reaches it.

    Works for any programming language via text search with AST refinement
    for supported languages.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: File where the function is defined (for context, not used as filter)
        function_name: Name of the function to search for (e.g. "execute_query")

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_callers(source_dir, file_path, function_name)


@mcp.tool()
@_log_tool
def trace_identifier_backward(
    pipeline_id: str, file_path: str, line_number: int, identifier: str,
) -> list[dict]:
    """
    Trace where a variable gets its value by walking backward through the function.

    Returns a chain of assignments leading to the variable, showing where
    the data originates. Each entry has {line, code, writes, reads}.
    Traces up to 3 hops backward. Essential for determining whether
    input is user-controlled (from request/params) or safe (constant/config).

    Works for any tree-sitter-supported language with regex fallback for others.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project
        line_number: 1-based line number where the identifier is used
        identifier: Variable name to trace (e.g. "user_input")

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return _trace_backward(source, full_path, line_number, identifier)


@mcp.tool()
@_log_tool
def find_definition(pipeline_id: str, symbol_name: str) -> list[dict]:
    """
    Search the project for definitions of a symbol (function, class, variable, type).

    Returns a list of locations where the symbol is defined, with kind and snippet.
    Use this to inspect helper functions, custom sanitizers, or type definitions
    that affect whether a finding is TP or FP.

    Works for any programming language via regex pattern matching.

    Args:
        pipeline_id: AIST pipeline ID
        symbol_name: Name to search for (e.g. "safe_query", "UserSerializer")

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_definition(source_dir, symbol_name)


# ── Security context tools ───────────────────────────────────────


@mcp.tool()
@_log_tool
def find_imports(pipeline_id: str, file_path: str) -> list[str]:
    """
    Collect all import/require/using/include statements from a file.

    Reveals which frameworks and libraries are used — critical for
    determining built-in protections. For example:
    - "from django.db import connection" suggests potential raw SQL usage
    - "import bleach" suggests HTML sanitization is available
    - ORM imports (Django/SQLAlchemy/Hibernate) imply parameterized queries

    AST-based for supported languages, regex fallback for others.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_imports(source_dir, file_path)


@mcp.tool()
@_log_tool
def find_decorators(pipeline_id: str, file_path: str, line_number: int) -> list[str]:
    """
    Find decorators and annotations on the function containing the given line.

    Returns decorator strings like "@login_required", "@csrf_exempt",
    "@RequestMapping", "@api_view(['GET'])". Critical for assessing:
    - Authentication: @login_required, @IsAuthenticated
    - CSRF protection: @csrf_exempt (disables protection!)
    - Authorization: @permission_required, @has_role
    - Input validation: @validated, serializer decorators

    AST-based for supported languages, regex fallback (@decorator pattern) for others.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project
        line_number: 1-based line number inside the function

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return _find_decorators(source, full_path, line_number)


@mcp.tool()
@_log_tool
def classify_file(pipeline_id: str, file_path: str) -> dict:
    """
    Classify a file as test, migration, generated, vendored, config, or production.

    Returns {type, confidence, reason}. Use this FIRST before deep analysis:
    - "test" files → findings are almost always FP (hardcoded creds, etc.)
    - "migration" files → DB migration code, usually safe to ignore
    - "vendored" / "generated" → not the project's own code
    - "config" → may contain security-relevant settings

    Language-agnostic: works purely on file path heuristics.

    Args:
        pipeline_id: AIST pipeline ID (used only for validation)
        file_path: Relative path within the project

    """
    _resolve_source_dir(pipeline_id)  # validate pipeline access
    return _classify_file(file_path)


# ── Navigation tools ─────────────────────────────────────────────


@mcp.tool()
@_log_tool
def get_file_structure(pipeline_id: str, file_path: str) -> dict:
    """
    Parse the top-level structure of a file: classes, functions, methods, imports.

    Returns {language, classes: [{name, line, methods}], functions: [{name, line}], imports}.
    Use this to understand a file's layout before reading specific functions.
    Saves tokens by letting you navigate to exactly what you need.

    AST-based for supported languages, regex fallback for others.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return _get_file_structure(source, full_path)


@mcp.tool()
@_log_tool
def find_route_to_function(pipeline_id: str, function_name: str) -> list[dict]:
    """
    Search for URL/route mappings that reference a given function or view.

    Returns a list of {file, line, pattern, snippet} for matching routes.
    Use this to determine if a vulnerable function is reachable from the
    outside — if there is no route mapping, the code may be dead/unreachable.

    Supports Django, Flask, FastAPI, Express.js, Spring, ASP.NET,
    Ruby on Rails, Laravel, Go net/http routing patterns.

    Args:
        pipeline_id: AIST pipeline ID
        function_name: Function/view name to search for (e.g. "UserView", "login")

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_route(source_dir, function_name)


# ── Config / misconfiguration tools ──────────────────────────────


@mcp.tool()
@_log_tool
def extract_config_block(pipeline_id: str, file_path: str, line_number: int) -> dict:
    """
    Extract the logical config block containing the given line.

    For YAML: returns the parent mapping pair (e.g. a full service definition).
    For Dockerfile: returns the instruction (RUN, ENV, EXPOSE, etc.).
    For HCL/Terraform: returns the enclosing resource/data/variable block.
    For TOML: returns the table or key-value pair.
    For JSON: returns the enclosing object or pair.

    All parsing is AST-based (tree-sitter). Falls back to indentation-based
    extraction for unsupported formats.

    Returns {block_text, block_type, key_path, start_line, end_line, language}.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path to the config file
        line_number: 1-based line number of the finding

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return _extract_config_block(source, full_path, line_number)


@mcp.tool()
@_log_tool
def classify_environment(pipeline_id: str, file_path: str) -> dict:
    """
    Determine the target environment (dev/staging/prod/test) of a config file.

    Returns {environment, confidence, reason}. Use this FIRST for config findings:
    - "dev" or "test" → finding is low priority or FP
    - "production" → finding is high priority
    - "unknown" → may be shared config, treat as potentially production

    Works on filename/path heuristics (e.g. ".dev.", "-prod.", "staging/").

    Args:
        pipeline_id: AIST pipeline ID (used only for validation)
        file_path: Relative path to the config file

    """
    _resolve_source_dir(pipeline_id)  # validate pipeline access
    return _classify_env(file_path)


@mcp.tool()
@_log_tool
def find_config_overrides(
    pipeline_id: str, file_path: str, key_or_variable: str,
) -> list[dict]:
    """
    Search the project for the same config key/variable in other config files.

    Returns a list of {file, line, value, environment} showing where the key
    appears in other files. Essential for determining if an insecure default
    in a dev config is overridden with a secure value in production.

    Example: DD_DEBUG=True in .env.dev → finds DD_DEBUG=False in .env.prod → FP.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Origin file (excluded from results)
        key_or_variable: Config key or env variable name to search for

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_config_overrides(source_dir, file_path, key_or_variable)


@mcp.tool()
@_log_tool
def extract_env_variables(pipeline_id: str, file_path: str) -> list[dict]:
    """
    Extract all environment variable definitions from a config file.

    Supports .env files, docker-compose.yml (environment: section),
    Dockerfile (ENV/ARG instructions), and shell scripts (export/assignment).
    All parsing is AST-based where a tree-sitter grammar is available.

    Returns a list of {name, value, source, line, has_secret_pattern}.
    The has_secret_pattern flag is True when the variable name matches
    common secret patterns (SECRET, PASSWORD, TOKEN, API_KEY, etc.).

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path to the config file

    """
    source, full_path = _read_source(pipeline_id, file_path)
    return _extract_env_vars(source, full_path)


@mcp.tool()
@_log_tool
def find_related_configs(pipeline_id: str, file_path: str) -> list[dict]:
    """
    Find configuration files related to the given file.

    Detects relationships like:
    - Dockerfile ↔ docker-compose files (builds/referenced_by)
    - docker-compose.yml ↔ .env files (env_file)
    - docker-compose variants (dev/prod/override)
    - Terraform module peers (main.tf ↔ variables.tf ↔ tfvars)
    - K8s peer resources (deployment ↔ service ↔ configmap)
    - Helm values ↔ templates

    Returns a list of {file, relationship}.

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path to the config file

    """
    source_dir = _resolve_source_dir(pipeline_id)
    return _find_related_configs(source_dir, file_path)


# ── Filesystem tools (replaces standalone filesystem MCP server) ──

_MAX_FILE_SIZE = 1_048_576  # 1 MB — refuse to return larger files
_MAX_SEARCH_RESULTS = 50


@mcp.tool()
@_log_tool
def read_file(pipeline_id: str, file_path: str) -> str:
    """
    Read the full contents of a file from the project source tree.

    Use this when smart tools (extract_function, extract_config_block)
    don't cover your needs — e.g. reading a full config file, a README,
    or a file in an unsupported format.

    Returns the file contents as a string (max 1 MB).

    Args:
        pipeline_id: AIST pipeline ID
        file_path: Relative path within the project

    """
    source, _full_path = _read_source(pipeline_id, file_path)
    if len(source) > _MAX_FILE_SIZE:
        return source[:_MAX_FILE_SIZE] + "\n\n... [truncated at 1 MB]"
    return source


@mcp.tool()
@_log_tool
def search_files(pipeline_id: str, pattern: str, path: str = "") -> list[dict]:
    """
    Search for a text pattern (regex) across all source and config files.

    Returns a list of {file, line, match} for each matching line.
    Equivalent to running grep across the project. Limited to 50 results.

    Args:
        pipeline_id: AIST pipeline ID
        pattern: Regular expression to search for (e.g. "cursor[.]execute")
        path: Optional subdirectory to limit search (e.g. "src/auth")

    """
    source_dir = _resolve_source_dir(pipeline_id)
    search_root = source_dir / path if path else source_dir

    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return [{"error": f"Invalid regex: {e}"}]

    results: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(search_root):
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", "vendor", ".tox"}
        ]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines()):
                if compiled.search(line):
                    rel = fpath.relative_to(source_dir)
                    results.append({
                        "file": str(rel),
                        "line": i + 1,
                        "match": line.strip()[:200],
                    })
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        return results
    return results


@mcp.tool()
@_log_tool
def list_directory(pipeline_id: str, path: str = "") -> list[dict]:
    """
    List files and directories in a project path.

    Returns a list of {name, type, size} entries.
    Use this to explore project structure before reading specific files.

    Args:
        pipeline_id: AIST pipeline ID
        path: Relative directory path (empty string for project root)

    """
    source_dir = _resolve_source_dir(pipeline_id)
    target = source_dir / path if path else source_dir

    if not target.is_dir():
        return [{"error": f"Not a directory: {path}"}]

    # Path traversal guard
    if not str(target.resolve()).startswith(str(source_dir.resolve())):
        return [{"error": "Path traversal detected"}]

    entries: list[dict] = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith(".git"):
                continue
            entry: dict = {"name": item.name}
            if item.is_dir():
                entry["type"] = "directory"
            else:
                entry["type"] = "file"
                try:
                    entry["size"] = item.stat().st_size
                except OSError:
                    entry["size"] = 0
            entries.append(entry)
    except OSError:
        return [{"error": f"Cannot read directory: {path}"}]
    return entries


if __name__ == "__main__":
    if MCP_AUTH_TOKEN:
        logger.info("MCP auth enabled — Bearer token required")
    else:
        logger.warning("MCP_AUTH_TOKEN not set — auth disabled (development mode)")

    # Get the Starlette ASGI app and add middleware
    from starlette.middleware.cors import CORSMiddleware

    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
