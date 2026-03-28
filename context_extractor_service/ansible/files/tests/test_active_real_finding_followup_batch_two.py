import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.config_analysis import (
    classify_environment,
    extract_config_block,
    extract_env_variables,
    find_related_configs,
)


def _write_source_tree(root: Path, file_path: str, source: str) -> None:
    full = root / file_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(source, encoding="utf-8")


def _pad_to_line(line_number: int, source: str) -> str:
    if line_number <= 1:
        return source
    return ("\n" * (line_number - 1)) + source


def _pad_source_line_to_target(target_line: int, source_line: int, source: str) -> str:
    if source_line < 1:
        raise ValueError("source_line must be >= 1")
    return _pad_to_line(target_line - source_line + 1, source)


def _exercise_code_flow(
    monkeypatch,
    tmp_path: Path,
    *,
    pipeline_id: str,
    file_path: str,
    line_number: int,
    source: str,
    expected_code_on_line: str,
    trace_symbol: str | None = None,
    symbol_name: str | None = None,
    expected_language: str | None = None,
) -> None:
    _write_source_tree(tmp_path, file_path, source)

    if symbol_name:
        if file_path.endswith(".py"):
            _write_source_tree(tmp_path, "callers.py", f"{symbol_name}()\n")
            _write_source_tree(
                tmp_path,
                "urls.py",
                "from django.urls import path\n"
                f"urlpatterns = [path('real/', {symbol_name})]\n",
            )
        else:
            _write_source_tree(tmp_path, "callers.ts", f"{symbol_name}();\n")
            _write_source_tree(tmp_path, "routes.ts", f"app.get('/real', {symbol_name});\n")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, line_number)
    imports = mcp_server.find_imports(pipeline_id, file_path)
    decorators = mcp_server.find_decorators(pipeline_id, file_path, line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, line_number)

    assert classification["type"] in {"production", "config", "vendored"}
    assert expected_code_on_line.strip() == extracted["meta"]["code_on_line"].strip()
    assert isinstance(imports, list)
    assert isinstance(decorators, list)
    assert isinstance(identifiers["reads"], list)
    assert isinstance(identifiers["writes"], list)

    if expected_language is not None:
        assert identifiers["language"] == expected_language

    if trace_symbol is not None:
        trace = mcp_server.trace_identifier_backward(pipeline_id, file_path, line_number, trace_symbol)
        assert isinstance(trace, list)

    if symbol_name is not None:
        callers = mcp_server.find_callers(pipeline_id, file_path, symbol_name)
        definition = mcp_server.find_definition(pipeline_id, symbol_name)
        route = mcp_server.find_route_to_function(pipeline_id, symbol_name)
        assert isinstance(callers, list)
        assert isinstance(definition, list)
        assert isinstance(route, list)


@pytest.mark.parametrize(
    "file_path",
    [
        "PythonRobot/NoptixLibrary/cloud_portal_api.py",
        "PythonRobot/NoptixLibrary/server_api.py",
        "PythonRobot/pages/downloads_page.py",
    ],
)
def test_active_followup_cloud_portal_stale_pythonrobot_paths_preserve_missing_file_behavior(
    monkeypatch,
    tmp_path,
    file_path,
):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)

    with pytest.raises(FileNotFoundError):
        mcp_server.extract_function("5a36b942", file_path, 3)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_imports("5a36b942", file_path)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_decorators("5a36b942", file_path, 3)

    with pytest.raises(FileNotFoundError):
        mcp_server.find_identifiers("5a36b942", file_path, 3)

    assert classification["type"] == "production"


