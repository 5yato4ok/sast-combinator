# Pipeline execution runtime

This package provides the library and command-line execution boundary for SAST
and standalone providers such as DAST. AIST workers load the package directly;
it is not a long-lived service. Product admission, tenant authorization,
capacity, recovery policy, finding review, and durable pipeline state remain in
the Django control plane.

For the reader-facing architecture, see the parent repository's
`docs/architecture/sast-pipeline-runtime.md`.

## Execution model

1. One provider registry selects the execution path from a caller-supplied
   execution identity and typed input.
2. SAST prepares a workspace through the builder, then runs selected `simple`,
   `builder`, or `agent-bridge` analyzers and returns partitioned reports.
3. A `standalone` provider uses its own executor. DAST creates one connector
   container and returns a bounded outcome with a recovery checkpoint; it does
   not join the SAST analyzer fan-out.
4. The caller imports reports or persists the returned terminal outcome and
   checkpoint.

The canonical analyzer catalog is
`pipeline/config/analyzers.yaml`. Each entry declares its runtime type, image,
time class, supported languages, importer scan type, result filename, and
required environment. Standalone catalog entries and command handlers must also
match the provider registry before command-line dispatch is allowed.

## Command-line run

Run from this directory so Docker build contexts and mounts resolve correctly:

```bash
python3 run_pipeline.py sast \
  --script /absolute/path/to/project_config.sh \
  --output_dir /absolute/path/to/results \
  --languages python \
  --time_class_level slow
```

Useful selection and rebuild options are:

- `--analyzers semgrep bearer` — select explicit analyzers;
- `--time_class_level fast|medium|slow` — when no analyzers are named, select those through that class;
- `--project_force_rebuild` — rebuild the prepared project workspace;
- `--rebuild_images` — rebuild builder and analyzer images;
- `--config path.yml` — load the same arguments from YAML.

Credentials belong in environment variables named by the selected analyzer's
catalog entry. Do not store analyzer tokens in project scripts or result files.

## Add an analyzer

An analyzer addition is complete only when it includes:

1. `Dockerfiles/<name>/Dockerfile`;
2. `Dockerfiles/<name>/analyze.sh`;
3. one catalog entry in `pipeline/config/analyzers.yaml` with the exact importer
   name and result file;
4. regression coverage for image configuration and output behavior.

Use an existing analyzer of the same runtime type as the template. The script
must accept input directory, output directory, and optional output filename in
the established order.

## Project initialization script

The script clones or prepares the requested revision and exports `PROJECT_PATH`.
Compiled projects may also export `COMPILE_COMMANDS_PATH`, `COMPILER_PATH`, and
the flags consumed by their analyzers. The script must be repeatable because a
worker retry can prepare the same request again.

## Build capture in the initialized builder

C/C++ CodeQL captures an explicit project build in the initialized builder,
then finalizes and analyzes its database in a separate analyzer container.
Project init installs dependencies and configures the build; it does not install
CodeQL or query packs. For a project whose CMake tooling comes from Python
requirements, the relevant part of init can be:

```bash
cd "$PROJECT_PATH"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
export NON_COMPILE_PROJECT=0
export SAST_BUILD_COMMAND='cmake --build build --clean-first --parallel "$JOBS"'
```

Keep the existing source acquisition and revision selection in init. The build
command runs under Bash with `errexit`, `nounset` and `pipefail`, in `PROJECT_PATH`,
inheriting the exported environment from init. It can invoke a script, native
build preset or multiple targets in one command. Use a clean or forced build and
disable compiler caches when needed: only compilations observed under capture
enter the database. Missing commands, failed capture and failed analysis are
reported as analyzer failures. Check CodeQL diagnostics and measured coverage
before treating a successful report as complete analysis.

The C/C++ runtime is currently packaged for Linux amd64. Use a compatible native
worker for binary-dependent verification; an ARM Docker Desktop run does not
establish compatibility with it. Separate incompatible platform or compiler
configurations into independent runs. The execution package does not discover
project targets or split databases automatically.

### Resource policy

| Setting | Where to set it | Meaning |
| --- | --- | --- |
| `base_image` | Explicit argument to `configure_project_run_analyses`, from the caller's versioned project configuration | Ubuntu/Debian-compatible builder base; omitted or empty retains `ubuntu:22.04`. Pin by digest for repeatability. The shared Dockerfile requires `apt`; arbitrary distributions are not supported |
| `SAST_BUILDER_MEMORY`, `SAST_BUILDER_CPUS` | Worker environment or the execution caller's `additional_env` | Docker limits for init and capture; must be supplied before the builder starts |
| `SAST_ANALYZER_MEMORY`, `SAST_ANALYZER_CPUS` | Worker environment, `additional_env`, or exported by init | Docker limits for analyzer containers |
| `CODEQL_RAM_MB` | `additional_env` or exported by init | CodeQL finalize/query memory budget in MB, distinct from the container limit |
| `JOBS` | Launch environment or init export; defaults to the builder's CPU-derived value when unset | Build parallelism and CodeQL query threads |

Docker accepts values such as `128g` for memory and `8` for CPUs. No memory limit
is added when unset. Choose budgets below available worker capacity, allowing
headroom for other services and concurrent containers. Builder and analyzer
containers have separate cgroups; their memory limits are not a combined budget.
Splitting the build into targets does not bound the final database analysis.

### Adapter contract

A build analyzer opts into capture by declaring this catalog shape:

```yaml
type: builder
build_runtime:
  root: /opt/sast-tools/example
  capture: /opt/sast-tools/example/capture.sh
optional_env: []
```

The analyzer image owns the runtime directory, executable capture adapter and
final analysis entrypoint. The runtime must contain its capture dependencies
and be compatible with the builder's OS libraries and architecture. The package
mounts an empty tool volume read-only in the builder before init. Only after
init selects the build analyzer does it populate the volume through Docker's
native image-directory copying and pin execution to the resolved image ID.
Source-only projects do not build or run skipped analyzer images. Tool
provisioning, capture and analysis failures are recorded per analyzer and allow
other selected analyzers to proceed.

The capture adapter receives `source_directory artifact_directory`. It runs
inside the builder and consumes `SAST_BUILD_COMMAND`. On success, the analyzer
entrypoint receives the usual `source_directory output_directory output_filename`
plus `artifact_directory` as the fourth argument. The artifact format belongs to
the analyzer. Intermediate artifacts live in a temporary directory on the
builder's anonymous `/shared/build` Docker volume, inherited by the analyzer.
The directory is removed after each analyzer, including on failure, and Docker
reclaims the volume when its containers are removed. Reports stay in run output;
the temporary tool volume is removed when execution ends. Optional environment names are
forwarded to the final container only when present; required names remain in
the existing `env` list. No project identity or project-specific target logic is
part of this contract.

The native integration test builds the real builder, initializes a CMake project
with two targets, captures with CodeQL and checks a SARIF finding. Run it inside
a Linux amd64 container with Docker access and a writable copy of this package:

```bash
SAST_TEST_CODEQL_IMAGE=codeql-cpp:test \
  python3 -m pytest tests/pipeline_tests/test_build_runtime_integration.py -v
```

The supplied image tag is built or refreshed from the local adapter sources.
All test workspaces use Docker volumes; no host checkout or host toolchain is
required by the child containers.
