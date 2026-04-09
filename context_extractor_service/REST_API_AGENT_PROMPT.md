# Context Extractor — REST API Reference for AI Agents

Self-contained reference for AI agents that **do not support the MCP protocol**.
All 20 Context Extractor tools are available via plain HTTP.

---

## Protocol

| Operation | Method | Path |
|-----------|--------|------|
| List all tools | `GET` | `/mcp/v1/tools` |
| Call a tool | `POST` | `/mcp/v1/tools/{tool_name}` |
| OpenAPI spec | `GET` | `/mcp/v1/openapi.yaml` |

Tool parameters are passed as a **JSON object in the request body**. No URL encoding needed.

---

## Authentication

```
Authorization: Bearer <MCP_AUTH_TOKEN>
Content-Type: application/json
```

Same token as the MCP protocol. When the server has no token configured
(development mode), the header is optional.

**Errors:** `401` — header missing · `403` — wrong token

---

## Base URL

```
https://aist.itsec-europe.com/mcp/v1
```

Development: `http://localhost:8000/v1`

---

## Common Concepts

**`pipeline_id`** — required by all tools except `list_supported_languages`.
The server resolves it to the project source directory via the AIST API.

**`file_path`** — relative path within the project. No leading `/`, no `..`.
Example: `src/auth/login.py`, `docker-compose.yml`.

**`line_number`** — always 1-based (first line = 1).

**Response envelope** — every successful response:
```json
{"tool": "<tool_name>", "result": <value>}
```

**Error response** — all errors (400/401/403/404/500):
```json
{"error": "<message>"}
```

---

## Tool Discovery

### `GET /tools` — List all tools

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://aist.itsec-europe.com/mcp/v1/tools
```

**Response:**
```json
[
  {
    "name": "extract_function",
    "description": "Extract the full function/method containing the given line number.",
    "params": [
      {"name": "pipeline_id", "type": "string",  "required": true},
      {"name": "file_path",   "type": "string",  "required": true},
      {"name": "line_number", "type": "integer", "required": true}
    ]
  },
  ...
]
```

---

## Code Analysis Tools

### `extract_function` — Extract function/method at a line

**What:** Extracts the full source of the function containing the given line.
Returns: `text` (full source), `meta.language`, `meta.function_lines` ([start, end]),
`meta.target_line` (absolute), `meta.relative_line_number` (offset within function),
`meta.code_on_line` (exact text of the requested line).

**When:** Always start here. Read the function before making a TP/FP verdict.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/login.py", "line_number": 87}' \
  https://aist.itsec-europe.com/mcp/v1/tools/extract_function
```

**Response:**
```json
{
  "tool": "extract_function",
  "result": {
    "text": "def login(request):\n    username = request.POST.get('user')\n    ...\n    cursor.execute(query)\n",
    "meta": {
      "language": "python",
      "function_lines": [80, 105],
      "target_line": 87,
      "relative_line_number": 8,
      "code_on_line": "    cursor.execute(query)"
    }
  }
}
```

---

### `find_identifiers` — Analyze reads and writes on a line

**What:** Returns all identifiers semantically read (operands, receiver, method name,
args) and written (assigned/bound) on the given statement.

**When:** Step after `extract_function`. Identify suspicious `reads` variables
(request objects, params) and feed them into `trace_identifier_backward`.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/login.py", "line_number": 87}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_identifiers
```

**Response:**
```json
{
  "tool": "find_identifiers",
  "result": {"reads": ["cursor", "execute", "query", "user_id"], "writes": [], "language": "python"}
}
```

---

### `dump_ast` — Show AST of the function at a line

**What:** Returns the tree-sitter AST of the enclosing function as a human-readable string.

**When:** When `extract_function` isn't enough structural context, or for unfamiliar languages.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/login.py", "line_number": 87}' \
  https://aist.itsec-europe.com/mcp/v1/tools/dump_ast
```

**Response:**
```json
{"tool": "dump_ast", "result": "function_definition [80:0 - 105:0]\n  name: identifier 'login'\n  ..."}
```

---

### `list_supported_languages` — List AST-supported languages

**What:** Returns sorted list of language IDs for which smart tools work.
Files in unsupported languages still accessible via filesystem tools.

**No parameters required.**

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://aist.itsec-europe.com/mcp/v1/tools/list_supported_languages
```

**Response:**
```json
{"tool": "list_supported_languages", "result": ["bash","cpp","csharp","go","java","javascript","kotlin","php","python","ruby","typescript"]}
```

---

### `get_file_structure` — Parse top-level structure of a file

**What:** Returns classes (with methods), standalone functions, and imports.

**When:** Before reading a large file — navigate to the exact function you need.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/views.py"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/get_file_structure
```

**Response:**
```json
{
  "tool": "get_file_structure",
  "result": {
    "language": "python",
    "classes": [{"name": "LoginView", "line": 12, "methods": [{"name": "post", "line": 20}]}],
    "functions": [{"name": "validate_token", "line": 78, "end_line": 95}],
    "imports": ["from django.contrib.auth import authenticate"]
  }
}
```

