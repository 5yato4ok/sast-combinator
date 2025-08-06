# SAST Pipeline

## Overview

This repository contains a SAST (Static Application Security Testing) pipeline that can build a target C/C++ project in an isolated container, generate a `compile_commands.json` file, and run one or more static analyzers against the built project.

The pipeline is designed to be flexible:

* Add new analyzers without modifying core logic
* Analyze any compatible project by adding build script

### Pipeline Stages:

1. **Builder Stage**: Prepares the build environment, clones the project, installs dependencies, builds via CMake, and generates `compile_commands.json`. Exposes the filesystem via Docker volumes for reuse.
2. **Analyzer Stage**: Executes each analyzer in its own container inside the builder. Thanks to Docker's `--volumes-from`, analyzers inherit volumes from the builder and can access build artifacts, includes, and write results.

The entry point is `run_pipeline.py`, which builds the builder image, starts the builder container, and runs configured analyzers.

---

## Running the Pipeline

### Prerequisites:

* **Install Docker**: Both the host and builder require Docker
* **Prepare Project**: TBD

### Steps:

```bash
# Optionally export to force fresh rebuild of project
export FORCE_REBUILD=1

python3 run_pipeline.py
```

This will:

* Build the builder image from `Dockerfiles/builder/Dockerfile`
* Run the builder container with mounts:

  * `project_path` → `/workspace`
  * `output_dir` → `/shared/output`
  * `/var/run/docker.sock` (for launching analyzer containers)

* During run it will firstly prepare the environment for building and analyzing the project
* Then it will launch analyses by analyzers, described in config `analyzers.yaml`

Set `FORCE_REBUILD=1` to force fresh clone; otherwise, `git pull` is used.

---

## Adding a New Analyzer

An analyzers configuration is stored in `analyzers.yaml`. Example:

```yaml
analyzers:
  - name: mytool
    type: simple         # or builder
    image: sast-mytool
    input: /src
    time_class: medium
    env:
      - MY_TOOL_TOKEN
```

### Steps:

1. **Dockerfile**:

   * Create under `Dockerfiles/mytool`
   * Install dependencies and set `WORKDIR /workspace`
   * Copy `analyze.sh` and set as entrypoint

2. **analyze.sh**:

```bash
#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
mkdir -p "$OUTPUT_DIR"
mytool --input "$INPUT_DIR" --output "$OUTPUT_DIR/report.sarif"
```

3. **Build Context**:

   * Directory should contain everything needed for reproducible build

4. **Update `analyzers.yaml`** with tool definition

### Notes:

* Use `type: simple` if the analyzer does not need build artifacts
* Use `type: builder` (e.g., for `codechecker`) if it needs full build context
* Use `env:` to pass API tokens/secrets to analyzers

---

## Adding a New Project

 !!! 
 TBD

---

## How Volumes and Nested Containers Work

### Builder Container:

* Mounts project at `/workspace`
* Clones source into `/workspace/build-tmp/nx_open`
* Builds with CMake and generates `compile_commands.json` at `/workspace/build-tmp/nx_open/build`

### Analyzer Container:

* Is launched from within builder using host's Docker socket
* Uses `--volumes-from` to inherit builder container’s volumes

This ensures:

* Full access to build files, headers, and libraries (e.g., `/usr`, `/usr/local`)
* Valid paths in `compile_commands.json` inside analyzer
* Persistent output to host

---

## Entry Points

* **`run_pipeline.py`**: Top-level orchestrator
* **`project_builder.py`**: Defines `build_environment()` and handles builder container setup
* **`builder-entrypoint.sh`**: Inside builder, clones project, builds it, and invokes `run_inside_builder.py`
* **`run_inside_builder.py`**: Applies optional filtering and calls `run_selected_analyzers()`
* **`analyzer_runner.py`**: Parses `analyzers.yaml`, builds images, and runs analyzer containers

---

## Example: Adding SuperLint Analyzer

1. Create:

```
Dockerfiles/superlint/
├── Dockerfile
└── analyze.sh
```

2. Update `analyzers.yaml`:

```yaml
analyzers:
  - name: superlint
    type: simple
    image: sast-superlint
    input: /src
    time_class: fast
```

3. Run:

```bash
python3 run_pipeline.py
```

Reports appear in `/tmp/sast_output/superlint_result.sarif`

---

## Notes

* Assumes project uses CMake
* Slow analyzers (`time_class: slow`) can be skipped by setting `exclude_slow=True`
* Use `FORCE_REBUILD` judiciously: it forces a clean clone, else `git pull` is used