@pytest.mark.parametrize(
    (
        "file_path",
        "line_number",
        "source",
        "expected_code_on_line",
        "trace_symbol",
        "symbol_name",
    ),
    [
        (
            "channel_partners/src/partners/services/cache_service.py",
            4,
            "import hashlib\n\n"
            "def real_finding_case(script):\n"
            "    sha1 = hashlib.sha1(script.encode()).hexdigest()\n"
            "    return sha1\n",
            "    sha1 = hashlib.sha1(script.encode()).hexdigest()",
            "script",
            "real_finding_case",
        ),
        (
            "channel_partners/src/partners/services/caching/redis_versions.py",
            2,
            "_LUA_INCR_SINGLE = 'return 1'\n"
            "_SHA_INCR_SINGLE = hashlib.sha1(_LUA_INCR_SINGLE.encode()).hexdigest()\n",
            "_SHA_INCR_SINGLE = hashlib.sha1(_LUA_INCR_SINGLE.encode()).hexdigest()",
            "_LUA_INCR_SINGLE",
            "_SHA_INCR_SINGLE",
        ),
        (
            "common/python/nx_jwt/jwt_auth.py",
            4,
            "import hashlib\n\n"
            "def real_finding_case(token_id):\n"
            "    return hashlib.sha1(token_id.encode()).hexdigest()\n",
            "    return hashlib.sha1(token_id.encode()).hexdigest()",
            "token_id",
            "real_finding_case",
        ),
        (
            "channel_partners/src/partners/services/caching/dependent_cache.py",
            4,
            "import hashlib\n\n"
            "def real_finding_case(dependency_strings):\n"
            "    validation_hash = hashlib.md5(str(dependency_strings).encode()).hexdigest()\n"
            "    return validation_hash\n",
            "    validation_hash = hashlib.md5(str(dependency_strings).encode()).hexdigest()",
            "dependency_strings",
            "real_finding_case",
        ),
        (
            "cloud/cloud/controllers/cloud_api.py",
            4,
            "from hashlib import md5\n\n"
            "def real_finding_case(password_string):\n"
            "    password_ha1 = md5(password_string).hexdigest()\n"
            "    return password_ha1\n",
            "    password_ha1 = md5(password_string).hexdigest()",
            "password_string",
            "real_finding_case",
        ),
        (
            "cloud/api/admin.py",
            5,
            "from django.shortcuts import redirect\n"
            "from django.urls import reverse\n\n"
            "def real_finding_case(user_id):\n"
            "    return redirect(reverse('admin:api_account_change', args=[user_id]))\n",
            "    return redirect(reverse('admin:api_account_change', args=[user_id]))",
            "user_id",
            "real_finding_case",
        ),
        (
            "cloud/cloud/middleware.py",
            4,
            "from django.shortcuts import redirect\n\n"
            "def real_finding_case(request):\n"
            "    return redirect(request.path_info + '?e=1')\n",
            "    return redirect(request.path_info + '?e=1')",
            "request",
            "real_finding_case",
        ),
        (
            "cloud/oauth/views.py",
            7,
            "from django.shortcuts import redirect\n\n"
            "def build_redirect_url(redirect_uri, code, state):\n"
            "    return redirect_uri\n\n"
            "def real_finding_case(redirect_uri, res, state):\n"
            "    return redirect(build_redirect_url(redirect_uri, res.get('code'), state))\n",
            "    return redirect(build_redirect_url(redirect_uri, res.get('code'), state))",
            "redirect_uri",
            "real_finding_case",
        ),
        (
            "cloud/api/views/utils.py",
            2,
            "def real_finding_case(response, lang):\n"
            "    response.set_cookie('language', lang, 60 * 60 * 24)\n"
            "    return response\n",
            "    response.set_cookie('language', lang, 60 * 60 * 24)",
            "lang",
            "real_finding_case",
        ),
        (
            "cloud/cloud/helpers/exceptions.py",
            2,
            "def real_finding_case(response, name, value):\n"
            "    response.set_cookie(name, value, httponly=True, secure=True)\n"
            "    return response\n",
            "    response.set_cookie(name, value, httponly=True, secure=True)",
            "value",
            "real_finding_case",
        ),
        (
            "cloud/cms/views/asset.py",
            2,
            "def real_finding_case(response, filename):\n"
            "    response.set_cookie('filename', filename, max_age=10)\n"
            "    return response\n",
            "    response.set_cookie('filename', filename, max_age=10)",
            "filename",
            "real_finding_case",
        ),
        (
            "channel_partners/src/tools/versioning/utils.py",
            4,
            "import importlib\n\n"
            "def real_finding_case(mod_name):\n"
            "    url_mod = importlib.import_module(mod_name)\n"
            "    return url_mod\n",
            "    url_mod = importlib.import_module(mod_name)",
            "mod_name",
            "real_finding_case",
        ),
        (
            "webadmin/replace_static.py",
            2,
            "def real_finding_case(lang_path):\n"
            "    with open(lang_path) as lang_file:\n"
            "        return lang_file.read()\n",
            "    with open(lang_path) as lang_file:",
            "lang_path",
            "real_finding_case",
        ),
        (
            "tools/scripts/setup_system.py",
            2,
            "def real_finding_case(session, host, credentials):\n"
            "    session.post(f\"{host}/rest/v1/login/sessions\", json=credentials)\n",
            "    session.post(f\"{host}/rest/v1/login/sessions\", json=credentials)",
            "credentials",
            "real_finding_case",
        ),
        (
            "tools/scripts/download_deb.py",
            4,
            "import requests\n\n"
            "def real_finding_case(download_url):\n"
            "    res = requests.get(download_url, stream=True)\n"
            "    return res\n",
            "    res = requests.get(download_url, stream=True)",
            "download_url",
            "real_finding_case",
        ),
        (
            "tools/mcp/cloud_system_util.py",
            4,
            "import httpx\n\n"
            "def real_finding_case(self, payload):\n"
            "    res = httpx.post(f\"{self.cloud_host}/cdb/oauth2/token\", json=payload, verify=False)\n"
            "    return res\n",
            "    res = httpx.post(f\"{self.cloud_host}/cdb/oauth2/token\", json=payload, verify=False)",
            "payload",
            "real_finding_case",
        ),
        (
            "tools/packages/internal-tools/src/internal_tools/setup_system.py",
            4,
            "import httpx\n\n"
            "def real_finding_case():\n"
            "    with httpx.Client(verify=False) as client:\n"
            "        return client\n",
            "    with httpx.Client(verify=False) as client:",
            None,
            "real_finding_case",
        ),
        (
            "webadmin/apply_customization.py",
            4,
            "from pathlib import Path\n\n"
            "def real_finding_case(output_package):\n"
            "    Path(str(output_package) + '.zip').replace(output_package)\n",
            "    Path(str(output_package) + '.zip').replace(output_package)",
            "output_package",
            "real_finding_case",
        ),
        (
            "cloud/safety-check.py",
            4,
            "import subprocess\n\n"
            "def real_finding_case(command):\n"
            "    safety_report = subprocess.check_output(command, shell=True)\n"
            "    return safety_report\n",
            "    safety_report = subprocess.check_output(command, shell=True)",
            "command",
            "real_finding_case",
        ),
        (
            "common/python/nx_django_redis/redis_cache.py",
            4,
            "import pickle\n\n"
            "def real_finding_case(obj, protocol):\n"
            "    return pickle.dumps(obj, protocol)\n",
            "    return pickle.dumps(obj, protocol)",
            "obj",
            "real_finding_case",
        ),
        (
            "cloud/cms/models.py",
            2,
            "def real_finding_case(tag, content, global_contexts_dict):\n"
            "    if tag in content:\n"
            "        content = content.replace(tag, global_contexts_dict[tag])\n"
            "    return content\n",
            "    if tag in content:",
            "tag",
            "real_finding_case",
        ),
        (
            "cloud/cms/admin.py",
            3,
            "class AssetManager:\n"
            "    def real_finding_case(self, asset_id):\n"
            "        asset = Asset.objects.get(id=asset_id)\n"
            "        return asset\n",
            "        asset = Asset.objects.get(id=asset_id)",
            "asset_id",
            "real_finding_case",
        ),
        (
            "channel_partners/src/channel_partners/settings.py",
            3,
            "def real_finding_case():\n"
            "    versions = {\n"
            "        'DEFAULT_VERSION': 'v2',\n"
            "    }\n"
            "    return versions['DEFAULT_VERSION']\n",
            "        'DEFAULT_VERSION': 'v2',",
            None,
            "real_finding_case",
        ),
        (
            "channel_partners/src/partners/utils/db.py",
            2,
            "class Interval:\n"
            "    function = 'INTERVAL'\n",
            "    function = 'INTERVAL'",
            None,
            "Interval",
        ),
        (
            "cloud/notifications/admin.py",
            4,
            "from django.utils.html import format_html\n\n"
            "def real_finding_case(timezone, converted_time):\n"
            "    return format_html(f'<span title=\"{timezone}\">{converted_time}</span>')\n",
            "    return format_html(f'<span title=\"{timezone}\">{converted_time}</span>')",
            "timezone",
            "real_finding_case",
        ),
        (
            "cloud/notifications/forms.py",
            2,
            "def real_finding_case(asset_customizations):\n"
            "    if len(asset_customizations.all()) > 0:\n"
            "        return True\n"
            "    return False\n",
            "    if len(asset_customizations.all()) > 0:",
            "asset_customizations",
            "real_finding_case",
        ),
        (
            "cloud/notifications/views/push_notification.py",
            2,
            "def real_finding_case(device):\n"
            "    return device\n",
            "    return device",
            "device",
            "real_finding_case",
        ),
        (
            "channel_partners/src/partners/serializers/v2/serializers.py",
            4,
            "from rest_framework import serializers\n\n"
            "class DeletedEmailsSerializer(serializers.Serializer):\n"
            "    emails = serializers.ListField(child=serializers.EmailField())\n",
            "    emails = serializers.ListField(child=serializers.EmailField())",
            None,
            "DeletedEmailsSerializer",
        ),
    ],
)
def test_active_followup_cloud_portal_python_shapes_keep_code_flow(
    monkeypatch,
    tmp_path,
    file_path,
    line_number,
    source,
    expected_code_on_line,
    trace_symbol,
    symbol_name,
):
    _exercise_code_flow(
        monkeypatch,
        tmp_path,
        pipeline_id="5a36b942",
        file_path=file_path,
        line_number=line_number,
        source=source,
        expected_code_on_line=expected_code_on_line,
        trace_symbol=trace_symbol,
        symbol_name=symbol_name,
        expected_language="python",
    )


