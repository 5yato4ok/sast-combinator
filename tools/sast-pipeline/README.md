# SAST Pipeline

## Overview

This repository contains a **static application security testing (SAST) pipeline** for
building projects and running multiple analyzers in an isolated Docker
environment.  The pipeline is split into two stages:

* **Builder stage:** the pipeline starts a dedicated container to
  clone and **configure** your project.  The configuration step can
  generate a `compile_commands.json` for C/C++ projects but does not
  necessarily build the entire code base.  The project’s location
  inside the container is communicated to analyzers via the
  environment variable `PROJECT_PATH`; if a compilation database is
  produced, its location is provided in `COMPILE_COMMANDS_PATH`.  The
  compiler used to generate the database is recorded in
  `COMPILER_PATH`.  These variables are set by your project
  configuration script and consumed by analyzers later on.

* **Analyzer stage:** each analyzer runs in its own Docker image and
  analyses the built source tree.  Analyzers are configured via the
  file `config/analyzers.yaml` (see below).  The pipeline launches
  analyzers in order of their `time_class` to optimise run time.  The
  `analyzer_runner.py` script uses Docker’s `--volumes-from` option to
  mount the builder container’s file system into each analyzer
  container so that tools can access the build outputs.

Each analyzer writes its report into the output directory using the
format appropriate for that tool.  **Not every analyzer produces a
SARIF file**: for example, Semgrep and Snyk can emit
[SARIF](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html),
but CodeChecker writes its findings to a JSON file.
Refer to the corresponding analyzer README files for details about
output formats and filenames.

## Prerequisites

* **Python 3.8+** – the pipeline uses Python scripts for orchestration.
* **Docker** – all analyzers and the builder run in containers.  Make
  sure your user has permission to run Docker commands.

## Running the pipeline

To run the pipeline, execute the `run_pipeline.py` script from the
`tools/sast-pipeline` directory of this repository.  **It is important
to run the script from within the project directory**; the pipeline
depends on relative paths when mounting volumes.  The script accepts
two required arguments:

```bash
python3 run_pipeline.py \
  --script input_projects/<project>_config.sh \
  --output_dir /absolute/path/to/results
```

* `--script` – path to the project configuration script.  See the
  section on *Adding a new project* below for how to write this
  script.  The script is executed inside the builder container to
  prepare the source code and set environment variables.
* `--output_dir` – absolute path on the host where analysis results
  (e.g. SARIF or JSON) will be written.

The pipeline will automatically load environment variables defined in
a `.env` file located at the repository root.  This is handled by
`python-dotenv` in `run_pipeline.py`.  Place any tokens required
by analyzers (e.g., `SNYK_TOKEN`, `SEMGREP_APP_TOKEN`) into this file.

To skip analyzers marked as _slow_, you can pass the `--exclude_slow`
flag when running the pipeline.

## Configuring analyzers

Analyzers are defined in `config/analyzers.yaml`.  Each entry
specifies the analyzer name, type, Docker image, classification
(`time_class`), whether it is enabled, and any environment variables
required.  For example, the bundled configuration includes analyzers
such as `cppcheck`, `semgrep`, `codechecker`, `snyk`, etc., and
associates variables like `SNYK_TOKEN`, `SEMGREP_APP_TOKEN`,
`COMPILE_COMMANDS_PATH` and `COMPILER_PATH` with the appropriate
analyzer.  To enable or disable an analyzer,
change its `enabled:` field.  You may add additional analyzers by
defining a new entry with a unique `name` and pointing it to a Docker
image built in `Dockerfiles/<analyzer>`.

### Adding a new analyzer

1. **Add an entry to `config/analyzers.yaml`:** provide a `name`, set
   `type` to `simple` for analyzers that read files directly or
   `builder` for analyzers that reuse the builder container.  Specify
   the Docker image under `image:` and set any required environment
   variables under the `env:` section.

2. **Create a Dockerfile:** create a directory `Dockerfiles/<name>`
   containing a `Dockerfile` that installs the analyzer.  See the
   existing directories (e.g., `Dockerfiles/semgrep` or
   `Dockerfiles/codechecker`) for examples.  Your Dockerfile should
   install the tool and copy an `analyze.sh` script that executes the
   analysis.  **The script is free to choose its output format**
   (SARIF, JSON, etc.) and destination.  The pipeline copies all
   generated files from `/tmp` in the analyzer container into the
   output directory.  Consult other analyzer directories for
   conventions.

3. **Reconfigure the project (optional):** on the next pipeline
   run the analyzer runner will build the image if it does not
   already exist.  If you need to re-run your project configuration
   script (for example after changing dependencies or build flags),
   pass argument `--force_rebuild` when invoking `run_pipeline.py`.  This
   removes any previously generated configuration artifacts inside the
   builder container and reruns your project script.
   It does **not** rebuild Docker images; to rebuild images, delete
   them via Docker before running the pipeline again.

Refer to the existing analyzer directories for guidance on how to
structure your `Dockerfile` and `analyze.sh`.

## Adding a new project

To analyse a new repository you need to provide a **project
configuration script**.  You must provide the path via the
`--script` argument when running `run_pipeline.py`. The pipeline copies the script into the builder
container as `project_config.sh` and executes it.
Your project script must:

1. **Check out or update the source code.**  Clone the repository
   into the build directory (inside the container) or update it if
   already present.  For example, the `nx_open_project_config.sh`
   script clones a Git repository into `/build/nx-open` and updates
   it on subsequent runs.

2. **Define mandatory variables.**  At minimum export
   `PROJECT_PATH` pointing to the directory containing the source code.
   If the project can generate a compilation database
   (`compile_commands.json`), set `COMPILE_COMMANDS_PATH` to its
   absolute path.  The builder sets `COMPILER_PATH` automatically by
   inspecting the compilation database.  If your project
   requires compilation and can provide `compile_commands.json`
   export `NON_COMPILE_PROJECT=0`.

3. **Configure the project (if necessary).**  If your analyzers need
   a compilation database (for example, CodeChecker), your script
   should **configure** the project using CMake or a similar tool to
   generate `compile_commands.json`.  A full build is not required.
   See the provided project configuration examples for details on
   generating a compilation database.

4. **Set additional environment variables (optional).**  If your
   analyzers require tokens or configuration, ensure those variables
   are set in the `.env` file at the repository root.  The pipeline
   automatically passes variables listed in `env:` sections of
   `analyzers.yaml` to the appropriate containers.

Once your script is ready, run the pipeline as shown above.  The
project will be built inside a builder container and each enabled
analyzer will run against the checked‑out source tree.  Remember to
execute the pipeline from the `tools/sast-pipeline` directory so that
relative mounts work correctly.
