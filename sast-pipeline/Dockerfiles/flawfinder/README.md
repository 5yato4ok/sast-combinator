# FlawFinder

Image runs [Flawfinder](https://dwheeler.com/flawfinder/), a static analysis tool
for C/C++ that searches for insecure function calls and related programming
flaws.

## Features

- No build system required (can work without `compile_commands.json`)
- Outputs SARIF

## Checks

- Dangerous functions (e.g., `strcpy`, `gets`, `sprintf`)
- Format string vulnerabilities
- Buffer overflows
- Insecure random number usage
- Hardcoded credentials and secrets
- Race conditions
- Input validation issues

Each issue is assigned a **risk level from 0 to 5** (higher means more dangerous).

## Build image

```bash
docker build -t flawfinder .
```

## Run

```bash
docker run --rm \
  -v "/absolute/path/to/source:/workspace:ro" \
  -v "/absolute/path/to/output:/shared/output" \
  flawfinder /workspace /shared/output flawfinder_result.sarif
```
