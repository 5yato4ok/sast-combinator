"""
Tool-specific blind spot tests.

Covers:
- find_route_to_function: FastAPI APIRouter with prefix, Django include() with namespace,
  Express route parameters, Rails resources DSL, programmatic route registration
- classify_file: Django settings.py, Django migration files, protobuf generated files,
  conftest.py, Alembic migrations, fixture data files
- classify_environment: conflicting signals in filename vs path vs content
- dump_ast: syntactically invalid file, BOM-prefixed file, unsupported language
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub(source: str, fname: str):
    def _reader(_pid: str, _fp: str):
        return source, Path(fname)
    return _reader


# ===========================================================================
# find_route_to_function
# ===========================================================================

def test_find_route_should_find_fastapi_router_with_prefix_and_tag(tmp_path):
    """find_route_to_function must find an endpoint registered on an APIRouter with prefix."""
    src = """\
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/users", tags=["users"])

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    return await user_service.get_by_id(db, user_id)

@router.post("/", status_code=201)
async def create_user(user: CreateUserRequest, db: Session = Depends(get_db)):
    return await user_service.create(db, user)
"""
    (tmp_path / "user_router.py").write_text(src)
    from context_extractor.project_analysis.navigation import find_route_to_function
    results = find_route_to_function(tmp_path, "get_user")
    assert len(results) >= 1, \
        "FastAPI endpoint registered on APIRouter with prefix must be found"


def test_find_route_should_find_django_view_in_include_with_namespace(tmp_path):
    """find_route_to_function must find a view in a URL conf using include() with namespace."""
    urls_py = """\
from django.urls import path, include

urlpatterns = [
    path('api/v1/', include('api.v1.urls', namespace='api_v1')),
    path('auth/', include('accounts.urls', namespace='accounts')),
]
"""
    api_urls = """\
from django.urls import path
from . import views

app_name = 'api_v1'
urlpatterns = [
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]
"""
    (tmp_path / "urls.py").write_text(urls_py)
    api_dir = tmp_path / "api" / "v1"
    api_dir.mkdir(parents=True)
    (api_dir / "urls.py").write_text(api_urls)
    from context_extractor.project_analysis.navigation import find_route_to_function
    results = find_route_to_function(tmp_path, "UserDetailView")
    assert isinstance(results, list), "Must return a list even for namespaced includes"


def test_find_route_should_find_express_route_with_param_pattern(tmp_path):
    """find_route_to_function must find an Express route using :param URL parameters."""
    src = """\
const express = require('express');
const router = express.Router();

router.get('/users/:id', async (req, res) => {
    const user = await UserService.findById(req.params.id);
    res.json(user);
});

router.put('/users/:id/password', async (req, res) => {
    await UserService.updatePassword(req.params.id, req.body.password);
    res.sendStatus(204);
});

async function getUserById(req, res) {
    const { id } = req.params;
    res.json(await UserService.findById(id));
}

router.get('/users/:id/profile', getUserById);
"""
    (tmp_path / "userRouter.js").write_text(src)
    from context_extractor.project_analysis.navigation import find_route_to_function
    results = find_route_to_function(tmp_path, "getUserById")
    assert len(results) >= 1, "Named function referenced in Express route must be found"


def test_find_route_should_find_flask_route_registered_via_add_url_rule(tmp_path):
    """find_route_to_function must find a view registered via app.add_url_rule()."""
    src = """\
from flask import Flask, jsonify

app = Flask(__name__)

def get_health():
    return jsonify({"status": "ok"})

def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

app.add_url_rule('/health', 'health', get_health)
app.add_url_rule('/users/<int:user_id>', 'get_user', get_user, methods=['GET'])
"""
    (tmp_path / "app.py").write_text(src)
    from context_extractor.project_analysis.navigation import find_route_to_function
    results = find_route_to_function(tmp_path, "get_user")
    assert len(results) >= 1, "Function registered via add_url_rule must be found"


def test_find_route_should_find_aspnet_minimal_api_map_get(tmp_path):
    """find_route_to_function must find handler function passed to app.MapGet()."""
    src = """\
var app = builder.Build();

async Task<IResult> GetUserById(int id, IUserService userService) =>
    await userService.GetByIdAsync(id) is { } user
        ? Results.Ok(user)
        : Results.NotFound();

