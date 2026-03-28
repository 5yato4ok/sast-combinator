from _mcp_server_regressions_helpers import *
def test_find_identifiers_should_support_tsx_files(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
    const nextUrl = "/oauth/callback";

    return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "src/app/debug/oauth/page.tsx", 4)

    assert "nextUrl" in result["reads"]




def test_find_identifiers_should_capture_typescript_template_literal_inputs(monkeypatch):
    source = """\
class UriService {
    changePort(newPort: string): void {
        window.location.replace(
            `${window.location.protocol}//${window.location.hostname}:${newPort}/${window.location.hash}`,
        );
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "uri.service.ts"))

    result = mcp_server.find_identifiers("pipe", "uri.service.ts", 3)

    assert "window" in result["reads"]
    assert "newPort" in result["reads"]




def test_find_identifiers_should_capture_typescript_declaration_reads_and_writes(monkeypatch):
    source = "const channel = new BroadcastChannel(COOKIE_POLICY_CHANNEL)\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.ts"))

    result = mcp_server.find_identifiers("pipe", "sample.ts", 1)

    assert "channel" in result["writes"]
    assert "BroadcastChannel" in result["reads"]
    assert "COOKIE_POLICY_CHANNEL" in result["reads"]




def test_find_identifiers_should_capture_javascript_template_literal_identifiers(monkeypatch):
    source = 'const stateLabel = `<a href="${reviewUrl}">${state}</a>`;\n'
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 1)

    assert "stateLabel" in result["writes"]
    assert "reviewUrl" in result["reads"]
    assert "state" in result["reads"]




def test_find_identifiers_should_capture_destructured_tsx_function_parameters(monkeypatch):
    source = """\
