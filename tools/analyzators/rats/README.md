# RATS in Docker

This Docker image runs [RATS (Rough Auditing Tool for Security)](https://github.com/andrew-d/rough-auditing-tool-for-security), a security-focused static analyzer for C, C++, Perl, PHP, Python and Ruby source code.

---

## Checks:

- Dangerous C/C++ functions (e.g. `gets`, `strcpy`, `sprintf`)
- Race conditions like TOCTOU
- Format string vulnerabilities
- Input/output misuse
- Language-specific weaknesses in Perl, PHP, Python, Ruby

Uses different **warning levels** (`-w1`, `-w2`, `-w3`) to filter by severity.

---

## Build

```bash
cd docker
docker build -t rats-analyzer .
```

## Run

```bash
docker run --rm -v "$PWD:/src" rats-analyzer
```