---

## Data Flow Tools

### `trace_identifier_backward` — Trace variable origin (up to 3 hops)

**What:** Walks backward through the function to find where a variable's value comes from.
Returns a chain of up to 3 assignment steps: `{line, code, writes, reads}`.

**When:** The critical step for TP/FP. Pick suspicious `reads` from `find_identifiers`, trace each one.

- **TP likely** — user-controlled: `request.GET`, `request.POST`, `req.body`, URL params, cookies, headers
- **FP likely** — safe: hardcoded constant, `int()` cast, `uuid.UUID()`, allowlist lookup
- **Check further** — semi-trusted: DB value, env var, config

If user-controlled, check for sanitization: `int()`, `escape()`, `bleach.clean()`, `%s` placeholder.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/login.py", "line_number": 87, "identifier": "query"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/trace_identifier_backward
```

**Response:**
```json
{
  "tool": "trace_identifier_backward",
  "result": [
    {"line": 84, "code": "    query = f\"SELECT * FROM users WHERE name='{username}'\"", "writes": ["query"], "reads": ["username"]},
    {"line": 82, "code": "    username = request.POST.get('user')", "writes": ["username"], "reads": ["request","POST","get","user"]}
  ]
}
```

---

### `find_callers` — Find all call sites of a function

**What:** Searches the entire project for where the function is called.
Returns `{file, line, caller_function, snippet}` per call site.

**When:** Check if all callers pass only safe/constant arguments → FP.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/db/queries.py", "function_name": "execute_query"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_callers
```

**Response:**
```json
{
  "tool": "find_callers",
  "result": [{"file": "src/api/views.py", "line": 117, "caller_function": "user_search", "snippet": "    result = execute_query(search_term)"}]
}
```

---

### `find_definition` — Find symbol definitions

**What:** Searches for where a function, class, variable, or type is defined.
Returns `{file, line, kind}`.

**When:** Inspect helper functions like `safe_query()` — does it actually sanitize?

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "symbol_name": "safe_query"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_definition
```

**Response:**
```json
{
  "tool": "find_definition",
  "result": [{"file": "src/db/helpers.py", "line": 23, "kind": "function"}]
}
```

---

## Security Context Tools

### `classify_file` — Classify file type

**What:** Language-agnostic classification using path heuristics.
Returns `{type, confidence, reason}`.
Types: `test` · `migration` · `vendored` · `generated` · `config` · `production`

**When:** Call **first**. `test`/`migration`/`vendored` → immediate FP.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "tests/test_auth.py"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/classify_file
```

**Response:**
```json
{"tool": "classify_file", "result": {"type": "test", "confidence": 0.95, "reason": "Path starts with 'tests/'"}}
```

---

### `find_imports` — Extract all import statements

**What:** Returns all `import`/`require`/`using`/`#include` statements.

**When:** Detect framework protections:
- Django ORM + `.filter()/.get()` → parameterized, SQLi FP
- `import bleach` → HTML sanitization available
- `subprocess` with `shell=False` → command injection FP

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/login.py"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_imports
```

**Response:**
```json
{"tool": "find_imports", "result": ["from django.db import connection", "import bleach"]}
```

---

### `find_decorators` — Find decorators on the function at a line

**What:** Returns all decorators/annotations on the enclosing function.

**When:** Assess access controls: `@login_required` → authenticated only; `@csrf_exempt` → CSRF protection off.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "src/auth/views.py", "line_number": 55}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_decorators
```

**Response:**
```json
{"tool": "find_decorators", "result": ["@login_required", "@permission_required('admin')"]}
```

---

### `find_route_to_function` — Find URL routes to a function

**What:** Searches routing files for entries referencing the function name.
Returns `{file, line, pattern, snippet}`.

**When:** Reachability check — no route found → dead code → strong FP.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "function_name": "UserView"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_route_to_function
```

**Response:**
```json
{
  "tool": "find_route_to_function",
  "result": [{"file": "myapp/urls.py", "line": 34, "pattern": "^api/users/<int:pk>/$", "snippet": "    path('api/users/<int:pk>/', UserView.as_view()),"}]
}
```

---

## Config Analysis Tools

### `classify_environment` — Determine config file environment

**What:** Classifies target environment from filename heuristics.
Returns `{environment, confidence, reason}`.
Environments: `dev` · `staging` · `production` · `test` · `ci` · `unknown`

**When:** Call **first** for config findings. `dev`/`test`/`ci` → low priority; `production` → high.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": ".env.production"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/classify_environment
```

**Response:**
```json
{"tool": "classify_environment", "result": {"environment": "production", "confidence": 0.95, "reason": "Filename contains '.production'"}}
```

---

### `extract_config_block` — Extract config block at a line

**What:** Extracts the logical block at the given line. AST-based for YAML, Dockerfile, HCL, TOML, JSON.
Returns `{block_text, block_type, key_path, start_line, end_line, language}`.

**When:** See full context around the finding before verdict.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "docker-compose.yml", "line_number": 42}' \
  https://aist.itsec-europe.com/mcp/v1/tools/extract_config_block
