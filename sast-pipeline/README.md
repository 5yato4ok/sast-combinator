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
- `--time_class_level fast|medium|slow` — include analyzers through that class;
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
