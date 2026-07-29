# Bearer analyzer

The wrapper runs `bearer scan` in JSON mode. It accepts input directory, output
directory, and an optional output filename:

```bash
/analyze.sh /workspace /shared/output bearer_result.json
```

The default output is `bearer_result.json`, imported as `Bearer CLI`. A non-zero
Bearer exit caused by findings is preserved as analyzer output rather than
being described as a SARIF result.