@pytest.mark.parametrize(
    (
        "file_path",
        "line_number",
        "source",
        "expected_code_on_line",
        "expected_language",
        "trace_symbol",
        "symbol_name",
    ),
    [
        (
            "help/cms/zoom_search.js",
            2,
            "function realFindingCase(queryForHTML) {\n"
            "  document.write(\"<div class=\\\"searchheading\\\">\" + queryForHTML);\n"
            "}\n",
            "  document.write(\"<div class=\\\"searchheading\\\">\" + queryForHTML);",
            "javascript",
            "queryForHTML",
            "realFindingCase",
        ),
        (
            "cloud/cms/static/js/assetImportConflicts.js",
            2,
            "function realFindingCase(conflictWrapper) {\n"
            "  conflictWrapper.innerHTML = window.conflictsHeader;\n"
            "}\n",
            "  conflictWrapper.innerHTML = window.conflictsHeader;",
            "javascript",
            "conflictWrapper",
            "realFindingCase",
        ),
        (
            "tools/extension/scripts/popup.js",
            2,
            "function realFindingCase(host, relayHost) {\n"
            "  host.innerHTML = relayHost;\n"
            "}\n",
            "  host.innerHTML = relayHost;",
            "javascript",
            "relayHost",
            "realFindingCase",
        ),
        (
            "open/examples/webrtc-stream-manager-example/src/main.ts",
            2,
            "function realFindingCase(systemSelect: { innerHTML: string }, systemOptions: string[]) {\n"
            "  systemSelect.innerHTML = systemOptions.join('');\n"
            "}\n",
            "  systemSelect.innerHTML = systemOptions.join('');",
            "typescript",
            "systemOptions",
            "realFindingCase",
        ),
        (
            "front_end/common/_mocks/getSettings.mock.ts",
            2,
            "export const settings = {\n"
            "  apiKey: 'AIzaSyA8bA6jCS4GnzmfGEg_I6mQyG5JIBKFrLI',\n"
            "};\n",
            "  apiKey: 'AIzaSyA8bA6jCS4GnzmfGEg_I6mQyG5JIBKFrLI',",
            "typescript",
            None,
            "settings",
        ),
        (
            "front_end/libs/services/layout-state/store/shared/utils.ts",
            2,
            "function realFindingCase(layout, id) {\n"
            "  md5(stringify({ ...layout, id: dirtyId(id) }));\n"
            "}\n",
            "  md5(stringify({ ...layout, id: dirtyId(id) }));",
            "typescript",
            "layout",
            "realFindingCase",
        ),
        (
            "front_end/libs/components/console-table/console-table.component.types.ts",
            2,
            "export function realFindingCase(value: string) {\n"
            "  return md5(value);\n"
            "}\n",
            "  return md5(value);",
            "typescript",
            "value",
            "realFindingCase",
        ),
    ],
)
def test_active_followup_cloud_portal_frontend_shapes_keep_code_flow(
    monkeypatch,
    tmp_path,
    file_path,
    line_number,
    source,
    expected_code_on_line,
    expected_language,
    trace_symbol,
    symbol_name,
):
    _exercise_code_flow(
        monkeypatch,
        tmp_path,
        pipeline_id="5a36b942",
        file_path=file_path,
        line_number=line_number,
        source=source,
        expected_code_on_line=expected_code_on_line,
        trace_symbol=trace_symbol,
        symbol_name=symbol_name,
        expected_language=expected_language,
    )


