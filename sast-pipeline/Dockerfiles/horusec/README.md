# Horusec analyzer

The wrapper runs Horusec against the prepared project and requests JSON output:

```bash
/analyze.sh /workspace /shared/output horusec_result.json
```

The default output is `horusec_result.json`, imported as `Horusec Scan`. The
wrapper fails the analyzer and removes the report when Horusec reports a
status other than `success`, and writes an empty finding list for a clean scan.
