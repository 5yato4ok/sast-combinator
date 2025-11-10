# Semgrep

## What is Semgrep?

[Semgrep](https://semgrep.dev/) is a lightweight static analysis tool
designed for developers.  It uses structured abstract syntax tree
(AST) patterns to find code that violates best practices or contains
security vulnerabilities.  Semgrep can be run as part of your CI
pipeline or from the command line and supports both community rules
and custom rules written in a simple YAML format.

Semgrep’s documentation lists a wide range of **general availability
(GA) languages**, including C#, Go, Java, JavaScript, Python,
TypeScript, C/C++, Kotlin, Ruby, Scala, Swift, Rust, PHP, Terraform,
JSON and YAML.  For these languages Semgrep
provides cross‑file data‑flow analysis and an extensive library of
pre‑built rules.  Beta or experimental languages (not enabled by
default) include Bash, Dockerfile and others.

## Running Semgrep

The pipeline includes a Docker image under `Dockerfiles/semgrep` that
installs the Semgrep CLI and wraps it in an `analyze.sh` script.  To
scan your project in the pipeline you must set the environment
variable `SEMGREP_APP_TOKEN` in your `.env` file.  The builder passes
both `PROJECT_PATH` and `SEMGREP_APP_TOKEN` into the Semgrep container;
you do not need to invoke the container manually.  The `analyze.sh`
script runs `semgrep ci` with the appropriate options to generate a
report.

If you wish to use Semgrep outside of this pipeline, refer to the
[official quickstart guide](https://semgrep.dev/docs/quickstart/) for
instructions on installation, authentication and invocation.  The
pipeline image follows the same principles but does not depend on the
public `semgrep/semgrep` image.

## Supported checks

Semgrep’s rule library covers thousands of security, correctness and
style patterns across supported languages.  Below are a few example
use cases drawn from the official documentation:

* **Ban dangerous APIs:** Semgrep can detect usage of high‑risk
  functions or APIs.  For example, it ships rules to flag React’s
  `dangerouslySetInnerHTML` call, which can lead to cross‑site
  scripting【30781551751786†L63-L81】.

* **Detect tainted data flows:** Semgrep’s dataflow engine can trace
  user‑supplied input flowing into dangerous functions.  One example
  rule flags when untrusted data is passed into a sandbox’s `run()`
  method in an ExpressJS application【30781551751786†L83-L93】.

* **Detect security violations:** Rules can detect when security
  mechanisms are disabled, such as disabling automatic HTML escaping
  in Django templates【30781551751786†L94-L104】.

* **Scan configuration files:** Semgrep natively supports JSON and
  YAML and includes rules to spot insecure settings in configuration
  files—such as skipped TLS verification in Kubernetes manifests【30781551751786†L105-L112】.

* **Enforce authentication patterns:** You can enforce project‑specific
  authentication patterns; for instance, a rule can detect Flask
  routes that lack a required authentication decorator【30781551751786†L118-L127】.

These examples illustrate the breadth of Semgrep’s rule ecosystem.
Semgrep also supports writing custom rules in YAML and provides
features like cross‑file data‑flow analysis and framework‑specific
checks.  See the
[Semgrep documentation](https://semgrep.dev/docs/) for up‑to‑date
information about available rules and language support.
