# Semgrep analyzer

The image runs the bundled Semgrep CLI in local scan mode:

```text
semgrep scan --json --json-output=<output-file>
```

No Semgrep account token is required by this wrapper. Rule selection follows
the rules packaged or configured in the image/runtime environment.

The analyzer script accepts:

```bash
/analyze.sh <input-dir> <output-dir> [output-filename]
```

The default result is `semgrep_result.json`, imported as `Semgrep JSON Report`.
An explicit filename supplied by the pipeline overrides the default.
