# CodeChecker

## What is CodeChecker?

[CodeChecker](https://codechecker.readthedocs.io/) is a static analysis
infrastructure built on top of the LLVM/Clang tooling ecosystem.  It
wraps and orchestrates a number of analysis tools such as:

* **Clang Static Analyzer** – the original clang-based analyser for
  C and C++.
* **Clang‑Tidy** – a collection of modern C/C++ lint checks.
* **Statistical analysis** – heuristics that look for patterns in
  pointer usage and other dangerous constructs.
* **Cppcheck** – a stand‑alone static analyser for C/C++ code.
* **GCC Static Analyzer** and **Facebook Infer** – additional
  analyzers that can be run through the CodeChecker interface.

Supports C/C++ analyzers.

## Running CodeChecker

The pipeline provides a Docker image for CodeChecker under
`Dockerfiles/codechecker`.  The `analyze.sh` script in this directory
expects the following environment variables:

* **`PROJECT_PATH`** – absolute path to the source tree inside the
  container (set by the builder stage).
* **`COMPILE_COMMANDS_PATH`** – absolute path to the project’s
  `compile_commands.json`.  Without this file the C/C++ analysers
  cannot run.
* **`COMPILER_PATH`** – path to the C/C++ compiler used during the
  build.  The builder determines this automatically.

The script invokes `CodeChecker analyze` followed by
`CodeChecker parse`.  In this pipeline the output is written to a
JSON file named `codechecker_result.json`,
which the pipeline copies into your specified results directory.

When running CodeChecker outside of this pipeline you must mount
your project and pass the environment variables shown above.  See the
official [CodeChecker documentation](https://codechecker.readthedocs.io)
for details on using the CLI.

## Supported languages and checks

When run through this pipeline, CodeChecker focuses on **C and C++**
projects.  It leverages tools from the LLVM/Clang ecosystem and
additional analyzers such as Cppcheck.  Some example checks exposed
via Clang’s static analyzer include:

* **Null dereference:** detects dereferencing of a null pointer,
  reported by `clang-analyzer-core.NullDereference`.
* **Stack address escape:** warns when the address of a stack
  variable escapes the function scope, which can lead to undefined
  behaviour (`clang-analyzer-core.StackAddressEscape`).
* **Undefined binary operator result:** checks for operations that
  yield undefined results, such as shifting by more than the width of
  an integer (`clang-analyzer-core.UndefinedBinaryOperatorResult`).

These are only a few of the hundreds of checkers available through
Clang Static Analyzer and Clang‑Tidy.  You can list all available
checkers and enable or disable them using `CodeChecker checkers` and
`CodeChecker analyze --enable <checker>` as described in the
documentation.  CodeChecker also supports
additional analyses via Cppcheck and other tools.  Because it relies
on a compilation database, the pipeline only runs CodeChecker against
compiled languages like C and C++; it does not analyse scripting
languages.
