"""
REST API wrapper tests — structural + integration.

Integration tests call real tool logic (no mock for parsing/analysis),
but stub the AIST API boundary (_read_source / _resolve_source_dir)
using the same fixture approach as the rest of the test suite.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE = ROOT / "fixtures" / "sample_project"
VIEWS_PY = (SAMPLE / "src/auth/views.py").read_text()


def _make_client() -> TestClient:
    """Build a TestClient wrapping only the REST router (no MCP protocol)."""
    app = Starlette(routes=[Mount("/v1", app=mcp_server._rest_router)])
    app.add_middleware(mcp_server.BearerTokenAuthMiddleware)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client() -> TestClient:
    return _make_client()


def _stub_read_source(source: str, file_name: str):
    """Return a _read_source stub that yields fixed (source, Path(file_name))."""
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)
    return _reader


def _stub_resolve_source_dir(root: Path):
    """Return a _resolve_source_dir stub that always returns *root*."""
    def _resolver(_pipeline_id: str) -> Path:
        return root
    return _resolver


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_missing_header_returns_401_when_token_required(self):
        with patch.object(mcp_server, "MCP_AUTH_TOKEN", "secret"):
            resp = _make_client().get("/v1/tools")
        assert resp.status_code == 401

    def test_wrong_token_returns_403(self):
        with patch.object(mcp_server, "MCP_AUTH_TOKEN", "secret"):
            resp = _make_client().get(
                "/v1/tools", headers={"Authorization": "Bearer wrong"}
            )
        assert resp.status_code == 403

    def test_correct_token_allows_request(self):
        with patch.object(mcp_server, "MCP_AUTH_TOKEN", "secret"):
            resp = _make_client().get(
                "/v1/tools", headers={"Authorization": "Bearer secret"}
            )
        assert resp.status_code == 200

    def test_no_token_configured_allows_all(self, client):
        resp = client.get("/v1/tools")
        assert resp.status_code == 200


# ── GET /v1/tools — schema listing ───────────────────────────────────────────

class TestListTools:
    def test_returns_all_20_tools(self, client):
        data = client.get("/v1/tools").json()
        assert len(data) == 20

    def test_each_entry_has_required_fields(self, client):
        for tool in client.get("/v1/tools").json():
            assert {"name", "description", "params"} <= tool.keys()
            for p in tool["params"]:
                assert {"name", "type", "required"} <= p.keys()

    def test_extract_function_param_types(self, client):
        tools = {t["name"]: t for t in client.get("/v1/tools").json()}
        params = {p["name"]: p for p in tools["extract_function"]["params"]}
        assert params["pipeline_id"]["type"] == "string"
        assert params["line_number"]["type"] == "integer"
        assert params["line_number"]["required"] is True

    def test_search_files_path_param_is_optional(self, client):
        tools = {t["name"]: t for t in client.get("/v1/tools").json()}
        params = {p["name"]: p for p in tools["search_files"]["params"]}
        assert params["path"]["required"] is False

    def test_list_supported_languages_has_no_params(self, client):
        tools = {t["name"]: t for t in client.get("/v1/tools").json()}
        assert tools["list_supported_languages"]["params"] == []


# ── POST routing / validation ─────────────────────────────────────────────────

class TestRouting:
    def test_unknown_tool_returns_404(self, client):
        resp = client.post("/v1/tools/nonexistent_tool", json={})
        assert resp.status_code == 404
        assert "Unknown tool" in resp.json()["error"]

    def test_missing_required_param_returns_400_with_param_name(self, client):
        resp = client.post(
            "/v1/tools/extract_function",
            json={"pipeline_id": "x", "file_path": "y"},  # line_number missing
        )
        assert resp.status_code == 400
        assert "line_number" in resp.json()["error"]

    def test_missing_pipeline_id_returns_400(self, client):
        resp = client.post(
            "/v1/tools/extract_function",
            json={"file_path": "y", "line_number": 1},
        )
        assert resp.status_code == 400
        assert "pipeline_id" in resp.json()["error"]

    def test_invalid_integer_type_returns_400(self, client):
        resp = client.post(
            "/v1/tools/extract_function",
            json={"pipeline_id": "x", "file_path": "y", "line_number": "notanint"},
        )
        assert resp.status_code == 400
        assert "line_number" in resp.json()["error"]

    def test_non_json_body_returns_400(self, client):
        resp = client.post(
            "/v1/tools/extract_function",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert "JSON" in resp.json()["error"]

    def test_json_array_body_returns_400(self, client):
        resp = client.post("/v1/tools/extract_function", json=["a", "b"])
        assert resp.status_code == 400


# ── Integration: list_supported_languages (no pipeline needed) ────────────────

class TestListSupportedLanguages:
    def test_returns_valid_language_list(self, client):
        resp = client.post("/v1/tools/list_supported_languages", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool"] == "list_supported_languages"
        assert isinstance(data["result"], list)
        assert "python" in data["result"]
        assert "javascript" in data["result"]
        assert "go" in data["result"]

    def test_response_envelope_shape(self, client):
        data = client.post("/v1/tools/list_supported_languages", json={}).json()
        assert set(data.keys()) == {"tool", "result"}


# ── Integration: extract_function ─────────────────────────────────────────────

class TestExtractFunction:
    def test_extracts_search_users(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/extract_function", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        # result shape: {text, meta: {language, function_lines, target_line, code_on_line}}
        assert "search_users" in result["text"]
        assert result["meta"]["language"] == "python"
        start, end = result["meta"]["function_lines"]
        assert start <= 14 <= end
        assert "cursor.execute" in result["meta"]["code_on_line"]

    def test_extracts_get_user_by_id(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/extract_function", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 21,
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert "get_user_by_id" in result["text"]
        assert "user_id" in result["text"]

    def test_result_contains_full_function_body(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/extract_function", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        }).json()["result"]

        assert "def search_users" in result["text"]
        start, end = result["meta"]["function_lines"]
        assert end > start


# ── Integration: find_identifiers ─────────────────────────────────────────────

class TestFindIdentifiers:
    def test_cursor_execute_line_reads_include_sink_operands(self, client, monkeypatch):
        """Line 14: cursor.execute(f"...{sanitized}") — cursor and sanitized are reads."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/find_identifiers", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["language"] == "python"
        assert "cursor" in result["reads"]
        assert "sanitized" in result["reads"]

    def test_assignment_line_has_correct_writes(self, client, monkeypatch):
        """Line 11: query = request.GET.get("q") — query is written."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/find_identifiers", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 11,
        })

        assert resp.status_code == 200
        assert "query" in resp.json()["result"]["writes"]

    def test_result_has_reads_writes_language_keys(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/find_identifiers", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        }).json()["result"]

        assert {"reads", "writes", "language"} <= result.keys()
        assert isinstance(result["reads"], list)
        assert isinstance(result["writes"], list)


# ── Integration: find_imports ─────────────────────────────────────────────────

class TestFindImports:
    def test_python_imports_from_views_py(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/find_imports", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        })

        assert resp.status_code == 200
        imports = resp.json()["result"]
        joined = "\n".join(imports)
        assert "django.db" in joined
        assert "bleach" in joined

    def test_result_is_list_of_strings(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/find_imports", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        }).json()["result"]

        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)
        assert len(result) >= 3  # django.db, decorators, bleach


# ── Integration: find_decorators ──────────────────────────────────────────────

class TestFindDecorators:
    def test_search_users_has_login_required_and_csrf_exempt(self, client, monkeypatch):
        """Lines 8-10: @login_required @csrf_exempt on search_users."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/find_decorators", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        })

        assert resp.status_code == 200
        joined = "\n".join(resp.json()["result"])
        assert "login_required" in joined
        assert "csrf_exempt" in joined

    def test_plain_function_has_no_decorators(self, client, monkeypatch):
        """Line 20 is inside get_user_by_id which has no decorators."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/find_decorators", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 20,
        })

        assert resp.status_code == 200
        assert resp.json()["result"] == []


# ── Integration: trace_identifier_backward ────────────────────────────────────

class TestTraceIdentifierBackward:
    def test_sanitized_traces_back_to_bleach_clean(self, client, monkeypatch):
        """Line 14 uses `sanitized`; line 12 assigns it from bleach.clean(query)."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/trace_identifier_backward", json={
            "pipeline_id": "pipe",
            "file_path": "src/auth/views.py",
            "line_number": 14,
            "identifier": "sanitized",
        })

        assert resp.status_code == 200
        chain = resp.json()["result"]
        assert len(chain) >= 1
        codes = " ".join(step["code"] for step in chain)
        assert "bleach" in codes or "sanitized" in codes

    def test_query_traces_back_to_request_get(self, client, monkeypatch):
        """Line 12 uses `query`; line 11 assigns query = request.GET.get("q")."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/trace_identifier_backward", json={
            "pipeline_id": "pipe",
            "file_path": "src/auth/views.py",
            "line_number": 12,
            "identifier": "query",
        })

        assert resp.status_code == 200
        chain = resp.json()["result"]
        assert len(chain) >= 1
        assert any("request" in step["code"] for step in chain)

    def test_each_step_has_line_code_writes_reads(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        chain = client.post("/v1/tools/trace_identifier_backward", json={
            "pipeline_id": "pipe",
            "file_path": "src/auth/views.py",
            "line_number": 14,
            "identifier": "sanitized",
        }).json()["result"]

        for step in chain:
            assert {"line", "code", "writes", "reads"} <= step.keys()


# ── Integration: get_file_structure ───────────────────────────────────────────

class TestGetFileStructure:
    def test_parses_all_three_functions_from_views_py(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/get_file_structure", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["language"] == "python"
        fn_names = {f["name"] for f in result.get("functions", [])}
        assert {"search_users", "get_user_by_id", "internal_helper"} <= fn_names

    def test_structure_contains_imports(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/get_file_structure", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        }).json()["result"]

        joined = "\n".join(result.get("imports", []))
        assert "django" in joined or "bleach" in joined


# ── Integration: classify_file ────────────────────────────────────────────────

class TestClassifyFile:
    """classify_file falls back to path heuristics when _resolve_source_dir fails,
    so these tests work with or without a patched resolver."""

    def test_test_file_classified_as_test(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/classify_file", json={
            "pipeline_id": "pipe", "file_path": "tests/test_auth.py",
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["type"] == "test"
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["reason"], str)

    def test_source_file_classified_as_production(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/classify_file", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        })

        assert resp.status_code == 200
        assert resp.json()["result"]["type"] == "production"

    def test_migration_file_classified_correctly(self, client):
        resp = client.post("/v1/tools/classify_file", json={
            "pipeline_id": "pipe", "file_path": "app/migrations/0001_initial.py",
        })
        # 200 because classify_file is resilient to _resolve_source_dir failures
        assert resp.status_code == 200
        assert resp.json()["result"]["type"] == "migration"


# ── Integration: find_callers (project-wide, real fixture dir) ────────────────

class TestFindCallers:
    def test_finds_validate_input_callers_in_utils_js(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_callers", json={
            "pipeline_id": "pipe",
            "file_path": "src/auth/utils.js",
            "function_name": "validateInput",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) >= 1
        assert any("utils.js" in r["file"] for r in results)
        for r in results:
            assert {"file", "line", "caller_function", "snippet"} <= r.keys()

    def test_nonexistent_function_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_callers", json={
            "pipeline_id": "pipe",
            "file_path": "src/auth/views.py",
            "function_name": "totally_nonexistent_xyz_abc",
        })

        assert resp.status_code == 200
        assert resp.json()["result"] == []


# ── Integration: find_definition ─────────────────────────────────────────────

class TestFindDefinition:
    def test_finds_search_users_in_views_py(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_definition", json={
            "pipeline_id": "pipe", "symbol_name": "search_users",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) >= 1
        assert results[0]["kind"] == "function"
        assert "views.py" in results[0]["file"]
        assert {"file", "line", "kind"} <= results[0].keys()

    def test_unknown_symbol_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_definition", json={
            "pipeline_id": "pipe", "symbol_name": "totally_unknown_xyz",
        })

        assert resp.status_code == 200
        assert resp.json()["result"] == []


# ── Integration: search_files ─────────────────────────────────────────────────

class TestSearchFiles:
    def test_finds_bleach_in_views_py(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/search_files", json={
            "pipeline_id": "pipe", "pattern": "bleach",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) >= 1
        assert any("views.py" in r["file"] for r in results)

    def test_search_scoped_to_subdirectory(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/search_files", json={
            "pipeline_id": "pipe", "pattern": "bleach", "path": "src/auth",
        })

        assert resp.status_code == 200
        assert len(resp.json()["result"]) >= 1

    def test_each_result_has_file_line_match(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        results = client.post("/v1/tools/search_files", json={
            "pipeline_id": "pipe", "pattern": "django",
        }).json()["result"]

        assert len(results) >= 1
        for r in results:
            assert {"file", "line", "match"} <= r.keys()
            assert isinstance(r["line"], int)
            assert r["line"] >= 1

    def test_no_pattern_match_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        results = client.post("/v1/tools/search_files", json={
            "pipeline_id": "pipe", "pattern": "ZZZNOMATCH_XYZ_9999",
        }).json()["result"]

        assert results == []


# ── Integration: list_directory ───────────────────────────────────────────────

class TestListDirectory:
    def test_lists_auth_directory_contents(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/list_directory", json={
            "pipeline_id": "pipe", "path": "src/auth",
        })

        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()["result"]}
        assert "views.py" in names
        assert "urls.py" in names

    def test_lists_project_root_when_path_omitted(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/list_directory", json={"pipeline_id": "pipe"})

        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()["result"]}
        assert "src" in names

    def test_file_entries_have_type_and_size(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        entries = client.post("/v1/tools/list_directory", json={
            "pipeline_id": "pipe", "path": "src/auth",
        }).json()["result"]

        files = [e for e in entries if e["type"] == "file"]
        assert len(files) >= 1
        for f in files:
            assert "size" in f
            assert isinstance(f["size"], int)

    def test_directory_entries_have_no_size(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        entries = client.post("/v1/tools/list_directory", json={
            "pipeline_id": "pipe",
        }).json()["result"]

        dirs = [e for e in entries if e.get("type") == "directory"]
        assert len(dirs) >= 1
        for d in dirs:
            assert "size" not in d


# ── Integration: get_file_structure — end_line ───────────────────────────────

class TestGetFileStructureEndLine:
    def test_functions_include_end_line(self, client, monkeypatch):
        """get_file_structure must return end_line for each function entry."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/get_file_structure", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        }).json()["result"]

        for fn in result.get("functions", []):
            assert "end_line" in fn, f"function {fn['name']} missing end_line"
            assert isinstance(fn["end_line"], int)
            assert fn["end_line"] >= fn["line"]


