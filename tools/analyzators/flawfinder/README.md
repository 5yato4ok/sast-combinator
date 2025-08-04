# FlawFinder

Image runs [Flawfinder](https://dwheeler.com/flawfinder/), , a simple static analysis tool for C/C++ that searches for insecure function calls and other common programming flaws.

## Features

- No build system required (can work without `compile_commands.json`)
- Outputs SARIF

## Checks:

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
cd docker
docker build -t flawfinder .
```

## Run

```bash
docker run --rm -v "$PWD:/src" flawfinder
```