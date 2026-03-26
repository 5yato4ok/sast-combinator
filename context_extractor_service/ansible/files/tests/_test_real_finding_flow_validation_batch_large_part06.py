# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

def test_real_finding_copy_nginx_configs_should_keep_python_tooling_flow(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/python_tooling/copy_nginx_configs.py")
    _write_source_tree(tmp_path, "etc/scripts/copy_nginx_configs.py", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "etc/scripts/copy_nginx_configs.py"
    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 11)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 11)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 11)
    callers = mcp_server.find_callers("5a36b942", file_path, "vars_substitute")
    definition = mcp_server.find_definition("5a36b942", "vars_substitute")
    route = mcp_server.find_route_to_function("5a36b942", "vars_substitute")

    assert classification["type"] == "config"
    assert extracted["meta"]["code_on_line"] == "    with open(os.path.join(NGINX_DEPLOYMENT_DIR, 'nginx.conf.template'), 'r') as template_file:"
    assert "import os" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["NGINX_DEPLOYMENT_DIR", "join", "open", "os", "path", "read", "template"],
        "writes": ["template_file"],
        "language": "python",
    }
    assert callers == [{"file": file_path, "line": 17, "caller_function": None, "snippet": callers[0]["snippet"]}]
    assert definition == [{"file": file_path, "line": 4, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_compare_licenses_should_keep_python_tooling_flow(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/python_tooling/compare_licenses.py")
    _write_source_tree(tmp_path, "tools/scripts/compare_licenses.py", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "compare_licenses.py"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "tools/scripts/compare_licenses.py"
    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 7)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 7)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 7)
    callers = mcp_server.find_callers("5a36b942", file_path, "compare_licenses")
    definition = mcp_server.find_definition("5a36b942", "compare_licenses")
    route = mcp_server.find_route_to_function("5a36b942", "compare_licenses")

    assert classification["type"] == "config"
    assert extracted["meta"]["code_on_line"] == "    with open(update, 'r') as f:"
    assert imports == ["import json", "import sys"]
    assert decorators == []
    assert identifiers == {
        "reads": ["json", "load", "open", "update", "update_licenses"],
        "writes": ["f"],
        "language": "python",
    }
    assert callers == [{"file": file_path, "line": 14, "caller_function": None, "snippet": callers[0]["snippet"]}]
    assert definition == [{"file": file_path, "line": 5, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_add_service_form_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/forms/AddServiceForm.tsx")
    _write_source_tree(tmp_path, "app/(dashboard)/channel-partners/components/AddServiceForm/AddServiceForm.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AddServiceForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/components/AddServiceForm/AddServiceForm.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 7)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 7)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 7)
    trace_console = mcp_server.trace_identifier_backward("69ec5b01", file_path, 7, "console")
    callers = mcp_server.find_callers("69ec5b01", file_path, "AddServiceForm")
    definition = mcp_server.find_definition("69ec5b01", "AddServiceForm")
    route = mcp_server.find_route_to_function("69ec5b01", "AddServiceForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\tconst onSubmit: SubmitHandler<IFormInput> = (data) => console.log(data);"
    assert "import { useForm, SubmitHandler } from 'react-hook-form';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["console", "data", "log"],
        "writes": ["onSubmit"],
        "language": "typescript",
    }
    assert trace_console == []
    assert callers == []
    assert definition == [{"file": file_path, "line": 5, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_dashboard_logo_should_keep_real_flow(monkeypatch, tmp_path):
    _write_fixture_tree(
        tmp_path,
        {
            "app/(dashboard)/components/Logo/Logo.tsx": "nx_connect/logo/DashboardLogo.tsx",
            "app/(external)/components/Logo/Logo.tsx": "nx_connect/logo/ExternalLogo.tsx",
        },
    )
    source = _fixture_text("nx_connect/logo/DashboardLogo.tsx")
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Logo.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/components/Logo/Logo.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 8)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 8)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 8)
    trace_logo_path = mcp_server.trace_identifier_backward("69ec5b01", file_path, 8, "logoPath")
    callers = mcp_server.find_callers("69ec5b01", file_path, "Logo")
    definition = mcp_server.find_definition("69ec5b01", "Logo")
    route = mcp_server.find_route_to_function("69ec5b01", "Logo")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\tconsole.log('logoPath', logoPath);"
    assert "import './styles.scss';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["console", "log", "logoPath"],
        "writes": [],
        "language": "typescript",
    }
    assert trace_logo_path == [
        {
            "line": 7,
            "code": "const logoPath = currentTheme === 'dark' ? configData.LOGO_DARK : configData.LOGO_LIGHT;",
            "writes": ["logoPath"],
            "reads": ["LOGO_DARK", "LOGO_LIGHT", "configData", "currentTheme"],
        },
        {
            "line": 6,
            "code": "const currentTheme = getTheme(theme, systemTheme);",
            "writes": ["currentTheme"],
            "reads": ["getTheme", "systemTheme", "theme"],
        },
    ]
    assert callers == []
    assert route == []
    assert any(item["file"] == "app/(dashboard)/components/Logo/Logo.tsx" for item in definition)
    assert any(item["file"] == "app/(external)/components/Logo/Logo.tsx" for item in definition)


def test_real_finding_channel_partner_form_error_line_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("channel_partner_form/ChannelPartnerForm.error.tsx")
    _write_source_tree(
        tmp_path,
        "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
        source,
    )
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ChannelPartnerForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 8)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 8)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 8)
    trace_console = mcp_server.trace_identifier_backward("69ec5b01", file_path, 8, "console")
    callers = mcp_server.find_callers("69ec5b01", file_path, "ChannelPartnerForm")
    definition = mcp_server.find_definition("69ec5b01", "ChannelPartnerForm")
    route = mcp_server.find_route_to_function("69ec5b01", "ChannelPartnerForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\t\tconsole.error('Error during channel partner creation: ', error);"
    assert imports == ["import axios from '@/app/axiosInstance';"]
    assert decorators == []
    assert identifiers == {"reads": ["console", "error"], "writes": [], "language": "typescript"}
    assert trace_console == []
    assert callers == []
    assert definition == [{"file": file_path, "line": 3, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_alert_component_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/alert/Alert.tsx")
    _write_source_tree(tmp_path, "app/components/ui/Alert/Alert.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Alert.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/components/ui/Alert/Alert.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 3)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 3)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 3)
    callers = mcp_server.find_callers("69ec5b01", file_path, "Alert")
    definition = mcp_server.find_definition("69ec5b01", "Alert")
    route = mcp_server.find_route_to_function("69ec5b01", "Alert")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "export default function Alert({ type, ...props }: Alert) {"
    assert imports == ["import InfoIcon from '@/icons/info.svg';"]
    assert decorators == []
    assert identifiers == {
        "reads": ["InfoIcon", "alert", "children", "classnames", "contentWrapper", "div", "icon", "styles"],
        "writes": ["Alert", "props", "type"],
        "language": "typescript",
    }
    assert callers == []
    assert definition == [{"file": file_path, "line": 3, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_add_subscription_form_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/forms/AddSubscriptionForm.tsx")
    _write_source_tree(
        tmp_path,
        "app/(dashboard)/subscriptions/components/AddSubscriptionForm/AddSubscriptionForm.tsx",
        source,
    )
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "AddSubscriptionForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/subscriptions/components/AddSubscriptionForm/AddSubscriptionForm.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 12)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 12)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 12)
    callers = mcp_server.find_callers("69ec5b01", file_path, "AddSubscriptionForm")
    definition = mcp_server.find_definition("69ec5b01", "AddSubscriptionForm")
    route = mcp_server.find_route_to_function("69ec5b01", "AddSubscriptionForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\tconst onSubmit: SubmitHandler<FormValues> = (data) => console.log(data);"
    assert "import { useForm, SubmitHandler } from 'react-hook-form';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["console", "data", "log"],
        "writes": ["onSubmit"],
        "language": "typescript",
    }
    assert callers == []
    assert definition == [{"file": file_path, "line": 8, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_profile_settings_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/settings/ProfileSettings.tsx")
    _write_source_tree(tmp_path, "app/(dashboard)/settings/components/ProfileSettings/ProfileSettings.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ProfileSettings.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/settings/components/ProfileSettings/ProfileSettings.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 7)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 7)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 7)
    callers = mcp_server.find_callers("69ec5b01", file_path, "ProfileSettings")
    definition = mcp_server.find_definition("69ec5b01", "ProfileSettings")
    route = mcp_server.find_route_to_function("69ec5b01", "ProfileSettings")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\tconst onSubmit: SubmitHandler<ProfileFormValues> = (data) => console.log(data);"
    assert imports == ["import { useForm, SubmitHandler } from 'react-hook-form';"]
    assert decorators == []
    assert identifiers == {
        "reads": ["console", "data", "log"],
        "writes": ["onSubmit"],
        "language": "typescript",
    }
    assert callers == []
    assert definition == [{"file": file_path, "line": 5, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


@pytest.mark.parametrize(
    ("line_number", "code_on_line", "reads", "writes", "trace_symbol", "trace_expected"),
    [
        (
            11,
            "\tObject.keys(pd.revenuePastYear).forEach((month: string) => {",
            ["Object", "console", "forEach", "keys", "log", "month", "pd", "revenuePastYear"],
            [],
            "pd",
            [{"line": 6, "code": "const pd = { revenuePastYear: { jan: { id: 0 } } };", "writes": ["pd"], "reads": []}],
        ),
        (
            15,
            "\t\tawait axios.get(`channel_partners/${rootChannelPartner?.id}/services/available/`)",
            ["axios", "data", "get", "id", "rootChannelPartner"],
            ["availableServices"],
            "rootChannelPartner",
            [{"line": 7, "code": "const rootChannelPartner = { id: 'cp-1' };", "writes": ["rootChannelPartner"], "reads": []}],
        ),
        (
            17,
            "\tpd.revenuePastYear.jan.id += quantity * price;",
            ["jan", "pd", "price", "quantity", "revenuePastYear"],
            ["id"],
            "quantity",
            [{"line": 8, "code": "const quantity = 2;", "writes": ["quantity"], "reads": []}],
        ),
        (
            18,
            "\tservice.numberAddedForEachService += quantity;",
            ["quantity", "service"],
            ["numberAddedForEachService"],
            "quantity",
            [{"line": 8, "code": "const quantity = 2;", "writes": ["quantity"], "reads": []}],
        ),
    ],
)
def test_real_finding_organization_details_should_keep_real_flow(
    monkeypatch,
    tmp_path,
    line_number,
    code_on_line,
    reads,
    writes,
    trace_symbol,
    trace_expected,
):
    source = _fixture_text("nx_connect/organizations/page.tsx")
    _write_source_tree(tmp_path, "app/(dashboard)/organizations/[id]/page.tsx", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/organizations/[id]/page.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, line_number)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, line_number)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("69ec5b01", file_path, "OrganizationDetails")
    definition = mcp_server.find_definition("69ec5b01", "OrganizationDetails")
    route = mcp_server.find_route_to_function("69ec5b01", "OrganizationDetails")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == code_on_line
    assert imports == ["import axios from '@/app/axiosInstance';"]
    assert decorators == []
    assert identifiers == {"reads": reads, "writes": writes, "language": "typescript"}
    assert trace == trace_expected
    assert callers == []
    assert definition == [{"file": file_path, "line": 5, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


