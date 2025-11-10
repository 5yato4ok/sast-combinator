# Horusec Analyzer

Runs **Horusec** against the project (multi-language; Python-first). Outputs SARIF to `/shared/output/horusec.sarif`.

## Quick start

```bash
docker build -t horusec-analyzer .
docker run --rm -v "$PWD":/workspace -v "$PWD/out":/shared/output \  horusec-analyzer /analyze.sh /workspace /shared/output
```

## Output
- `horusec.sarif`
- `horusec.log`
