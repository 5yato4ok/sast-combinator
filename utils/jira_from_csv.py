#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create Jira epics and issues from a CSV file with Russian headers:
- "Категория"     -> Epic name
- "Подкатегория"  -> Component (created if missing)
- "Требование"    -> Issue summary
- "Описание"      -> Issue description
- "Приоритет"     -> Priority (e.g., Highest/High/Medium/Low/Lowest or numeric)
- "SAST"          -> Optional label (added if non-empty)

Configuration via environment variables:
  JIRA_BASE_URL       e.g. https://your-domain.atlassian.net
  JIRA_EMAIL          e.g. you@example.com (Jira account email)
  JIRA_API_TOKEN      Atlassian API token (https://id.atlassian.com/manage/api-tokens)
  JIRA_PROJECT_KEY    e.g. ABC
  JIRA_ISSUE_TYPE     (optional, default: Story) issue type for requirements (Story/Task/Bug)
  DRY_RUN             (optional: "1" to print actions only)

Usage:
  python3 jira_from_csv.py /mnt/data/reqs.csv

Notes:
- Script auto-discovers custom field IDs for "Epic Link" and "Epic Name".
- If "Epic Link" is not available (Team-managed projects), it falls back to the Agile API to add issues to an epic.
- For Company-managed projects, "Epic Name" is required on Epic creation.
"""

import csv
import json
import os
import sys
import time
import typing as t
import requests
from dotenv import load_dotenv
load_dotenv(dotenv_path="/Users/butkevichveronika/work/sast-combinator/tools/utils/.env")

BASE = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
EMAIL = os.environ.get("JIRA_EMAIL", "")
TOKEN = os.environ.get("JIRA_API_TOKEN", "")
PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")
ISSUE_TYPE = os.environ.get("JIRA_ISSUE_TYPE", "Story")
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"

if not (BASE and EMAIL and TOKEN and PROJECT_KEY):
    print("ERROR: missing required env vars JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY", file=sys.stderr)
    sys.exit(2)

AUTH = (EMAIL, TOKEN)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

FIELDS_CACHE = None
COMPONENTS_CACHE = {}

def _req(method: str, path: str, **kwargs):
    url = path if path.startswith("http") else f"{BASE}{path}"
    r = requests.request(method, url, auth=AUTH, headers=HEADERS, timeout=30, **kwargs)
    if r.status_code >= 400:
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text}", response=r)
    return r

def fetch_all_fields() -> t.List[dict]:
    global FIELDS_CACHE
    if FIELDS_CACHE is None:
        FIELDS_CACHE = _req("GET", "/rest/api/3/field").json()
    return FIELDS_CACHE

def find_field_id(field_name: str) -> t.Optional[str]:
    for f in fetch_all_fields():
        if (f.get("name") or "").strip().lower() == field_name.strip().lower():
            return f.get("id")
    return None

def jql_search(jql: str, max_results: int = 1) -> t.List[dict]:
    payload = {"jql": jql, "maxResults": max_results, "fields": ["summary", "issuetype", "components"]}
    r = _req("POST", "/rest/api/3/search", json=payload)
    return r.json().get("issues", [])

def get_or_create_component(project_key: str, name: str) -> dict:
    if not name:
        return {}
    key = name.lower().strip()
    if key in COMPONENTS_CACHE:
        return COMPONENTS_CACHE[key]
    # list components (paginated)
    start_at = 0
    while True:
        r = _req("GET", f"/rest/api/3/project/{project_key}/components?startAt={start_at}")
        items = r.json()
        if isinstance(items, dict) and "values" in items:
            items_list = items["values"]
            is_paged = True
        else:
            items_list = items
            is_paged = False
        for c in items_list:
            if (c.get("name") or "").strip().lower() == key:
                COMPONENTS_CACHE[key] = c
                return c
        if is_paged and r.headers.get("X-Has-More-Items") == "true":
            start_at += len(items_list)
        else:
            break
    # create if missing
    payload = {"name": name, "project": project_key}
    if DRY_RUN:
        print(f"[DRY] Would create component: {name}")
        comp = {"name": name}
    else:
        comp = _req("POST", "/rest/api/3/component", json=payload).json()
    COMPONENTS_CACHE[key] = comp
    return comp

def ensure_epic(project_key: str, epic_name: str) -> str:
    """Return Epic key, creating if needed. Handles 'Epic Name' field id dynamically."""
    epic_name = (epic_name or "").strip()
    if not epic_name:
        return ""

    # try find existing by summary=epic_name and issuetype=Epic in this project
    jql = f'project = "{project_key}" AND issuetype = Epic AND summary ~ "{epic_name}" ORDER BY created DESC'
    found = jql_search(jql, max_results=5)
    for issue in found:
        if (issue.get("fields", {}).get("summary") or "").strip().lower() == epic_name.lower():
            return issue["key"]

    epic_name_field = find_field_id("Epic Name")
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": epic_name,
            "issuetype": {"name": "Epic"}
        }
    }
    if epic_name_field:
        payload["fields"][epic_name_field] = epic_name

    if DRY_RUN:
        print(f"[DRY] Would create EPIC: {epic_name}")
        # Fake key
        return f"{project_key}-EPIC-NEW"
    res = _req("POST", "/rest/api/3/issue", json=payload).json()
    return res["key"]

def add_issue_to_epic(epic_key: str, issue_key: str, epic_link_field_id: t.Optional[str]) -> None:
    """Prefer setting Epic Link custom field; fallback to Agile 'add to epic' endpoint."""
    if not epic_key or not issue_key:
        return
    if epic_link_field_id:
        payload = {"update": {epic_link_field_id: [{"set": epic_key}]}}
        if DRY_RUN:
            print(f"[DRY] Would set Epic Link {epic_link_field_id}={epic_key} for {issue_key}")
            return
        _req("PUT", f"/rest/api/3/issue/{issue_key}", json=payload)
        return
    # fallback via Agile API
    body = {"issues": [issue_key]}
    if DRY_RUN:
        print(f"[DRY] Would add {issue_key} to epic {epic_key} via Agile API")
        return
    _req("POST", f"/rest/agile/1.0/epic/{epic_key}/issue", json=body)

def normalize_priority(val: t.Any) -> t.Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # mapping = {
    #     "1": "Highest", "highest": "Highest",
    #     "2": "High", "high": "High",
    #     "3": "Medium", "medium": "Medium",
    #     "4": "Low", "low": "Low",
    #     "5": "Lowest", "lowest": "Lowest",
    #     "critical": "Highest", "blocker": "Highest", "p1": "Highest", "p2": "High", "p3": "Medium", "p4": "Low", "p5": "Lowest",
    #     "критично": "Highest", "высокий": "High", "средний": "Medium", "низкий": "Low"
    # }
    mapping = {
        "обязательное" : "High",
        "важное": "Medium",
        "опциональное": "Low"
    }
    return mapping.get(s.lower(), s)

def adf_paragraph(lines: list[str])->dict:
    content = []
    for i, line in enumerate(lines):
        if i>0:
            content.append({"type":"hardBreak"})
        if line:
            content.append({"type":"text","text":line})
    if not content:
        content = [{"type":"text","text":""}]
    return {"type":"paragraph","content":content}

def adf_from_text(text:str)->dict:
    text = (text or "").replace("\r\n","\n").replace("\r","\n")
    blocks = text.split("\n\n") if text else [""]
    doc = {
        "type":"doc",
        "version":1,
        "content":[ adf_paragraph(block.split("\n")) for block in blocks ]
    }
    # Ensure at least one paragraph with text node (some Jira instances are picky)
    if not doc["content"]:
        doc["content"]=[adf_paragraph([""])]
    return doc

def build_description(summary: str, description: str, subcat: str, sast: str):
    parts = []
    if description:
        parts.append(description)
    extras = []
    if subcat:
        extras.append(f"*Подкатегория:* {subcat}")
    if sast:
        extras.append(f"*SAST:* {sast}")
    if extras:
        parts.append("\n".join(extras))
    return adf_from_text("\n\n".join(parts) if parts else summary)

def create_issue(project_key: str, issue_type: str, summary: str, description: str,
                 component_name: t.Optional[str], priority: t.Optional[str],
                 labels: t.Optional[t.List[str]],
                 epic_key: t.Optional[str], epic_link_field_id: t.Optional[str]) -> str:
    fields = {
        "project": {"key": project_key},
        "issuetype": {"name": issue_type},
        "summary": summary[:255] if summary else "(no summary)",
    }
    if description:
        fields["description"] = description
    if priority:
        fields["priority"] = {"name": priority}

    if component_name:
        labels.append(f"subcat:{component_name.replace(' ', '_')}")

    if labels:
        fields["labels"] = labels

    if epic_key:
        if epic_link_field_id:
            fields[epic_link_field_id] = epic_key
        else:
            fields["parent"] = {"key": epic_key}

    payload = {"fields": fields}
    if DRY_RUN:
        print(f"[DRY] Would create {issue_type}: {summary!r}")
        return f"{project_key}-NEW"
    res = _req("POST", "/rest/api/3/issue", json=payload).json()
    return res["key"]

def main(csv_path: str) -> None:
    epic_link_field_id = find_field_id("Epic Link")  # may be None (team-managed)
    created = 0
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            epic_name = (row.get("Категория") or "").strip()
            subcat = (row.get("Подкатегория") or "").strip()
            summary = (row.get("Требование") or "").strip()
            description = (row.get("Описание") or "").strip()
            priority = normalize_priority(row.get("Приоритет"))
            sast_val = (row.get("SAST") or "").strip()
            labels = []
            if sast_val:
                labels.append("SAST")
                # also add the value if not boolean-like
                if sast_val.lower() not in {"1","true","yes","да","y"}:
                    labels.append(f"sast:{sast_val}")

            if not summary:
                print(f"[WARN] Row {i}: empty 'Требование' — skipping")
                continue

            epic_key = ensure_epic(PROJECT_KEY, epic_name) if epic_name else ""
            body = build_description(summary, description, subcat, sast_val)
            issue_key = create_issue(PROJECT_KEY, ISSUE_TYPE, summary, body, subcat, priority, labels, epic_key, epic_link_field_id)

            created += 1
            if created % 20 == 0:
                time.sleep(0.5)  # be polite to API

    print(f"[OK] Created/processed {created} issues.")

if __name__ == "__main__":
    url = f"{os.environ['JIRA_BASE_URL']}/rest/api/3/issuetype"
    r = requests.get(url, auth=(os.environ['JIRA_EMAIL'], os.environ['JIRA_API_TOKEN']))
    for t in r.json():
        print(t["name"])
    # if len(sys.argv) < 2:
    #     print("Usage: python3 jira_from_csv.py /path/to/reqs.csv", file=sys.stderr)
    #     sys.exit(2)
    main("/Users/butkevichveronika/work/sast-combinator/tools/utils/reqs.csv")
