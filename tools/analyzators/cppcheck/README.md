# Cppcheck(v2.17.1)

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
cd docker
docker build -t cppcheck:2.17.1 .
```

## Run

```bash
docker run --rm -v "$PWD:/src" cppcheck:2.17.1
```

## Custom Run 

```bash
docker run --rm -v "$PWD:/src" cppcheck:2.17.1 \
  cppcheck -j8 \
           --output-format=sarif \
           --output-file=result.sarif .
```