# ── Integration: dump_ast ─────────────────────────────────────────────────────

DOCKERFILE_SRC = (SAMPLE / "Dockerfile").read_text()
ENV_DEV_SRC = (SAMPLE / ".env.dev").read_text()


class TestDumpAst:
    def test_returns_nonempty_string(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/dump_ast", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py", "line_number": 14,
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert isinstance(result, str)
        assert len(result) > 0

    def test_envelope_shape(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        data = client.post("/v1/tools/dump_ast", json={
            "pipeline_id": "pipe", "file_path": "views.py", "line_number": 14,
        }).json()

        assert set(data.keys()) == {"tool", "result"}
        assert data["tool"] == "dump_ast"

    def test_ast_contains_function_node_type(self, client, monkeypatch):
        """AST string must reference the enclosing function node."""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        result = client.post("/v1/tools/dump_ast", json={
            "pipeline_id": "pipe", "file_path": "views.py", "line_number": 14,
        }).json()["result"]

        # tree-sitter Python: function_definition or method_definition
        assert "function_definition" in result or "function" in result.lower()


# ── Integration: read_file ────────────────────────────────────────────────────

class TestReadFile:
    def test_returns_full_file_contents(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        resp = client.post("/v1/tools/read_file", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert isinstance(result, str)
        assert "bleach" in result
        assert "cursor.execute" in result

    def test_result_is_string_not_dict(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(VIEWS_PY, "views.py"))

        data = client.post("/v1/tools/read_file", json={
            "pipeline_id": "pipe", "file_path": "src/auth/views.py",
        }).json()

        assert data["tool"] == "read_file"
        assert isinstance(data["result"], str)


# ── Integration: find_route_to_function ──────────────────────────────────────

class TestFindRouteToFunction:
    def test_finds_search_users_in_urls_py(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_route_to_function", json={
            "pipeline_id": "pipe", "function_name": "search_users",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert len(results) >= 1
        assert any("urls.py" in r["file"] for r in results)
        for r in results:
            assert {"file", "line", "pattern", "snippet"} <= r.keys()

    def test_unknown_function_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_route_to_function", json={
            "pipeline_id": "pipe", "function_name": "totally_nonexistent_xyz_abc",
        })

        assert resp.status_code == 200
        assert resp.json()["result"] == []


# ── Integration: classify_environment ────────────────────────────────────────

class TestClassifyEnvironment:
    def test_dev_env_file_classified_as_development(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/classify_environment", json={
            "pipeline_id": "pipe", "file_path": ".env.dev",
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["environment"] == "dev"
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["reason"], str)

    def test_prod_env_file_classified_as_production(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/classify_environment", json={
            "pipeline_id": "pipe", "file_path": ".env.prod",
        })

        assert resp.status_code == 200
        assert resp.json()["result"]["environment"] == "production"

    def test_result_shape_has_required_keys(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        result = client.post("/v1/tools/classify_environment", json={
            "pipeline_id": "pipe", "file_path": ".env.dev",
        }).json()["result"]

        assert {"environment", "confidence", "reason"} <= result.keys()


# ── Integration: extract_env_variables ───────────────────────────────────────

class TestExtractEnvVariables:
    def test_extracts_secret_key_with_has_secret_pattern(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(ENV_DEV_SRC, ".env.dev"))

        resp = client.post("/v1/tools/extract_env_variables", json={
            "pipeline_id": "pipe", "file_path": ".env.dev",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert isinstance(results, list)
        names = {e["name"] for e in results}
        assert "DD_SECRET_KEY" in names
        secret = next(e for e in results if e["name"] == "DD_SECRET_KEY")
        assert secret["has_secret_pattern"] is True
        assert secret["value"] == "insecure-dev-key-12345"

    def test_debug_flag_has_no_secret_pattern(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(ENV_DEV_SRC, ".env.dev"))

        results = client.post("/v1/tools/extract_env_variables", json={
            "pipeline_id": "pipe", "file_path": ".env.dev",
        }).json()["result"]

        debug = next((e for e in results if e["name"] == "DD_DEBUG"), None)
        assert debug is not None
        assert debug["has_secret_pattern"] is False

    def test_each_entry_has_required_fields(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(ENV_DEV_SRC, ".env.dev"))

        results = client.post("/v1/tools/extract_env_variables", json={
            "pipeline_id": "pipe", "file_path": ".env.dev",
        }).json()["result"]

        assert len(results) >= 1
        for entry in results:
            assert {"name", "value", "source", "line", "has_secret_pattern"} <= entry.keys()

    def test_dockerfile_env_instructions_extracted(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(DOCKERFILE_SRC, "Dockerfile"))

        results = client.post("/v1/tools/extract_env_variables", json={
            "pipeline_id": "pipe", "file_path": "Dockerfile",
        }).json()["result"]

        names = {e["name"] for e in results}
        # Dockerfile has ENV DD_DEBUG=False and ENV DD_SECRET_KEY=changeme
        assert "DD_DEBUG" in names or "DD_SECRET_KEY" in names


# ── Integration: extract_config_block ────────────────────────────────────────

class TestExtractConfigBlock:
    def test_extracts_env_instruction_from_dockerfile(self, client, monkeypatch):
        """Line 6 of Dockerfile is: ENV DD_DEBUG=False"""
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(DOCKERFILE_SRC, "Dockerfile"))

        resp = client.post("/v1/tools/extract_config_block", json={
            "pipeline_id": "pipe", "file_path": "Dockerfile", "line_number": 6,
        })

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert isinstance(result, dict)
        assert {"block_text", "block_type", "key_path", "start_line", "end_line", "language"} <= result.keys()
        assert "DD_DEBUG" in result["block_text"]

    def test_line_range_covers_requested_line(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_read_source",
                            _stub_read_source(DOCKERFILE_SRC, "Dockerfile"))

        result = client.post("/v1/tools/extract_config_block", json={
            "pipeline_id": "pipe", "file_path": "Dockerfile", "line_number": 6,
        }).json()["result"]

        assert result["start_line"] <= 6 <= result["end_line"]
        assert isinstance(result["start_line"], int)
        assert isinstance(result["end_line"], int)


# ── Integration: find_config_overrides ───────────────────────────────────────

class TestFindConfigOverrides:
    def test_dd_debug_found_in_other_files(self, client, monkeypatch):
        """.env.dev has DD_DEBUG=True; .env.prod and docker-compose.yml also define it."""
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_config_overrides", json={
            "pipeline_id": "pipe",
            "file_path": ".env.dev",
            "key_or_variable": "DD_DEBUG",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert isinstance(results, list)
        assert len(results) >= 1
        for r in results:
            assert {"file", "line", "value", "environment"} <= r.keys()

    def test_origin_file_excluded_from_results(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        results = client.post("/v1/tools/find_config_overrides", json={
            "pipeline_id": "pipe",
            "file_path": ".env.dev",
            "key_or_variable": "DD_DEBUG",
        }).json()["result"]

        assert not any(".env.dev" in r["file"] for r in results)

    def test_nonexistent_key_returns_empty_list(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        results = client.post("/v1/tools/find_config_overrides", json={
            "pipeline_id": "pipe",
            "file_path": ".env.dev",
            "key_or_variable": "TOTALLY_NONEXISTENT_XYZ_999",
        }).json()["result"]

        assert results == []


# ── Integration: find_related_configs ────────────────────────────────────────

class TestFindRelatedConfigs:
    def test_dockerfile_related_to_docker_compose(self, client, monkeypatch):
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_related_configs", json={
            "pipeline_id": "pipe", "file_path": "Dockerfile",
        })

        assert resp.status_code == 200
        results = resp.json()["result"]
        assert isinstance(results, list)
        assert len(results) >= 1
        assert any("docker-compose" in r["file"] for r in results)
        for r in results:
            assert {"file", "relationship"} <= r.keys()

    def test_related_configs_returns_list(self, client, monkeypatch):
        """Any config file query returns a list, even if no relations found."""
        monkeypatch.setattr(mcp_server, "_resolve_source_dir",
                            _stub_resolve_source_dir(SAMPLE))

        resp = client.post("/v1/tools/find_related_configs", json={
            "pipeline_id": "pipe", "file_path": "config/pyproject.toml",
        })

        assert resp.status_code == 200
        assert isinstance(resp.json()["result"], list)
