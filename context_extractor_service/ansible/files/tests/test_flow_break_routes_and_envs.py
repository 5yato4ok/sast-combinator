import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config_analysis import classify_environment, extract_env_variables
from context_extractor.project_analysis import find_route_to_function


def test_find_route_to_function_should_ignore_vendor_hits_for_short_generic_symbol():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "vendor.js").write_text("app.use('/admin', middleware),u=1;\n")
        (root / "module.js").write_text("const u = 1;\n")

        routes = find_route_to_function(root, "u")

    assert routes == []


def test_find_route_to_function_should_keep_real_django_route_hit():
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

    assert routes
    assert routes[0]["pattern"] == "/login"
    assert routes[0]["file"] == "urls.py"


def test_classify_environment_should_keep_dev_and_template_semantics():
    assert classify_environment("deploy/docker-compose.override.yml")["environment"] == "dev"
    assert classify_environment(".env.local")["environment"] == "dev"
    assert classify_environment(".env.example")["environment"] == "template"


def test_extract_env_variables_should_keep_exact_yaml_environment_values():
    compose_source = (
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      ADMIN_PASSWORD: ${ADMIN_PASSWORD}\n"
        "      LOG_LEVEL: info\n"
    )

    result = extract_env_variables(compose_source, Path("docker-compose.prod.yml"))

    assert result == [
        {
            "name": "ADMIN_PASSWORD",
            "value": "${ADMIN_PASSWORD}",
            "source": "yaml_environment",
            "line": 4,
            "has_secret_pattern": True,
        },
        {
            "name": "LOG_LEVEL",
            "value": "info",
            "source": "yaml_environment",
            "line": 5,
            "has_secret_pattern": False,
        },
    ]
