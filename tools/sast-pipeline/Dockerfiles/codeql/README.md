# CodeQL Analyzer

Builds a CodeQL DB and runs default queries, emitting SARIF to `/shared/output/codeql.sarif`.

## Quick start

```bash
docker build -t codeql-analyzer .
docker run --rm -v "$PWD":/workspace -v "$PWD/out":/shared/output \  -e CODEQL_LANGUAGE=python \  codeql-analyzer /analyze.sh /workspace /shared/output
```

## Environment
- `CODEQL_LANGUAGE` — one of: `python`, `cpp`, `csharp`, `javascript`, `typescript` (default auto-detects Python if *.py present)
- `CODEQL_DB_DIR` (optional)

## Output
- `codeql.sarif`
