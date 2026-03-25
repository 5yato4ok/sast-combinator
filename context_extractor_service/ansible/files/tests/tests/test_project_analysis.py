"""Tests for context_extractor.project_analysis tools."""
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from context_extractor.project_analysis import (
    classify_file,
    find_callers,
    find_decorators,
    find_definition,
    find_imports,
    find_route_to_function,
    get_file_structure,
    trace_identifier_backward,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sample_project"


# ── classify_file ────────────────────────────────────────────────

class TestClassifyFile:

    def test_test_file_by_directory(self):
        result = classify_file("tests/test_auth.py")
        assert result["type"] == "test"

    def test_test_file_by_name(self):
        result = classify_file("src/test_utils.py")
        assert result["type"] == "test"

    def test_migration_file(self):
        result = classify_file("app/migrations/0001_initial.py")
        assert result["type"] == "migration"

    def test_vendored_file(self):
        result = classify_file("vendor/django/core/base.py")
        assert result["type"] == "vendored"

    def test_config_file(self):
        result = classify_file("settings.py")
        assert result["type"] == "config"

    def test_production_file(self):
        result = classify_file("src/auth/views.py")
        assert result["type"] == "production"

    def test_generated_file(self):
        result = classify_file("generated/api_client.py")
        assert result["type"] == "generated"

    def test_node_modules(self):
        result = classify_file("node_modules/express/index.js")
        assert result["type"] == "vendored"

    def test_spec_file(self):
        result = classify_file("src/auth/views.spec.js")
        assert result["type"] == "test"


# ── find_imports ─────────────────────────────────────────────────

class TestFindImports:

    def test_python_imports(self):
        result = find_imports(FIXTURES, "src/auth/views.py")
        texts = "\n".join(result)
        assert "django.db" in texts
        assert "bleach" in texts

    def test_javascript_imports(self):
        result = find_imports(FIXTURES, "src/auth/utils.js")
        texts = "\n".join(result)
        assert "express" in texts or "sanitize-html" in texts

    def test_java_imports(self):
        result = find_imports(FIXTURES, "src/auth/Handler.java")
        texts = "\n".join(result)
        assert "java.sql" in texts

    def test_typescript_imports(self):
        result = find_imports(FIXTURES, "src/auth/service.ts")
        texts = "\n".join(result)
        assert "@angular/core" in texts
        assert "sanitize-html" in texts

    def test_go_imports(self):
        result = find_imports(FIXTURES, "src/auth/handler.go")
        texts = "\n".join(result)
        assert "database/sql" in texts
        assert "net/http" in texts

    def test_csharp_using_directives(self):
        result = find_imports(FIXTURES, "src/auth/AuthController.cs")
        texts = "\n".join(result)
        assert "SqlClient" in texts or "System.Data" in texts
        assert "AspNetCore" in texts or "Mvc" in texts


# ── find_decorators ──────────────────────────────────────────────

class TestFindDecorators:

    def test_python_decorators(self):
        source = (FIXTURES / "src/auth/views.py").read_text()
        filepath = FIXTURES / "src/auth/views.py"
        # line 14 is inside search_users which has @login_required and @csrf_exempt
        result = find_decorators(source, filepath, 14)
        texts = "\n".join(result)
        assert "login_required" in texts
        assert "csrf_exempt" in texts

    def test_no_decorators(self):
        source = (FIXTURES / "src/auth/views.py").read_text()
        filepath = FIXTURES / "src/auth/views.py"
        # get_user_by_id has no decorators
        result = find_decorators(source, filepath, 20)
        assert len(result) == 0

    def test_regex_fallback_for_decorators(self):
        # Verify regex fallback works for unsupported file types
        source = "@login_required\n@csrf_exempt\ndef my_view(request):\n    pass\n"
        filepath = Path("unknown_extension.xyz")  # no grammar → regex path
        result = find_decorators(source, filepath, 3)
        assert len(result) == 2
        assert "@login_required" in result
        assert "@csrf_exempt" in result

    def test_csharp_http_attribute(self):
        source = (FIXTURES / "src/auth/AuthController.cs").read_text()
        filepath = FIXTURES / "src/auth/AuthController.cs"
        # Line 11 is inside GetUser body — decorator [HttpGet("user")] is at line 8
        result = find_decorators(source, filepath, 11)
        texts = "\n".join(result)
        assert "HttpGet" in texts


# ── find_callers ─────────────────────────────────────────────────

class TestFindCallers:

    def test_find_callers_across_project(self):
        # validateInput is called inside utils.js by processQuery
        results = find_callers(FIXTURES, "src/auth/utils.js", "validateInput")
        assert len(results) >= 1
        # Should find the call in processQuery, not the definition
        assert any("utils.js" in r["file"] for r in results)

    def test_find_callers_internal_helper(self):
        results = find_callers(FIXTURES, "src/auth/views.py", "internal_helper")
        # internal_helper is not called anywhere in fixtures
        assert len(results) == 0

    def test_find_callers_no_results_for_unused(self):
        results = find_callers(FIXTURES, "src/auth/views.py", "nonexistent_function_xyz")
        assert len(results) == 0


# ── trace_identifier_backward ────────────────────────────────────

class TestTraceIdentifierBackward:

    def test_trace_query_in_python(self):
        source = (FIXTURES / "src/auth/views.py").read_text()
        filepath = FIXTURES / "src/auth/views.py"
        # Line 14: cursor.execute(f"SELECT ... '{sanitized}'")
        # Trace "sanitized" backward → should find sanitized = bleach.clean(query)
        chain = trace_identifier_backward(source, filepath, 14, "sanitized")
        assert len(chain) >= 1
        assert any("bleach" in step["code"] for step in chain)

    def test_trace_user_id(self):
        source = (FIXTURES / "src/auth/views.py").read_text()
        filepath = FIXTURES / "src/auth/views.py"
        # Line 22: cursor.execute("SELECT ... id = %s", [user_id])
        # Trace "user_id" backward → should find user_id = int(request.GET.get("id"))
        chain = trace_identifier_backward(source, filepath, 22, "user_id")
        assert len(chain) >= 1
        assert any("int(" in step["code"] or "request" in step["code"] for step in chain)

    def test_trace_go_query(self):
        source = (FIXTURES / "src/auth/handler.go").read_text()
        filepath = FIXTURES / "src/auth/handler.go"
        # Line 20: rows, _ := h.db.Query(query)
        # Trace "query" backward → should find query := fmt.Sprintf(...)
        chain = trace_identifier_backward(source, filepath, 20, "query")
        assert len(chain) >= 1
        assert any("Sprintf" in step["code"] or "query" in step["code"] for step in chain)


# ── get_file_structure ───────────────────────────────────────────

class TestGetFileStructure:

    def test_python_structure(self):
        source = (FIXTURES / "src/auth/views.py").read_text()
        filepath = FIXTURES / "src/auth/views.py"
        result = get_file_structure(source, filepath)
        assert result["language"] == "python"
        func_names = [f["name"] for f in result["functions"]]
        assert "search_users" in func_names
        assert "get_user_by_id" in func_names
        assert "internal_helper" in func_names

    def test_java_structure(self):
        source = (FIXTURES / "src/auth/Handler.java").read_text()
        filepath = FIXTURES / "src/auth/Handler.java"
        result = get_file_structure(source, filepath)
        assert result["language"] == "java"
        assert len(result["classes"]) >= 1
        cls = result["classes"][0]
        assert cls["name"] == "Handler"
        method_names = [m["name"] for m in cls["methods"]]
        assert "login" in method_names

    def test_go_structure(self):
        source = (FIXTURES / "src/auth/handler.go").read_text()
        filepath = FIXTURES / "src/auth/handler.go"
        result = get_file_structure(source, filepath)
        assert result["language"] == "go"
        func_names = [f["name"] for f in result["functions"]]
        # function_declarations (not method_declarations) have clear identifier names
        assert "NewAuthHandler" in func_names
        assert "sanitizeInput" in func_names

    def test_csharp_structure(self):
        source = (FIXTURES / "src/auth/AuthController.cs").read_text()
        filepath = FIXTURES / "src/auth/AuthController.cs"
        result = get_file_structure(source, filepath)
        assert result["language"] == "csharp"
        assert len(result["classes"]) >= 1
        cls = result["classes"][0]
        assert cls["name"] == "AuthController"
        method_names = [m["name"] for m in cls["methods"]]
        assert "GetUser" in method_names


# ── find_definition ──────────────────────────────────────────────

class TestFindDefinition:

    def test_find_function_definition(self):
        results = find_definition(FIXTURES, "search_users")
        assert len(results) >= 1
        assert results[0]["kind"] == "function"
        assert "views.py" in results[0]["file"]

    def test_find_class_definition(self):
        results = find_definition(FIXTURES, "Handler")
        assert len(results) >= 1
        assert results[0]["kind"] == "class"

    def test_find_nonexistent(self):
        results = find_definition(FIXTURES, "nonexistent_symbol_xyz")
        assert len(results) == 0

    def test_go_function_definition(self):
        results = find_definition(FIXTURES, "NewAuthHandler")
        assert len(results) >= 1
        assert any("handler.go" in r["file"] for r in results)
        assert results[0]["kind"] == "function"

    def test_ruby_method_definition(self):
        results = find_definition(FIXTURES, "handle_login")
        assert len(results) >= 1
        assert any("controller.rb" in r["file"] for r in results)


# ── find_route_to_function ───────────────────────────────────────

class TestFindRouteToFunction:

    def test_django_route(self):
        results = find_route_to_function(FIXTURES, "search_users")
        assert len(results) >= 1
        assert any("urls.py" in r["file"] for r in results)

    def test_no_route(self):
        results = find_route_to_function(FIXTURES, "internal_helper")
        assert len(results) == 0

    def test_spring_route(self):
        # Handler.java has @RequestMapping("/api/login") on the login method
        results = find_route_to_function(FIXTURES, "login")
        assert len(results) >= 1
        assert any("Handler.java" in r["file"] for r in results)
        assert any("/api/login" in r.get("pattern", "") for r in results)