@pytest.mark.parametrize(
    ("file_path", "source", "expected_type", "raises_extract"),
    [
        ("cloud/cms/asset_structure_template.html.mustache", "<td>{{{description}}}</td>\n", "production", False),
        (
            "cloud/notifications/static/templates/cloud_notification.mustache.html",
            "<div class=\"cloud-notification\">{{{message.html_body}}}</div>\n",
            "production",
            True,
        ),
        (
            "cloud/django_templates/cms/context_change_form.html",
            "{% autoescape off %}{{ original.description }}{% endautoescape %}\n",
            "production",
            True,
        ),
        ("cloud/django_templates/api/invite_form.html", "<form method=\"post\">{% csrf_token %}</form>\n", "production", True),
    ],
)
def test_active_followup_cloud_portal_markup_paths_preserve_current_html_extract_exception(
    monkeypatch,
    tmp_path,
    file_path,
    source,
    expected_type,
    raises_extract,
):
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)

    if raises_extract:
        with pytest.raises(KeyError):
            mcp_server.extract_function("5a36b942", file_path, 1)
    else:
        extracted = mcp_server.extract_function("5a36b942", file_path, 1)
        assert extracted["text"] == "// Unsupported file extension: .mustache"
        assert "code_on_line" not in extracted["meta"]

    assert classification["type"] == expected_type