export default function Alert({ type, ...props }: AlertProps) {
    return props.children;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Alert.tsx"))

    result = mcp_server.find_identifiers("pipe", "Alert.tsx", 1)

    assert "Alert" in result["writes"]
    assert "type" in result["writes"]
    assert "props" in result["writes"]




def test_find_identifiers_should_capture_jsx_expression_identifiers(monkeypatch):
    source = """\
function GlobalSearchBar() {
  return <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "GlobalSearchBar.tsx"))

    result = mcp_server.find_identifiers("pipe", "GlobalSearchBar.tsx", 2)

    assert "styles" in result["reads"]
    assert "getCommandKeySymbol" in result["reads"]




def test_find_identifiers_should_support_json_assets(monkeypatch):
    source = """\
{
  "apiKey": "AIzaSyA8bA6jCS4GnzmfGEg_I6mQyG5JIBKFrLI",
  "enabled": true
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_structure.json"))

    result = mcp_server.find_identifiers("pipe", "cloud_structure.json", 2)

    assert result["language"] == "json"
    assert result["reads"] == []
    assert result["writes"] == []




def test_find_identifiers_should_capture_bash_redirect_literal_as_write_target(monkeypatch):
    source = """\
#!/usr/bin/env bash

if [[ ! -f etc/.local_env ]]; then
    echo "Creating .local_env file in etc directory"
    echo 'PY_PKG_MANAGER="poetry"' > etc/.local_env
fi
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 6)

    assert result["language"] == "bash"
    assert result["reads"] == []
    assert result["writes"] == ["etc/.local_env"]




def test_find_identifiers_should_keep_bash_variable_expansions_without_command_tokens(monkeypatch):
    """
    Scenario: a triage agent inspects a shell command that forwards an environment
    variable to another tool and needs the actual data dependency, not the command name.
    """
    source = """\
#!/usr/bin/env bash

echo "$BAR"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["BAR"]
    assert result["writes"] == []




def test_find_identifiers_should_capture_bash_redirect_expression_as_write_target(monkeypatch):
    """
    Scenario: a triage agent inspects a shell redirection and needs the dynamic output
    target variable, while static command and path words should stay out of the result.
    """
    source = """\
#!/usr/bin/env bash

echo ok > "$OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["OUT"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_capture_bash_append_redirect_as_write_target(monkeypatch):
    source = """\
#!/usr/bin/env bash

echo ok >> logs/output.log
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == []
    assert result["writes"] == ["logs/output.log"]


def test_find_identifiers_should_capture_bash_input_redirect_as_read_target(monkeypatch):
    source = """\
#!/usr/bin/env bash

cat < etc/input.conf
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["etc/input.conf"]
    assert result["writes"] == []


def test_find_identifiers_should_capture_mixed_bash_redirect_semantics(monkeypatch):
    source = """\
#!/usr/bin/env bash

cat < "$IN" > "$OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["$IN", "IN", "OUT"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_ignore_redirect_operators_inside_bash_strings(monkeypatch):
    source = """\
#!/usr/bin/env bash

echo "the string where 7 < 9 and 11 >> 2 and x > y"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == []
    assert result["writes"] == []


def test_find_identifiers_should_treat_docker_exec_inner_shell_as_opaque_string(monkeypatch):
    source = """\
#!/usr/bin/env bash

docker exec "$CTR" sh -c "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["CTR", "OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_parse_bash_lc_inner_redirects(monkeypatch):
    source = """\
#!/usr/bin/env bash

bash -lc "cat < /tmp/in > /tmp/out"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["/tmp/in"]
    assert result["writes"] == ["/tmp/out"]


def test_find_identifiers_should_parse_zsh_c_inner_redirects(monkeypatch):
    source = """\
#!/usr/bin/env bash

zsh -c "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_parse_sudo_bash_lc_inner_redirects(monkeypatch):
    source = """\
#!/usr/bin/env bash

sudo -u app bash -lc "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_parse_env_sh_c_inner_redirects(monkeypatch):
    source = """\
#!/usr/bin/env bash

env FOO=1 BAR=2 sh -c "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_parse_docker_compose_exec_shell_command(monkeypatch):
    source = """\
#!/usr/bin/env bash

docker compose exec app sh -c "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_parse_ssh_remote_shell_command(monkeypatch):
    source = """\
#!/usr/bin/env bash

ssh "$HOST" "cat $VAR > $OUT"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == ["HOST", "OUT", "VAR"]
    assert result["writes"] == ["$OUT"]


def test_find_identifiers_should_ignore_inner_redirect_symbols_inside_wrapper_shell_strings(monkeypatch):
    source = """\
#!/usr/bin/env bash

bash -lc "echo 'the string where 7 < 9 and 11 >> 2 and x > y'"
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "cloud_helper.sh"))

    result = mcp_server.find_identifiers("pipe", "cloud_helper.sh", 3)

    assert result["language"] == "bash"
    assert result["reads"] == []
    assert result["writes"] == []


def test_find_identifiers_should_capture_typed_arrow_parameter_bindings(monkeypatch):
    source = """\
export const buildMutation = async (
  updateServiceUrl: string,
  services: Record<string, { price: number | null }>,
  entityType: 'channel_partners' | 'organization'
) => {
  const includeTier = entityType === 'channel_partners';
  return includeTier;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))

    result = mcp_server.find_identifiers("pipe", "mutations.ts", 3)

    assert "updateServiceUrl" in result["writes"]
    assert "services" in result["writes"]
    assert "entityType" in result["writes"]




def test_find_identifiers_should_not_treat_window_as_write_on_redirect_assignment(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const buildOauthUrl = () => '/oauth';
  return () => {
    window.location.href = buildOauthUrl();
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 4)

    assert "buildOauthUrl" in result["reads"]
    assert "window" not in result["writes"]




def test_find_identifiers_should_capture_inline_jsx_callback_reads(monkeypatch):
    source = """\
function Page() {
  return <Button onClick={() => {
    router.push('/x')
  }}>Go</Button>
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 2)

    assert "router" in result["reads"]
    assert "push" in result["reads"]


def test_find_identifiers_should_support_qml_function_calls(monkeypatch):
    source = """\
Item {
  property string url: backend.baseUrl
  function send(value) {
    Qt.openUrlExternally(url)
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "View.qml"))

    result = mcp_server.find_identifiers("pipe", "View.qml", 4)

    assert result["language"] == "qml"
    assert result["reads"] == ["Qt", "openUrlExternally", "url"]
    assert result["writes"] == []


def test_find_identifiers_should_treat_typescript_for_of_binding_as_write(monkeypatch):
    source = "for (const item of items) { sink(item) }\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.ts"))

    result = mcp_server.find_identifiers("pipe", "sample.ts", 1)

    assert result["language"] == "typescript"
    assert "item" in result["writes"]
    assert "items" in result["reads"]
    assert "item" not in result["reads"]


def test_find_identifiers_should_treat_csharp_foreach_binding_as_write(monkeypatch):
    source = "foreach (var item in items) { Sink(item); }\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.cs"))

    result = mcp_server.find_identifiers("pipe", "sample.cs", 1)

    assert result["language"] == "csharp"
    assert "item" in result["writes"]
    assert "items" in result["reads"]
    assert "item" not in result["reads"]