```

**Response:**
```json
{
  "tool": "extract_config_block",
  "result": {"block_text": "celeryworker:\n  privileged: true\n", "block_type": "yaml-mapping", "key_path": "services.celeryworker", "start_line": 38, "end_line": 51, "language": "yaml"}
}
```

---

### `find_config_overrides` — Find same key in other config files

**What:** Searches other config files for the same key/variable. Returns `{file, line, value, environment}`.

**When:** `DD_DEBUG=True` in `.env.dev` → check if `DD_DEBUG=False` in `.env.prod` → FP.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": ".env.dev", "key_or_variable": "DD_DEBUG"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_config_overrides
```

**Response:**
```json
{"tool": "find_config_overrides", "result": [{"file": ".env.production", "line": 7, "value": "False", "environment": "production"}]}
```

---

### `extract_env_variables` — Extract env variable definitions

**What:** Returns `{name, value, source, line, has_secret_pattern}` per variable.

Decision guide:
- `has_secret_pattern: true` + hardcoded value → **TP**
- `has_secret_pattern: true` + `${VAR}` or empty → **FP** (placeholder)

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "docker-compose.yml"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/extract_env_variables
```

**Response:**
```json
{
  "tool": "extract_env_variables",
  "result": [
    {"name": "SECRET_KEY", "value": "hardcoded-abc123", "source": "ENV", "line": 14, "has_secret_pattern": true},
    {"name": "DEBUG", "value": "True", "source": "ENV", "line": 15, "has_secret_pattern": false}
  ]
}
```

---

### `find_related_configs` — Find related config files

**What:** Detects Dockerfile ↔ docker-compose, docker-compose ↔ .env, Terraform peers, K8s peers.
Returns `{file, relationship}`.

**When:** Understand the full config chain: does docker-compose override the Dockerfile setting?

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "Dockerfile"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/find_related_configs
```

**Response:**
```json
{
  "tool": "find_related_configs",
  "result": [
    {"file": "docker-compose.yml", "relationship": "referenced_by"},
    {"file": ".env", "relationship": "env_file"}
  ]
}
```

---

## Filesystem Tools

### `read_file` — Read full file contents

**What:** Raw text content of any file (max 1 MB).
Use when smart tools don't cover your need (unsupported format, full config file, README).

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "file_path": "README.md"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/read_file
```

**Response:**
```json
{"tool": "read_file", "result": "# My Project\n\nThis project does ...\n"}
```

---

### `search_files` — Regex search across project files

**What:** Grep across all source and config files. Up to 50 results. Timeout 30s.
Excluded: `.git/`, `node_modules/`, `__pycache__/`, `vendor/`, `.tox/`.

**No URL encoding needed** — pass complex regexes as plain JSON strings.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "pattern": "cursor\\.execute", "path": "src/db"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/search_files
```

**Response:**
```json
{
  "tool": "search_files",
  "result": [
    {"file": "src/db/queries.py", "line": 87, "match": "    cursor.execute(query, params)"},
    {"file": "src/reports/export.py", "line": 134, "match": "    cursor.execute(f\"SELECT * FROM {table}\")"}
  ]
}
```

---

### `list_directory` — List files and directories

**What:** Lists contents of a project directory. Returns `{name, type, size}`.
Omit `path` to list the project root.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pipeline_id": "a1b2c3d4", "path": "src/auth"}' \
  https://aist.itsec-europe.com/mcp/v1/tools/list_directory
```

**Response:**
```json
{
  "tool": "list_directory",
  "result": [
    {"name": "views.py", "type": "file", "size": 4821},
    {"name": "serializers.py", "type": "file", "size": 2103},
    {"name": "tests", "type": "directory"}
  ]
}
```

---

## Quick Decision Flows

### Code finding (SQLi, XSS, Command Injection, Path Traversal)

```
1. classify_file            → "test"/"migration"/"vendored" → FP, stop
2. extract_function         → read the function, identify the sink
3. find_imports             → detect ORM, bleach, shell=False, etc.
4. find_decorators          → @login_required, @csrf_exempt, etc.
5. find_identifiers         → get reads/writes on the sink line
6. trace_identifier_backward → for each suspicious "reads" var:
   → user-controlled origin (request.*) → TP
   → safe origin (int cast, constant) → FP
7. find_route_to_function   → no route → dead code → FP
8. find_callers             → all callers pass constants → FP
9. find_definition          → sink calls sanitizer → inspect it
```

### Config finding (Docker, YAML, Terraform, K8s)

```
1. classify_file            → "test"/"ci"/"template" → FP, stop
2. classify_environment     → "dev"/"test" → low priority, check overrides
3. extract_config_block     → read full context around the finding
4. find_config_overrides    → secure override in prod exists → FP
5. extract_env_variables    → has_secret_pattern + value type
6. find_related_configs     → inspect the full config chain
```

---

## OpenAPI Specification

Machine-readable OpenAPI 3.0 schema:
```
GET /mcp/v1/openapi.yaml
```
Compatible with Swagger UI, Redoc, and any OpenAPI-aware tooling.
