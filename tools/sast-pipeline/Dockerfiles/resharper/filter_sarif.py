#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import json
import re
import sys
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

KEY_RE = re.compile(
    r"/Default/CodeInspection/Highlighting/InspectionSeverities/=(?P<id>[^/]+)/@EntryValue"
)

def _get_attr_local_name(full_name: str) -> str:
    # attribute can be '{namespace}Key' or 'x:Key' or 'Key'
    if '}' in full_name:
        return full_name.split('}', 1)[1]
    if ':' in full_name:
        return full_name.split(':', 1)[1]
    return full_name

def extract_disabled_ids(dotsettings_path: Path) -> set[str]:
    """Return set of inspection IDs with DO_NOT_SHOW severity in the given .DotSettings."""
    try:
        tree = ET.parse(dotsettings_path)
    except ET.ParseError as e:
        raise SystemExit(f"ERROR: Failed to parse DotSettings XML: {e}")
    root = tree.getroot()

    disabled: set[str] = set()
    for el in root.iter():
        # Find attribute whose local name is 'Key'
        key_attr = None
        for attr_name, attr_val in el.attrib.items():
            if _get_attr_local_name(attr_name) == "Key":
                key_attr = attr_val
                break
        if not key_attr:
            continue
        m = KEY_RE.search(key_attr)
        if not m:
            continue
        inspection_id = m.group("id")
        val = (el.text or "").strip().upper()
        if val == "DO_NOT_SHOW":
            disabled.add(inspection_id)
    return disabled

def filter_sarif(input_path: Path, output_path: Path, disabled_ids: set[str], prune_rules: bool) -> dict:
    """Filter SARIF results and optionally prune rules. Returns a summary dict."""
    with input_path.open("r", encoding="utf-8") as fh:
        sarif = json.load(fh)

    total_runs = 0
    total_results = 0
    removed = 0

    for run in sarif.get("runs", []):
        total_runs += 1
        results = run.get("results", [])
        total_results += len(results)

        # Filter results
        kept_results = []
        for r in results:
            # Prefer 'ruleId' per SARIF spec; fall back to run.tool.driver.rules[ruleIndex] if needed.
            rid = r.get("ruleId")
            if rid is None and "ruleIndex" in r:
                # try to map index to rules if present
                try:
                    rules = run.get("tool", {}).get("driver", {}).get("rules", [])
                    idx = r["ruleIndex"]
                    if isinstance(idx, int) and 0 <= idx < len(rules):
                        rid = rules[idx].get("id")
                except Exception:
                    rid = None
            if rid in disabled_ids:
                removed += 1
                continue
            kept_results.append(r)
        run["results"] = kept_results

        if prune_rules:
            # Keep only rules that are still referenced by remaining results
            referenced: set[str] = set()
            for r in kept_results:
                rid = r.get("ruleId")
                if rid:
                    referenced.add(rid)
                elif "ruleIndex" in r:
                    # We'll rebuild ruleIndex after pruning
                    pass

            driver = run.get("tool", {}).get("driver", {})
            rules = driver.get("rules", [])
            if rules:
                new_rules = [rule for rule in rules if rule.get("id") in referenced or not referenced]
                # Rebuild mapping if we changed it notably
                if len(new_rules) != len(rules):
                    driver["rules"] = new_rules
                    # Also fix ruleIndex values
                    id_to_index = {rule.get("id"): i for i, rule in enumerate(new_rules)}
                    for r in kept_results:
                        if "ruleId" in r and r["ruleId"] in id_to_index:
                            r["ruleIndex"] = id_to_index[r["ruleId"]]
                        elif "ruleId" in r and "ruleIndex" in r and r["ruleId"] not in id_to_index:
                            r.pop("ruleIndex", None)

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(sarif, fh, ensure_ascii=False, indent=2)

    kept = total_results - removed
    return {
        "runs": total_runs,
        "results_before": total_results,
        "removed": removed,
        "results_after": kept,
        "disabled_ids_count": len(disabled_ids),
    }

def main(argv=None):
    p = argparse.ArgumentParser(description="Filter InspectCode SARIF using a .DotSettings profile (DO_NOT_SHOW severities).")
    p.add_argument("--dotsettings", required=True, type=Path, help=".DotSettings file path")
    p.add_argument("--input", required=True, type=Path, help="Input SARIF file (JSON)")
    p.add_argument("--output", required=True, type=Path, help="Output SARIF file path")
    p.add_argument("--prune-rules", action="store_true", help="Also remove rules that no longer have results and reindex ruleIndex")
    args = p.parse_args(argv)

    if not args.dotsettings.exists():
        raise SystemExit(f"DotSettings not found: {args.dotsettings}")
    if not args.input.exists():
        raise SystemExit(f"Input SARIF not found: {args.input}")

    disabled = extract_disabled_ids(args.dotsettings)
    if not disabled:
        print("WARNING: No DO_NOT_SHOW entries found in the DotSettings. Nothing to filter.", file=sys.stderr)

    summary = filter_sarif(args.input, args.output, disabled, args.prune_rules)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