def test_active_followup_cloud_portal_gitlab_private_key_block_keeps_config_flow(tmp_path):
    file_path = "channel_partners/.gitlab-ci.yml"
    source = """\
deploy:
  variables:
    SSH_PRIVATE_KEY: |
      -----BEGIN RSA PRIVATE KEY-----
      MIICXAIBAAKBgQC7
"""
    _write_source_tree(tmp_path, file_path, source)

    classification = mcp_server.classify_file("5a36b942", file_path)
    environment = classify_environment(file_path)
    block = extract_config_block(source, Path(file_path), 3)
    env_vars = extract_env_variables(source, Path(file_path))
    related = find_related_configs(tmp_path, file_path)

    assert classification["type"] == "config"
    assert environment["environment"] == "unknown"
    assert block["key_path"] == "deploy.variables.SSH_PRIVATE_KEY"
    assert "BEGIN RSA PRIVATE KEY" in block["block_text"]
    assert env_vars == []
    assert related == []


def test_active_followup_authorization_sso_import_line_keeps_exact_typescript_import_context(
    monkeypatch,
    tmp_path,
):
    """
    Audit trail:
    - live source line 19: `import { formControlValueSignal } from '@utils/nx';`
    - fixture line 19: `import { formControlValueSignal } from '@utils/nx';`
    - tool under test: extract_function / find_identifiers
    """
    file_path = (
        "front_end/apps/authorization-sso/src/app/screens/login-path/"
        "enter-password-or-org-name/enter-password-or-org-name.component.ts"
    )
    source = """\
import {
    ChangeDetectionStrategy,
    Component,
    computed,
    effect,
    inject,
    signal,
} from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';
import { NxInputFieldModule } from '@components/forms/input/input-field.module';
import { NxValidators } from '@components/forms/validators';
import {
    NxInitialFocusDirective,
    NxInitialFocusParentDirective,
} from '@directives/nx-initial-focus.directive';

import { formControlValueSignal } from '@utils/nx';
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 19)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 19)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 19)

    assert classification["type"] == "production"
    assert extracted["text"] == "// Function not found."
    assert extracted["meta"]["code_on_line"] == "import { formControlValueSignal } from '@utils/nx';"
    assert imports[-1] == "import { formControlValueSignal } from '@utils/nx';"
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}


@pytest.mark.parametrize(
    (
        "file_path",
        "line_number",
        "source_line",
        "source",
        "expected_code_on_line",
        "expected_writes",
    ),
    [
        (
            "common/python/nx_cloud_api_client/base_auth.py",
            25,
            2,
            'username = "username"\npassword = "password"\n',
            'password = "password"',
            ["password"],
        ),
        (
            "cloud/cloud/controllers/cloud_api.py",
            250,
            2,
            'username = "username"\npassword = "password"\n',
            'password = "password"',
            ["password"],
        ),
        (
            "cloud/cloud/helpers/exceptions.py",
            41,
            1,
            "wrong_old_password = 'wrongOldPassword'\nwrong_password = 'wrongPassword'\n",
            "wrong_old_password = 'wrongOldPassword'",
            ["wrong_old_password"],
        ),
        (
            "cloud/cloud/helpers/exceptions.py",
            42,
            2,
            "wrong_old_password = 'wrongOldPassword'\nwrong_password = 'wrongPassword'\n",
            "wrong_password = 'wrongPassword'",
            ["wrong_password"],
        ),
        (
            "cloud/oauth/views.py",
            87,
            3,
            "successful_introspect_response = {\n"
            "    'active': True,\n"
            "    'time_since_password': '11',\n"
            "}\n",
            "    'time_since_password': '11',",
            ["successful_introspect_response"],
        ),
    ],
)
def test_active_followup_python_literal_lines_keep_current_line_local_context(
    monkeypatch,
    tmp_path,
    file_path,
    line_number,
    source_line,
    source,
    expected_code_on_line,
    expected_writes,
):
    """
    Audit trail is carried in the parametrized cases above by keeping the live source text
    and fixture target line aligned for each finding family.
    """
    _write_source_tree(tmp_path, file_path, _pad_source_line_to_target(line_number, source_line, source))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, line_number)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, line_number)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, line_number)

    assert classification["type"] == "production"
    assert extracted["text"] == "// Function not found."
    assert extracted["meta"]["code_on_line"].strip() == expected_code_on_line.strip()
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["writes"] == expected_writes
    assert identifiers["language"] == "python"


@pytest.mark.parametrize(
    ("file_path", "line_number", "source"),
    [
        ("front_end/ssl_keys/server-old.crt", 1, "-----BEGIN CERTIFICATE-----\nMIIB\n"),
        ("front_end/ssl_keys/server.crt", 1, "-----BEGIN CERTIFICATE-----\nMIIC\n"),
    ],
)
def test_active_followup_certificate_assets_should_raise_unsupported_extension_errors(
    monkeypatch,
    tmp_path,
    file_path,
    line_number,
    source,
):
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, line_number)

    assert classification["type"] == "production"
    assert extracted["text"] == "// Unsupported file extension: .crt"

    with pytest.raises(ValueError, match=r"Unsupported file extension: \.crt"):
        mcp_server.find_imports("5a36b942", file_path)

    with pytest.raises(ValueError, match=r"Unsupported file extension: \.crt"):
        mcp_server.find_decorators("5a36b942", file_path, line_number)

    with pytest.raises(ValueError, match=r"Unsupported file extension: \.crt"):
        mcp_server.find_identifiers("5a36b942", file_path, line_number)


def test_active_followup_api_docstring_line_should_keep_exact_schema_line_text(
    monkeypatch,
    tmp_path,
):
    file_path = "common/python/nx_cloud_api_client/apis.py"
    source = """\
