import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


def test_extract_function_should_keep_exact_typed_arrow_parameter_line():
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

    result = extract_function_from_source(source, "mutations.ts", 3, 200)

    assert result["meta"]["code_on_line"] == "  services: Record<string, { price: number | null }>,"


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


def test_extract_function_should_keep_exact_normal_typed_variable_line():
    source = """\
export const buildMutation = async () => {
  const includeTier: boolean = true;
  return includeTier;
}
"""

    result = extract_function_from_source(source, "mutations.ts", 2, 200)

    assert result["meta"]["code_on_line"] == "  const includeTier: boolean = true;"


def test_find_identifiers_should_keep_normal_typed_variable_reads_and_writes(monkeypatch):
    source = """\
export const buildMutation = async () => {
  const includeTier: boolean = entityType === 'channel_partners';
  return includeTier;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "mutations.ts"))

    result = mcp_server.find_identifiers("pipe", "mutations.ts", 2)

    assert "includeTier" in result["writes"]
    assert "entityType" in result["reads"]
