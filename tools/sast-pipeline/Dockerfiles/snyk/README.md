# Snyk Code

## What is Snyk Code?

[Snyk](https://snyk.io/) provides a suite of developer‑centric
security tools.  **Snyk Code** is its static application security
testing (SAST) product, which scans application source code for
vulnerabilities, insecure coding patterns and other quality issues.

Snyk Code currently supports at least Java, JavaScript,
TypeScript, Python, C#, and C/C++.

## Running Snyk Code

The pipeline’s `Dockerfiles/snyk` image installs the Snyk CLI and wraps
it in an `analyze.sh` script.  To run Snyk Code inside the pipeline
you must provide the following environment variables (usually via a
`.env` file):

* **`PROJECT_PATH`** – absolute path to the source tree in the
  container.
* **`SNYK_TOKEN`** – your personal or organisational Snyk API token.

The `analyze.sh` script invokes `snyk code test` with the
`--sarif` flag and writes the results to a SARIF file in `/tmp`.
When you run the pipeline, the script automatically mounts your
project and passes `SNYK_TOKEN` to the CLI; you do not need to
interact with the container directly.

## Supported languages and example rules

Its rule set covers many common vulnerability classes.  Here are a
few examples taken from the official list of Snyk Code security rules:

* **SQL injection:** detects unsafe construction of SQL queries and is
  applicable to languages including C#, C++, Go, Java, JavaScript,
  Kotlin, PHP, Python, Ruby, Rust, Scala, Swift and Visual Basic.

* **Server‑Side Request Forgery (SSRF):** flags patterns where
  attacker‑controlled input is used to make network requests (for
  example, unsanitized URLs passed to HTTP clients).  Snyk lists
  SSRF rules for languages such as Apex, C#, C++, Go, Java,
  JavaScript, Kotlin, PHP, Python, Rust, Scala, Swift and Visual
  Basic.

* **Use of hardcoded credentials:** identifies hardcoded passwords or
  API keys embedded in code.  These rules apply to many languages
  including Apex, C#, Go, Java, JavaScript, Kotlin, PHP, Python,
  Ruby, Rust, Scala, Swift and Visual Basic.

This is only a small selection of the vulnerability types covered by
Snyk Code.  The full list includes categories such as cross‑site
scripting, insecure deserialization, unsafe reflection, cryptographic
issues and memory corruption.  Consult the [Snyk Code security
rules](https://docs.snyk.io/scan-with-snyk/snyk-code/snyk-code-security-rules)
for an up‑to‑date catalogue.
