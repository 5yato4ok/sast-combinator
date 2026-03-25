import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_callers



def test_find_callers_should_not_return_exported_function_definition_as_caller():
    source = """\
import { useState } from 'react';

export default function OAuthDebugPage() {
  const [code, setCode] = useState(null);
  return code;
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(source)

        result = find_callers(root, "page.tsx", "OAuthDebugPage")

    assert result == []

def test_find_callers_should_prefer_real_method_invocation_over_definition():
    source_def = """\
export class UriService {
  changePort(newPort: string): void {
    window.location.replace(newPort);
  }
}
"""
    source_use = """\
function run(service) {
  service.changePort('8443');
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "uri.service.ts").write_text(source_def)
        (root / "page.ts").write_text(source_use)

        result = find_callers(root, "uri.service.ts", "changePort")

    assert result
    assert result[0]["file"] == "page.ts"

def test_find_callers_should_not_treat_cpp_declaration_and_definition_as_callers():
    source_def = """\
class SecuritySettingsWidget {
public:
    void openPixelationConfigurationDialog();
};

void SecuritySettingsWidget::openPixelationConfigurationDialog()
{
    configure();
}
"""
    source_use = """\
void run(SecuritySettingsWidget* widget)
{
    widget->openPixelationConfigurationDialog();
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "security_settings_widget.cpp").write_text(source_def)
        (root / "other.cpp").write_text(source_use)

        result = find_callers(root, "security_settings_widget.cpp", "openPixelationConfigurationDialog")

    assert result
    assert result[0]["file"] == "other.cpp"

def test_find_callers_should_report_enclosing_javascript_function_name_for_callback_invocations():
    source = """\
async function setPreviewState(asset_id, create_id, el, state) {
    const params = new URLSearchParams(window.location.search);
    return state;
}

function bindSelects() {
    const selectElements = $('.field-asset select');
    selectElements.each(function (index) {
        const val = $(this).children("option:selected").val();
        setPreviewState(val, false, this);
    });
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "menuChange.js").write_text(source)

        result = find_callers(root, "menuChange.js", "setPreviewState")

    assert result
    assert result[0]["caller_function"] == "bindSelects"



def test_find_callers_should_not_use_catch_parameter_name_as_caller_function():
    source = """\
async function main() {
    console.log('Starting');
}

main().catch(error => {
    console.error(error.message);
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "generate-customization.js").write_text(source)

        result = find_callers(root, "generate-customization.js", "main")

    assert result
    assert result[0]["caller_function"] is None


def test_find_callers_should_leave_top_level_promise_then_without_fake_caller_name():
    source = """\
function fetchData() {
    return Promise.resolve(1);
}

fetchData().then((result) => {
    console.log(result);
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sample.js").write_text(source)

        result = find_callers(root, "sample.js", "fetchData")

    assert result
    assert result[0]["caller_function"] is None


def test_find_callers_should_leave_event_listener_callback_invocation_without_fake_caller_name():
    source = """\
function handle() {
    return true;
}
window.addEventListener('click', () => {
    handle();
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sample.js").write_text(source)

        result = find_callers(root, "sample.js", "handle")

    assert result
    assert result[0]["caller_function"] is None
