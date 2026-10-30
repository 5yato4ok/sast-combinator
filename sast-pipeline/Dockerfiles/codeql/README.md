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

## Version pinning

Each image pins both halves of the CodeQL toolchain:

- `ARG CODEQL_VERSION` — the CLI release from `github/codeql-cli-binaries`.
- `ARG CODEQL_QUERIES_VERSION` — the `codeql/<language>-queries` pack release.

A pack release declares the CLI it was built for. Query packs are published
ahead of the CLI, so an unpinned `codeql pack download` eventually resolves a
pack that refuses to run on the pinned CLI and the image build fails.

To move to a new CLI release, update `CODEQL_VERSION` in every language image
and set each `CODEQL_QUERIES_VERSION` to a pack release whose
`com.github.codeql.cli.version` matches:

```bash
TOKEN=$(curl -s "https://ghcr.io/token?service=ghcr.io&scope=repository:codeql/go-queries:pull" | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/vnd.oci.image.manifest.v1+json" \
     "https://ghcr.io/v2/codeql/go-queries/manifests/<pack-version>" \
  | jq -r '.annotations."com.github.codeql.cli.version"'
```

`tests/pipeline_tests/test_codeql_dockerfile_pins.py` enforces that both
versions stay pinned and that all images share one CLI version.
