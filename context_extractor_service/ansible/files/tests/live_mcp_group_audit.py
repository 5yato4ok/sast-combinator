from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROJECT_PIPELINES = {
    "69ec5b01": 15,  # nx-connect-ui
    "07734951": 17,  # nx-maps-ui
    "9ce90895": 12,  # nx
    "5a36b942": 14,  # cloud_portal
}

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "live_audit"
    / "latest_report.json"
)

FUNCTION_PATTERNS = [
    re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*function\s*\("),
    re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>"),
    re.compile(r"\b([A-Za-z_][A-Za-z0-9_:<>]*)::([A-Za-z_][A-Za-z0-9_]*)\s*\("),
]


def _run_python_in_service(service: str, script: str) -> str:
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", service, "python", "-"],
        input=script,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker compose exec failed for {service}:\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def fetch_group_manifest(limit_per_project: int) -> list[dict[str, Any]]:
    script = f"""
import os, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aist_site.settings')
import django
django.setup()
from django.db.models import Count
from dojo.models import Finding

mapping = {PROJECT_PIPELINES!r}
rows = []
for pipeline_id, product_id in mapping.items():
    groups = (
        Finding.objects.filter(test__engagement__product_id=product_id)
        .exclude(file_path='')
        .values('title', 'file_path', 'line')
        .annotate(count=Count('id'))
        .order_by('-count', 'id')[:{limit_per_project}]
    )
    for group in groups:
        rows.append({{'pipeline_id': pipeline_id, **group}})

print(json.dumps(rows))
"""
    stdout = _run_python_in_service("uwsgi", script)
    payload_line = stdout.strip().splitlines()[-1]
    return json.loads(payload_line)


def _is_config_path(path: str) -> bool:
    lower = path.lower()
    name = Path(path).name.lower()
    config_suffixes = (
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".tf",
        ".tfvars",
        ".hcl",
        ".env",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".sh",
        ".bash",
    )
    return (
        name == "dockerfile"
        or name.startswith("docker-compose")
        or lower.endswith(config_suffixes)
        or "/deploy/" in lower
        or lower.startswith("deploy/")
    )


def _code_flow_tools(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    base = {
        "pipeline_id": group["pipeline_id"],
        "file_path": group["file_path"],
    }
    line = group["line"]
    return [
        ("classify_file", dict(base)),
        ("extract_function", {**base, "line_number": line}),
        ("find_imports", dict(base)),
        ("find_decorators", {**base, "line_number": line}),
        ("find_identifiers", {**base, "line_number": line}),
    ]


def _config_flow_tools(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    base = {
        "pipeline_id": group["pipeline_id"],
        "file_path": group["file_path"],
    }
    line = group["line"]
    return [
        ("classify_file", dict(base)),
        ("classify_environment", dict(base)),
        ("extract_config_block", {**base, "line_number": line}),
        ("extract_env_variables", dict(base)),
        ("find_related_configs", dict(base)),
    ]


def _tools_for_group(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if _is_config_path(group["file_path"]):
        return _config_flow_tools(group)
    return _code_flow_tools(group)


def _candidate_trace_identifiers(payload: Any, limit: int = 2) -> list[str]:
    if not isinstance(payload, dict):
        return []
    reads = payload.get("reads") or []
    candidates: list[str] = []
    for value in reads:
        if not isinstance(value, str):
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
            continue
        if value not in candidates:
            candidates.append(value)
        if len(candidates) >= limit:
            break
    return candidates


_RESERVED_WORDS = frozenset({
    "void", "null", "undefined", "true", "false", "return", "new",
    "this", "class", "if", "else", "for", "while", "switch", "case",
    "int", "float", "double", "char", "bool", "string", "var", "let", "const",
})


def _candidate_function_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    for pattern in FUNCTION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(2) if len(match.groups()) == 2 else match.group(1)
        if name.lower() in _RESERVED_WORDS:
            continue
        return name
    return None


def run_mcp_audit(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups_json = json.dumps(groups)
    script = f"""
import json
import os
import re
import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

GROUPS = json.loads({groups_json!r})
FUNCTION_PATTERNS = [
    re.compile(r"\\bdef\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\("),
    re.compile(r"\\bfunction\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*\\("),
    re.compile(r"\\b([A-Za-z_][A-Za-z0-9_]*)\\s*:\\s*function\\s*\\("),
    re.compile(r"\\b([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(?:async\\s+)?\\([^)]*\\)\\s*=>"),
    re.compile(r"\\b([A-Za-z_][A-Za-z0-9_:<>]*)::([A-Za-z_][A-Za-z0-9_]*)\\s*\\("),
]

def is_config_path(path: str) -> bool:
    lower = path.lower()
    name = path.rsplit('/', 1)[-1].lower()
    return (
        name == 'dockerfile'
        or name.startswith('docker-compose')
        or lower.endswith((
            '.yml', '.yaml', '.json', '.toml', '.tf', '.tfvars', '.hcl',
            '.env', '.ini', '.cfg', '.conf', '.properties', '.sh', '.bash',
        ))
        or '/deploy/' in lower
        or lower.startswith('deploy/')
    )

def code_flow_tools(group):
    base = {{
        'pipeline_id': group['pipeline_id'],
        'file_path': group['file_path'],
    }}
    line = group['line']
    return [
        ('classify_file', dict(base)),
        ('extract_function', {{**base, 'line_number': line}}),
        ('find_imports', dict(base)),
        ('find_decorators', {{**base, 'line_number': line}}),
        ('find_identifiers', {{**base, 'line_number': line}}),
    ]

def config_flow_tools(group):
    base = {{
        'pipeline_id': group['pipeline_id'],
        'file_path': group['file_path'],
    }}
    line = group['line']
    return [
        ('classify_file', dict(base)),
        ('classify_environment', dict(base)),
        ('extract_config_block', {{**base, 'line_number': line}}),
        ('extract_env_variables', dict(base)),
        ('find_related_configs', dict(base)),
    ]

def tools_for_group(group):
    if is_config_path(group['file_path']):
        return config_flow_tools(group)
    return code_flow_tools(group)

def parse_text_payload(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return text

def candidate_trace_identifiers(payload, limit=2):
    if not isinstance(payload, dict):
        return []
    reads = payload.get('reads') or []
    candidates = []
    for value in reads:
        if not isinstance(value, str):
            continue
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', value):
            continue
        if value not in candidates:
            candidates.append(value)
        if len(candidates) >= limit:
            break
    return candidates

def candidate_function_name(payload):
    if not isinstance(payload, dict):
        return None
    text = payload.get('text')
    if not isinstance(text, str) or not text.strip():
        return None
    for pattern in FUNCTION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if len(match.groups()) == 2:
            return match.group(2)
        return match.group(1)
    return None

def detect_anomalies(tool_name, group, payload):
    anomalies = []
    path = group['file_path']
    if tool_name == 'extract_function' and isinstance(payload, dict):
        text = payload.get('text', '')
        meta = payload.get('meta', {{}})
        code_on_line = meta.get('code_on_line')
        if isinstance(code_on_line, str) and code_on_line.strip() in {{'{{', '}}'}}:
            anomalies.append('code_on_line_only_brace')
        if isinstance(code_on_line, str) and len(code_on_line.splitlines()) > 8:
            anomalies.append('code_on_line_too_large')
        if path.endswith(('.tsx', '.jsx')) and 'Unsupported file extension' in text:
            anomalies.append('unsupported_tsx_extract')
    if tool_name == 'find_identifiers':
        if isinstance(payload, dict):
            reads = payload.get('reads') or []
            writes = payload.get('writes') or []
            if path.endswith(('.tsx', '.jsx')) and payload.get('language') is None:
                anomalies.append('tsx_identifiers_missing_language')
            if not reads and not writes:
                anomalies.append('identifiers_empty')
            if set(writes) & {{'BroadcastChannel', 'COOKIE_POLICY_CHANNEL'}}:
                anomalies.append('identifiers_constants_marked_as_writes')
        elif isinstance(payload, str) and 'Unsupported file extension' in payload:
            anomalies.append('unsupported_tsx_identifiers')
    if tool_name == 'trace_identifier_backward' and isinstance(payload, dict):
        reads = payload.get('reads') or []
        writes = payload.get('writes') or []
        if reads and writes and set(reads) == set(writes):
            anomalies.append('trace_self_referential_assignment')
    if tool_name == 'classify_file' and isinstance(payload, dict):
        result_type = payload.get('type')
        if ('.min.' in path or '/tinymce/' in path or '/jquery' in path) and result_type == 'production':
            anomalies.append('third_party_asset_marked_production')
    if tool_name == 'find_related_configs' and isinstance(payload, dict):
        if payload.get('relationship') == 'references_origin' and payload.get('file', '').endswith('.sh'):
            anomalies.append('shell_script_false_related_config')
    if tool_name == 'find_route_to_function' and isinstance(payload, dict):
        target_file = payload.get('file', '')
        if ('.min.' in target_file or '/tinymce/' in target_file) and payload.get('pattern'):
            anomalies.append('route_to_vendor_asset')
    return anomalies

async def call_and_store(session, entry, tool_name, args):
    result = await session.call_tool(tool_name, args)
    texts = [getattr(item, 'text', '') for item in result.content]
    payload = parse_text_payload(texts[0]) if texts else None
    record = {{
        'tool': tool_name,
        'args': args,
        'is_error': result.isError,
        'payload': payload,
        'anomalies': detect_anomalies(tool_name, entry['group'], payload),
    }}
    entry['results'].append(record)
    return record

async def main():
    headers = {{}}
    token = os.environ.get('MCP_AUTH_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {{token}}'
    report = []
    async with streamablehttp_client('http://127.0.0.1:8000/mcp', headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            for group in GROUPS:
                entry = {{
                    'group': group,
                    'results': [],
                }}
                base_results = {{}}
                for tool_name, args in tools_for_group(group):
                    base_results[tool_name] = await call_and_store(session, entry, tool_name, args)
                if is_config_path(group['file_path']):
                    report.append(entry)
                    continue
                identifiers_payload = base_results.get('find_identifiers', {{}}).get('payload')
                for identifier in candidate_trace_identifiers(identifiers_payload):
                    await call_and_store(
                        session,
                        entry,
                        'trace_identifier_backward',
                        {{
                            'pipeline_id': group['pipeline_id'],
                            'file_path': group['file_path'],
                            'line_number': group['line'],
                            'identifier': identifier,
                        }},
                    )
                function_name = candidate_function_name(base_results.get('extract_function', {{}}).get('payload'))
                if function_name:
                    await call_and_store(
                        session,
                        entry,
                        'find_callers',
                        {{
                            'pipeline_id': group['pipeline_id'],
                            'file_path': group['file_path'],
                            'function_name': function_name,
                        }},
                    )
                    await call_and_store(
                        session,
                        entry,
                        'find_route_to_function',
                        {{
                            'pipeline_id': group['pipeline_id'],
                            'function_name': function_name,
                        }},
                    )
                    await call_and_store(
                        session,
                        entry,
                        'find_definition',
                        {{
                            'pipeline_id': group['pipeline_id'],
                            'symbol_name': function_name,
                        }},
                    )
                report.append(entry)
    print(json.dumps(report))

anyio.run(main)
"""
    stdout = _run_python_in_service("context-extractor-mcp", script)
    payload_line = stdout.strip().splitlines()[-1]
    return json.loads(payload_line)


def summarize(report: list[dict[str, Any]]) -> dict[str, Any]:
    anomaly_counts: dict[str, int] = {}
    error_count = 0
    tool_counts: dict[str, int] = {}
    for entry in report:
        for result in entry["results"]:
            tool_name = result["tool"]
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            if result["is_error"]:
                error_count += 1
            for anomaly in result["anomalies"]:
                anomaly_counts[anomaly] = anomaly_counts.get(anomaly, 0) + 1
    return {
        "groups": len(report),
        "tool_errors": error_count,
        "tool_counts": dict(sorted(tool_counts.items())),
        "anomalies": dict(sorted(anomaly_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit live MCP behavior across grouped findings.")
    parser.add_argument("--limit-per-project", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    groups = fetch_group_manifest(limit_per_project=args.limit_per_project)
    report = run_mcp_audit(groups)
    summary = summarize(report)
    payload = {
        "summary": summary,
        "report": report,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"saved_report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
