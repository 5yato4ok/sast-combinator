# CodeQL analyzer

CodeQL uses a separate image for each supported language family. Each image
creates a CodeQL database from the mounted source, runs its security query
suite, and writes SARIF to the shared output directory.

## Quick start

The pipeline builds the image selected by the language-specific catalog entry.
For a standalone Python run from this directory:

```bash
docker build -t codeql-python-analyzer python
docker run --rm \
  -v "/absolute/path/to/source:/workspace:ro" \
  -v "/absolute/path/to/output:/shared/output" \
  codeql-python-analyzer /workspace /shared/output codeql_python.sarif
```

Available image directories are `python`, `cpp`, `csharp`, `go`, `java`,
`javascript`, `ruby`, and `swift`. Catalog enablement and supported-language
selection remain authoritative; some language entries may be disabled.

## Output

The result filename is language-specific, for example `codeql_python.sarif` or
`codeql_javascript.sarif`, and is declared by the analyzer catalog.
