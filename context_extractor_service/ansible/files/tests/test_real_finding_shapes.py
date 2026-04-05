from pathlib import Path
from tempfile import TemporaryDirectory

from context_extractor.config_analysis import (
    classify_environment,
    extract_config_block,
    extract_env_variables,
    find_config_overrides,
    find_related_configs,
)
from context_extractor.extract import extract_function_from_source
from context_extractor.project_analysis import (
    classify_file,
    find_callers,
    find_definition,
    find_imports,
    find_route_to_function,
    trace_identifier_backward,
)
import mcp_server
from conftest import _stub_read_source


def test_classify_file_real_finding_paths():
    assert classify_file(
        "front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts"
    )["type"] == "test"
    assert classify_file("cloud/cloud/settings.py")["type"] == "config"
    assert classify_file("cloud/ams/deploy/ams_service_crash_receiver/Dockerfile")["type"] == "config"
    assert classify_file("front_end/common/scripts/vendor/firebase-app.js")["type"] == "vendored"
    assert classify_file(".github/chatmodes/modules/context-extractor.js")["type"] == "production"


def test_find_definition_on_exported_typescript_symbols():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(
            "export default function OAuthDebugPage() {\n"
            "  return null;\n"
            "}\n",
        )
        (root / "uri.service.ts").write_text(
            "export class UriService {\n"
            "  changePort(newPort: string): void {\n"
            "    window.location.replace(newPort);\n"
            "  }\n"
            "}\n",
        )

        oauth_defs = find_definition(root, "OAuthDebugPage")
        uri_defs = find_definition(root, "UriService")

    assert oauth_defs and oauth_defs[0]["kind"] == "function"
    assert uri_defs and uri_defs[0]["kind"] == "class"


def test_find_imports_on_tsx_via_regex_fallback():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(
            "import { useEffect, useState } from 'react';\n"
            "import { config } from '@/config';\n"
            "export default function OAuthDebugPage(){ return <div />; }\n",
        )

        imports = find_imports(root, "page.tsx")

    assert len(imports) == 2
    assert "react" in imports[0]
    assert "@/config" in imports[1]


def test_trace_identifier_backward_on_realistic_go_and_ts_shapes():
    go_source = """\
package fetcher

func f(data []byte) {
    hash := md5.Sum(data)
    _ = hash
}
"""
    go_chain = trace_identifier_backward(go_source, Path("site_info_reader.go"), 5, "hash")
    assert go_chain
    assert go_chain[0]["writes"] == ["hash"]
    assert "md5" in go_chain[0]["reads"]
    assert "data" in go_chain[0]["reads"]

    ts_source = """\
export default function OAuthDebugPage() {
    const nextUrl = '/oauth/callback'
    return <a href={nextUrl}>Continue</a>
}
"""
    ts_chain = trace_identifier_backward(ts_source, Path("page.tsx"), 3, "nextUrl")
    assert ts_chain
    assert ts_chain[0]["writes"] == ["nextUrl"]


def test_navigation_flow_on_realistic_django_and_express_shapes():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "urls.py").write_text(
            "from views import login_view\n"
            "path('/login', login_view)\n",
        )
        (root / "views.py").write_text(
            "def login_view(request):\n"
            "    return True\n",
        )

        routes = find_route_to_function(root, "login_view")
        defs = find_definition(root, "login_view")

    assert routes and routes[0]["file"] == "urls.py"
    assert routes[0]["pattern"] == "/login"
    assert defs and defs[0]["file"] == "views.py"
    assert defs[0]["kind"] == "function"

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.js").write_text(
            "app.get('/health', healthCheck)\n"
            "function healthCheck(req, res) { return res }\n",
        )

        routes = find_route_to_function(root, "healthCheck")
        defs = find_definition(root, "healthCheck")

    assert routes and routes[0]["pattern"] == "/health"
    assert defs and defs[0]["file"] == "api.js"


def test_find_callers_on_realistic_typescript_service_usage():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.ts").write_text(
            "export function changePort(newPort: string): void {\n"
            "  return;\n"
            "}\n",
        )
        (root / "page.ts").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n",
        )

        callers = find_callers(root, "service.ts", "changePort")

    assert callers
    assert callers[0]["file"] == "page.ts"
    assert callers[0]["caller_function"] == "run"


