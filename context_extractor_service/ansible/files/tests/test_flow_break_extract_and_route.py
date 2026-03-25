import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.extract import extract_function_from_source
from context_extractor.project_analysis import find_route_to_function


def test_find_route_to_function_should_ignore_vendor_asset_hits_for_generic_symbol():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.js").write_text("async function main() { return true; }\n")
        (root / "vendor.js").write_text("app.use('/admin', middleware),main=1;\n")

        routes = find_route_to_function(root, "main")

    assert routes == []


def test_find_route_to_function_should_keep_real_express_route_hits():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.js").write_text(
            "app.get('/health', handleHealth)\n"
            "function handleHealth(req, res) { return res; }\n",
        )

        routes = find_route_to_function(root, "handleHealth")

    assert routes
    assert routes[0]["pattern"] == "/health"


def test_extract_function_should_keep_typescript_catch_boundary_line():
    source = """\
async function extractIcons() {
  for (const filename of imageFiles) {
    try {
      const fileData = await read(filename);
    } catch (error) {
      logger.warn(error);
    }
  }
}
"""

    result = extract_function_from_source(source, "kmz-parser.ts", 5, 200)

    assert result["meta"]["code_on_line"] == "    } catch (error) {"


def test_extract_function_should_keep_normal_typescript_statement_line():
    source = """\
async function extractIcons() {
  for (const filename of imageFiles) {
    try {
      const fileData = await read(filename);
      logger.debug(fileData);
    } catch (error) {
      logger.warn(error);
    }
  }
}
"""

    result = extract_function_from_source(source, "kmz-parser.ts", 4, 200)

    assert result["meta"]["code_on_line"] == "      const fileData = await read(filename);"
