# Pysa Analyzer (Pyre taint analysis)

Runs **Pysa** (via Pyre) against a Python project. Outputs taint findings to `/shared/output/pysa.json`.

## Quick start

```bash
docker build -t pysa-analyzer .
docker run --rm -v "$PWD":/workspace -v "$PWD/out":/shared/output \
  -e ANALYZER=pysa pysa-analyzer /analyze.sh /workspace /shared/output
```
> `ANALYZER` is optional here and only used for consistency across tools.

## Environment
- None required. If `.pyre_configuration` is missing, it will be created minimally.

## Output
- `pysa.json` (taint analysis results)
- `pysa.log` (tool log)