def test_config_flow_returns_semantically_correct_context():
    assert classify_environment("deploy/docker-compose.prod.yml")["environment"] == "production"

    compose_source = (
        "services:\n"
        "  web:\n"
        "    image: app\n"
        "    environment:\n"
        "      ADMIN_PASSWORD: ${ADMIN_PASSWORD}\n"
        "      LOG_LEVEL: info\n"
    )
    block = extract_config_block(compose_source, Path("docker-compose.prod.yml"), 5)
    assert block["key_path"] == "services.web.environment.ADMIN_PASSWORD"
    assert block["block_text"] == "ADMIN_PASSWORD: ${ADMIN_PASSWORD}"

    env_vars = extract_env_variables(compose_source, Path("docker-compose.prod.yml"))
    assert env_vars[0] == {
        "name": "ADMIN_PASSWORD",
        "value": "${ADMIN_PASSWORD}",
        "source": "yaml_environment",
        "line": 5,
        "has_secret_pattern": True,
    }
    assert env_vars[1] == {
        "name": "LOG_LEVEL",
        "value": "info",
        "source": "yaml_environment",
        "line": 6,
        "has_secret_pattern": False,
    }

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.11\nCOPY . /app\n")
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == [{"file": "docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_code_flow_returns_semantically_correct_context_for_oauth_page():
    source = """\
export default function OAuthDebugPage() {
    const nextUrl = '/oauth/callback'
    return <a href={nextUrl}>Continue</a>
}
"""

    extracted = extract_function_from_source(source, "page.tsx", 3, 200)
    trace = trace_identifier_backward(source, Path("page.tsx"), 3, "nextUrl")

    assert extracted["meta"]["code_on_line"] == "    return <a href={nextUrl}>Continue</a>"
    assert extracted["meta"]["function_lines"] == (1, 4)
    assert trace == [
        {
            "line": 2,
            "code": "const nextUrl = '/oauth/callback'",
            "writes": ["nextUrl"],
            "reads": [],
        }
    ]


def test_find_identifiers_returns_semantically_correct_reads_and_writes_for_js_assignment(monkeypatch):
    source = """\
function fetch(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https') ? https : require('http');
    protocol.get(url, (res) => {
      return resolve(url);
    });
  });
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))

    result = mcp_server.find_identifiers("pipe", "generate-customization.js", 3)

    assert result == {
        "reads": ["https", "require", "startsWith", "url"],
        "writes": ["protocol"],
        "language": "javascript",
    }


def test_code_flow_returns_semantically_correct_context_for_oauth_handler_redirect(monkeypatch):
    source = """\
export function handleOAuthCodeInUrl(): boolean {
  if (typeof window === 'undefined') return false;
  const code = urlParams.get('code');
  const oauthUrl = `/auth/oauth?code=${encodeURIComponent(code)}&returnUrl=${encodeURIComponent(returnUrl)}`;
  window.location.href = oauthUrl;
  return true;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "oauth-handler.ts"))

    extracted = extract_function_from_source(source, "oauth-handler.ts", 5, 200)
    identifiers = mcp_server.find_identifiers("pipe", "oauth-handler.ts", 5)
    trace = trace_identifier_backward(source, Path("oauth-handler.ts"), 5, "oauthUrl")

    assert extracted["meta"]["code_on_line"] == "  window.location.href = oauthUrl;"
    assert identifiers == {
        "reads": ["location", "oauthUrl", "window"],
        "writes": ["href"],
        "language": "typescript",
    }
    assert trace == [
        {
            "line": 4,
            "code": "const oauthUrl = `/auth/oauth?code=${encodeURIComponent(code)}&returnUrl=${encodeURIComponent(returnUrl)}`;",
            "writes": ["oauthUrl"],
            "reads": ["code", "encodeURIComponent", "returnUrl"],
        },
        {
            "line": 3,
            "code": "const code = urlParams.get('code');",
            "writes": ["code"],
            "reads": ["get", "urlParams"],
        },
    ]


def test_config_flow_handles_dev_template_and_override_semantics():
    assert classify_environment("deploy/docker-compose.override.yml")["environment"] == "dev"
    assert classify_environment(".env.local")["environment"] == "dev"
    assert classify_environment("config/.env.example")["environment"] == "template"

    compose_source = (
        "services:\n"
        "  worker:\n"
        "    privileged: true\n"
        "    environment:\n"
        "      DB_PASSWORD: ''\n"
        "      API_TOKEN: ${API_TOKEN}\n"
    )
    block = extract_config_block(compose_source, Path("docker-compose.dev.yml"), 3)
    assert block == {
        "block_text": "privileged: true",
        "block_type": "block_mapping_pair",
        "key_path": "services.worker.privileged",
        "start_line": 3,
        "end_line": 3,
        "language": "yaml",
    }

    env_vars = extract_env_variables(compose_source, Path("docker-compose.dev.yml"))
    assert env_vars == [
        {
            "name": "DB_PASSWORD",
            "value": "",
            "source": "yaml_environment",
            "line": 5,
            "has_secret_pattern": True,
        },
        {
            "name": "API_TOKEN",
            "value": "${API_TOKEN}",
            "source": "yaml_environment",
            "line": 6,
            "has_secret_pattern": True,
        },
    ]

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.dev").write_text("DB_PASSWORD=devpass\nAPI_TOKEN=\n")
        (root / ".env.prod").write_text("DB_PASSWORD=${DB_PASSWORD}\nAPI_TOKEN=${API_TOKEN}\n")

        db_overrides = find_config_overrides(root, ".env.dev", "DB_PASSWORD")
        api_overrides = find_config_overrides(root, ".env.dev", "API_TOKEN")

    assert db_overrides == [
        {
            "file": ".env.prod",
            "line": 1,
            "value": "DB_PASSWORD=${DB_PASSWORD}",
            "environment": "production",
        }
    ]
    assert api_overrides == [
        {
            "file": ".env.prod",
            "line": 2,
            "value": "API_TOKEN=${API_TOKEN}",
            "environment": "production",
        }
    ]

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text("services:\n  web:\n    env_file: .env\n")
        (root / ".env").write_text("ADMIN_PASSWORD=${ADMIN_PASSWORD}\n")
        (root / "docker-compose.prod.yml").write_text(
            "services:\n  web:\n    build:\n      context: .\n      dockerfile: Dockerfile\n"
        )
        (root / "Dockerfile").write_text("FROM python:3.11\n")

        related = find_related_configs(root, "docker-compose.yml")

    assert related == [
        {"file": "Dockerfile", "relationship": "builds_dockerfile"},
        {"file": "docker-compose.prod.yml", "relationship": "compose_variant"},
        {"file": ".env", "relationship": "env_file"},
    ]
