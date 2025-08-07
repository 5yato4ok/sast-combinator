import os
import json
import argparse


def load_sarif_findings(sarif_path):
    with open(sarif_path, 'r', encoding='utf-8') as f:
        sarif = json.load(f)

    findings = []
    for run in sarif.get("runs", []):
        for result in run.get("results", []):
            location = result.get("locations", [{}])[0]
            artifact_location = location.get("physicalLocation", {}).get("artifactLocation", {})
            uri = artifact_location.get("uri", "")
            findings.append(uri.replace("\\", "/"))  # Normalize Windows paths
    return findings


def analyze_testcases(root_dir, sarif_path):
    sarif_findings = load_sarif_findings(sarif_path)
    negative_matched = []
    positive_matched = 0
    positive_not_matched = 0

    for dirpath, _, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith((".cpp", ".c")):
                file_path = os.path.join(dirpath, file)
                base_name = os.path.splitext(file)[0]
                parent_folder = os.path.basename(os.path.dirname(file_path))

                json_path = os.path.join(dirpath, f"{base_name}.json")
                if not os.path.exists(json_path):
                    continue

                try:
                    with open(json_path, 'r', encoding='utf-8') as jf:
                        meta = json.load(jf)
                except json.JSONDecodeError:
                    continue

                search_pattern = f"{parent_folder}/{file}"
                found_in_sarif = any(search_pattern in finding for finding in sarif_findings)

                if meta.get("positive", False):
                    if found_in_sarif:
                        positive_matched += 1
                    else:
                        positive_not_matched += 1
                else:
                    if found_in_sarif:
                        print(f"[MATCH] {search_pattern}")
                        negative_matched.append(search_pattern)

    print("\n--- Summary ---")
    print(f"Negative matches (positive: false and found in SARIF): {len(negative_matched)}")
    print(f"Positive matches (positive: true and found in SARIF): {positive_matched}")
    print(f"Positive not found in SARIF: {positive_not_matched}")
    total = len(negative_matched) + positive_matched + positive_not_matched
    print(f"Total test cases considered: {total}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze test cases and check which ones appear in the SARIF report."
    )
    parser.add_argument(
        "--root", required=True,
        help="Path to the root directory containing test cases"
    )
    parser.add_argument(
        "--sarif", required=True,
        help="Path to the SARIF file containing analyzer results"
    )

    args = parser.parse_args()
    analyze_testcases(args.root, args.sarif)


if __name__ == "__main__":
    main()