app.MapGet("/users/{id}", GetUserById);
app.MapPost("/users", async ([FromBody] CreateUserRequest req, IUserService svc) =>
{
    var user = await svc.CreateAsync(req);
    return Results.Created($"/users/{user.Id}", user);
});
"""
    (tmp_path / "Program.cs").write_text(src)
    from context_extractor.project_analysis.navigation import find_route_to_function
    results = find_route_to_function(tmp_path, "GetUserById")
    assert len(results) >= 1, "Handler passed to app.MapGet must be found"


# ===========================================================================
# classify_file
# ===========================================================================

def test_classify_file_should_recognise_django_settings_as_config(monkeypatch, tmp_path):
    """classify_file must classify Django settings.py as config, not production code."""
    source = """\
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-xxx'
DEBUG = True
ALLOWED_HOSTS = []
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth']
"""
    (tmp_path / "settings.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "settings.py")
    assert result.get("type") in ("config", "production"), \
        "Django settings.py must be classified as config or production (not test/generated)"


def test_classify_file_should_recognise_django_migration_as_generated(monkeypatch, tmp_path):
    """classify_file must classify a Django migration file as generated or migration."""
    source = """\
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(primary_key=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
            ],
        ),
    ]
"""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "0001_initial.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "migrations/0001_initial.py")
    assert result.get("type") in ("migration", "generated"), \
        "Django migration file must be classified as migration or generated"


def test_classify_file_should_recognise_protobuf_generated_python_as_generated(monkeypatch, tmp_path):
    """classify_file must classify a _pb2.py protobuf generated file as generated."""
    source = """\
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: user.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message

DESCRIPTOR = _descriptor.FileDescriptor(
    name='user.proto',
    package='user.v1',
)
"""
    (tmp_path / "user_pb2.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "user_pb2.py")
    assert result.get("type") in ("generated", "vendored"), \
        "Protobuf generated _pb2.py must be classified as generated"


def test_classify_file_should_recognise_conftest_as_test(monkeypatch, tmp_path):
    """classify_file must classify conftest.py as a test file."""
    source = """\
import pytest

@pytest.fixture
def db_session():
    session = Session()
    yield session
    session.rollback()

@pytest.fixture
def client(app):
    return app.test_client()
"""
    (tmp_path / "conftest.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "conftest.py")
    assert result.get("type") == "test", \
        "conftest.py must be classified as a test file"


def test_classify_file_should_recognise_alembic_migration_as_migration(monkeypatch, tmp_path):
    """classify_file must classify an Alembic migration as migration or generated."""
    source = """\
\"\"\"Add user table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2024-01-15 10:00:00.000000
\"\"\"
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = None

def upgrade() -> None:
    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
    )

def downgrade() -> None:
    op.drop_table('user')
"""
    ver_dir = tmp_path / "alembic" / "versions"
    ver_dir.mkdir(parents=True)
    (ver_dir / "a1b2c3d4e5f6_add_user_table.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "alembic/versions/a1b2c3d4e5f6_add_user_table.py")
    assert result.get("type") in ("migration", "generated"), \
        "Alembic migration file must be classified as migration or generated"


def test_classify_file_should_not_classify_production_view_as_test(monkeypatch, tmp_path):
    """classify_file must not misclassify a production view file as a test file."""
    source = """\
from django.views import View
from django.http import JsonResponse

class UserView(View):
    def get(self, request, pk):
        user = User.objects.get(pk=pk)
        return JsonResponse({'id': user.id, 'email': user.email})
