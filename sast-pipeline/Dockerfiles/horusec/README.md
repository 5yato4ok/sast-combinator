# Horusec analyzer

The wrapper runs Horusec against the prepared project and requests JSON output:

```bash
/analyze.sh /workspace /shared/output horusec_result.json
```

The default output is `horusec_result.json`, imported as `Horusec Scan`. Horusec
uses the mounted Docker socket declared by its analyzer catalog entry.