def fetch_security_settings():
    \"\"\"
    200,
    {
        \"httpDigestAuthEnabled\": true,
        \"account2faEnabled\": true,
        \"mfaCode\": \"string\",
        \"password\": \"string\",
        \"totpExistsForAccount\": true,
        \"authSessionLifetime\": \"string\"
    }
    \"\"\"
    return None
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    extracted = mcp_server.extract_function("5a36b942", file_path, 8)

    assert extracted["meta"]["code_on_line"] == '        "password": "string",'


@pytest.mark.parametrize(
    ("file_path", "line_number", "source_line"),
    [
        ("cloud/cms/structures/cloud_structure.json", 892, '  "apiKey": "AIzaSyA8bA6jCS4GnzmfGEg_I6mQyG5JIBKFrLI",'),
        ("package-license.json", 12480, '  "url": "https://www.linkedin.com/in/vladimirgorej/",'),
    ],
)
def test_active_followup_json_assets_should_raise_parse_errors_instead_of_raw_keyerrors(
    monkeypatch,
    tmp_path,
    file_path,
    line_number,
    source_line,
):
    prefix_lines = ["{"] + ['  "pad": 0,' for _ in range(line_number - 2)]
    source = "\n".join(prefix_lines + [source_line, "}"]) + "\n"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    assert classification["type"] == "production"

    extracted = mcp_server.extract_function("5a36b942", file_path, line_number)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, line_number)

    assert extracted["meta"]["code_on_line"].strip() == source_line.strip()
    assert identifiers["language"] == "json"

    with pytest.raises(ValueError, match=r"Failed to parse file: .*\.json"):
        mcp_server.find_imports("5a36b942", file_path)

    with pytest.raises(ValueError, match=r"Failed to parse file: .*\.json"):
        mcp_server.find_decorators("5a36b942", file_path, line_number)


