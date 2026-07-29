# Cppcheck 2.17.1

## Features

- Detects bugs, memory issues, style/performance problems
- No build system required (can work without `compile_commands.json`)
- Outputs SARIF

## Types of Checks

Cppcheck can detect:

- Memory leaks
- Null pointer dereferencing
- Uninitialized variables
- Buffer overflows
- Unused functions or variables
- Redundant or dead code
- Style and performance issues
- Coding standard violations

Image runs [Cppcheck](http://cppcheck.sourceforge.net/), a static analysis tool for C/C++ code, built from source with rules support.

## Build image

```bash
docker build -t cppcheck:2.17.1 .
```

## Run

The image entrypoint accepts source directory, output directory, and optional
result filename:

```bash
docker run --rm \
  -v "/absolute/path/to/source:/workspace:ro" \
  -v "/absolute/path/to/output:/shared/output" \
  cppcheck:2.17.1 /workspace /shared/output cppcheck_result.sarif
```
