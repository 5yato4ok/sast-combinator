# Bearer CLI Analyzer

Runs **Bearer CLI** and outputs SARIF to `/shared/output/bearer.sarif`.

## Quick start

```bash
docker build -t bearer-analyzer .
docker run --rm -v "$PWD":/workspace -v "$PWD/out":/shared/output \  bearer-analyzer /analyze.sh /workspace /shared/output
```

## Output
- `bearer.sarif`
- `bearer.log`
