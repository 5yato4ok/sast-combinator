import json
import sys


def compare_licenses(update, ci):
    print(f"Comparing {update} with {ci}")
    with open(update, 'r') as f:
        update_licenses = json.load(f)
    with open(ci, 'r') as f:
        ci_licenses = json.load(f)
    return update_licenses, ci_licenses


compare_licenses(sys.argv[1], sys.argv[2])