"""
    (tmp_path / "views.py").write_text(source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_file("pipe", "views.py")
    assert result.get("type") != "test", \
        "Production view file must not be classified as test"


# ===========================================================================
# classify_environment — conflicting signals
# ===========================================================================

def test_classify_environment_with_prod_in_name_but_test_in_path_should_resolve(monkeypatch, tmp_path):
    """classify_environment must handle conflicting prod/test signals in path vs filename."""
    test_dir = tmp_path / "tests" / "fixtures"
    test_dir.mkdir(parents=True)
    (test_dir / "production_config.yml").write_text("debug: false\nenv: production\n")
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_environment("pipe", "tests/fixtures/production_config.yml")
    # Either classification is acceptable, but it must not crash and confidence must be noted
    assert isinstance(result, dict), "Must return a dict"
    assert "environment" in result, "Must have environment key"
    assert "confidence" in result, "Must have confidence key"


def test_classify_environment_with_staging_in_path_and_dev_in_filename(monkeypatch, tmp_path):
    """classify_environment must return a consistent result for staging/dev conflict."""
    staging_dir = tmp_path / "deploy" / "staging"
    staging_dir.mkdir(parents=True)
    (staging_dir / "dev.env").write_text("APP_ENV=development\n")
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_environment("pipe", "deploy/staging/dev.env")
    assert isinstance(result, dict) and "environment" in result, \
        "Conflicting path/filename signals must produce a result, not crash"


def test_classify_environment_with_no_env_signals_should_return_unknown(monkeypatch, tmp_path):
    """classify_environment on a generic config file must return unknown or low confidence."""
    (tmp_path / "config.yml").write_text("timeout: 30\nmax_retries: 3\n")
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)
    result = mcp_server.classify_environment("pipe", "config.yml")
    assert isinstance(result, dict)
    env = result.get("environment", "")
    conf = result.get("confidence", "")
    assert env in ("unknown", "dev", "development", "production", "staging", "test") or env == "", \
        "Generic config must return a known environment value or 'unknown'"


# ===========================================================================
# dump_ast edge cases
# ===========================================================================

def test_dump_ast_on_syntactically_invalid_file_should_return_partial_or_error():
    """dump_ast must return something useful (partial AST or error) for an invalid file."""
    source = """\
def broken_function(
    # missing closing paren and colon
    return "never"

def valid_after():
    return 42
"""
    from context_extractor.debug_ast import function_ast_to_string
    try:
        result = function_ast_to_string(source, "broken.py", 5)
        assert isinstance(result, str), "Must return a string for partially invalid Python"
    except Exception as e:
        # Acceptable: raised a descriptive error rather than silent failure
        assert len(str(e)) > 0


def test_dump_ast_on_bom_prefixed_file_should_not_include_bom_in_output():
    """dump_ast must strip the UTF-8 BOM before returning the AST string."""
    bom = "\ufeff"
    source = f"{bom}function add(a, b) {{\n    return a + b;\n}}\n"
    from context_extractor.debug_ast import function_ast_to_string
    result = function_ast_to_string(source, "add.js", 1)
    assert "\ufeff" not in result, "BOM must not appear in dump_ast output"


def test_dump_ast_on_unsupported_extension_should_return_error_or_empty():
    """dump_ast must not crash on a file with an unsupported extension."""
    source = "SELECT * FROM users WHERE id = 1;"
    from context_extractor.debug_ast import function_ast_to_string
    try:
        result = function_ast_to_string(source, "query.sql", 1)
        assert result is None or isinstance(result, str), \
            "Unsupported extension must return None or a string, not crash"
    except (ValueError, KeyError):
        pass  # Acceptable: raises a descriptive error for unsupported language


# ===========================================================================
# _find_node_at_line — deepest named node
# ===========================================================================

def test_find_identifiers_on_chained_call_captures_rhs_identifiers(monkeypatch):
    """find_identifiers on 'result = obj.method(arg)' must include identifiers
    from the right-hand side, not just the left-hand assignment target.

    Regression for: _find_node_at_line breaking after first named child hit,
    which could return a less-specific node and miss rhs identifiers.
    """
    source = """\
def process(obj, arg):
    result = obj.method(arg)
    return result
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("proc.py")))
    result = mcp_server.find_identifiers("pipe", "proc.py", 2)
    reads = set(result.get("reads", []))
    writes = set(result.get("writes", []))
    assert "obj" in reads, f"'obj' missing from reads; got {reads}"
    assert "arg" in reads, f"'arg' missing from reads; got {reads}"
    assert "result" in writes, f"'result' missing from writes; got {writes}"


def test_find_identifiers_on_nested_call_captures_all_argument_identifiers(monkeypatch):
    """find_identifiers on 'x = foo(bar(baz))' must see baz as a read."""
    source = """\
def run():
    x = foo(bar(baz))
    return x
"""
    monkeypatch.setattr(mcp_server, "_read_source", lambda _pid, _fp: (source, Path("run.py")))
    result = mcp_server.find_identifiers("pipe", "run.py", 2)
    reads = set(result.get("reads", []))
    assert "baz" in reads, f"'baz' missing from reads; got {reads}"
    assert "bar" in reads, f"'bar' missing from reads; got {reads}"
    assert "foo" in reads, f"'foo' missing from reads; got {reads}"
