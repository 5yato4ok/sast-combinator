# Context extractor implementation

This directory contains the FastMCP server, the reusable Tree-sitter analysis
package, and isolated regression tests.

## Layout

- `mcp_server.py` — authenticated MCP transport, pipeline-root resolution, path
  guard, bounded filesystem tools, and tool registration;
- `context_extractor/` — parsing, extraction, identifier, configuration, and
  source-analysis logic;
- `tests/` — fixture-based unit and MCP regression tests;
- `Dockerfile` — production and test image.

Handlers in `mcp_server.py` should remain thin. Parsing or analysis fixes belong
in `context_extractor/`, where they can be tested without a live AIST workspace.
Every file access must pass through the project-root guard.

## CLI smoke check

From the service image or an equivalent container environment:

```bash
python -m context_extractor.cli \
  --file tests/fixtures/sample.py \
  --line 5 \
  --compress
```

## Tests

Run tests in Docker from this directory:

```bash
docker build -t aist-context-extractor-mcp:test .
docker run --rm \
  -v "$PWD":/app \
  -w /app \
  aist-context-extractor-mcp:test \
  python -m pytest tests/ -q
```

Tests must use their own fixtures and must not depend on live paths under
`/tmp/aist/projects`.
