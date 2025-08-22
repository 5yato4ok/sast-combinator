import json, sys, os

json_in, out = sys.argv[1], sys.argv[2]
findings = []

def sev_map(sev: str) -> str:
    s = (sev or "").upper()
    if s in ("BLOCKER","CRITICAL","HIGH","ERROR"): return "High"
    if s in ("MEDIUM","MODERATE","WARNING","WARN"): return "Medium"
    if s in ("LOW","INFO","INFORMATIONAL"):        return "Low"
    return "Medium"

data = {}
if os.path.isfile(json_in) and os.path.getsize(json_in) > 0:
    try:
        data = json.load(open(json_in, "r", encoding="utf-8"))
    except Exception:
        data = {}

issues = data if isinstance(data, list) else data.get("issues", [])
for it in issues:
    bug_type = it.get("bug_type") or it.get("type") or "Infer issue"
    msg      = it.get("qualifier") or it.get("message") or ""
    filep    = it.get("file") or it.get("source") or ""
    line     = it.get("line") or it.get("line_number") or None
    sev      = sev_map(it.get("severity") or it.get("kind") or "")

    # Формируем запись DefectDojo Generic Findings
    findings.append({
        "title": bug_type,
        "description": msg,
        "severity": sev,
        "file_path": filep if filep else None,
        "line": int(line) if isinstance(line, int) or (isinstance(line, str) and line.isdigit()) else None,
    })

with open(out, "w", encoding="utf-8") as f:
    json.dump({"findings": findings}, f, ensure_ascii=False)

print(f"[INFO] Converted {len(findings)} issues -> {out}")