def test_active_followup_cloud_helper_bash_finding_should_not_raise_raw_language_keyerror(
    monkeypatch,
    tmp_path,
):
    """
    Audit trail:
    - live source line 7: `fi`
    - fixture line 7: `fi`
    - tool under test: extract_function / find_identifiers

    The real finding 71010 reports line 7. The scanner's semantic target is likely the
    preceding shell literal on line 6, but the current MCP failure reproduces on the
    recorded line 7 as well because bash files fail before line-local analysis begins.
    """
    file_path = "cloud_helper.sh"
    source = """\
#!/usr/bin/env bash

source ./tools/cloud_helper/manage_volumes.sh
if [[ ! -f etc/.local_env ]]; then
    echo "Creating .local_env file in etc directory"
    echo 'PY_PKG_MANAGER="poetry"' > etc/.local_env
fi
source etc/.local_env

if [[ $PY_PKG_MANAGER != "poetry" && $PY_PKG_MANAGER != "uv" ]]; then
    echo "Unsupported python package manager: PY_PKG_MANAGER=$PY_PKG_MANAGER."
    echo "Supported values are 'poetry' and 'uv', must be set in etc/.local_env file."
    exit 1
fi
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 7)

    assert classification["type"] == "production"
    assert imports == []
    assert decorators == []

    extracted = mcp_server.extract_function("5a36b942", file_path, 7)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 7)

    assert extracted["meta"]["code_on_line"] == "fi"
    assert identifiers["language"] == "bash"
