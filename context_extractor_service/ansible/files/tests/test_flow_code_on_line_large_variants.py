import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source


def test_extract_function_should_keep_exact_line_for_hook_dependency_array_call():
    source = """\
const StatusForm = () => {
  const { isSaving, setIsSaving } = useEditEntityFormRef(
    {
      ref,
      hasUnsavedChanges,
      retry: async () => {
        await handleSaveButtonClick(saveAndExit);
      },
    },
    [individualCpOrOrg, selectedEntityState]
  );
}
"""

    result = extract_function_from_source(source, "StatusForm.tsx", 10, 200)

    assert result["meta"]["code_on_line"] == "    [individualCpOrOrg, selectedEntityState]"


def test_extract_function_should_keep_exact_line_for_fallback_object_property():
    source = """\
function loadBrandConfig() {
  try {
    return require('./brand.json');
  } catch (error) {
    return {
      customization: 'default',
      cloudHost: 'nxvms.com',
      mapsName: 'NxMaps',
      supportLink: 'https://support.networkoptix.com',
    };
  }
}
"""

    result = extract_function_from_source(source, "config.ts", 8, 200)

    assert result["meta"]["code_on_line"] == "      mapsName: 'NxMaps',"


def test_extract_function_should_keep_exact_line_for_normal_array_literal():
    source = """\
function useStatePair() {
  const values = [firstValue, secondValue];
  return values;
}
"""

    result = extract_function_from_source(source, "pair.ts", 2, 200)

    assert result["meta"]["code_on_line"] == "  const values = [firstValue, secondValue];"


def test_extract_function_should_keep_exact_line_for_normal_call_expression_argument():
    source = """\
function save() {
  useEditEntityFormRef(ref, [individualCpOrOrg, selectedEntityState]);
}
"""

    result = extract_function_from_source(source, "StatusForm.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == "  useEditEntityFormRef(ref, [individualCpOrOrg, selectedEntityState]);"
