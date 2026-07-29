# SAST pipeline runtime

This package prepares a source workspace, runs the selected analyzers, and
returns their reports to AIST. Product admission, tenant authorization, finding
review, and durable pipeline state remain in the Django control plane.

For the reader-facing architecture, see the parent repository's
`docs/architecture/sast-pipeline-runtime.md`.

## Execution model

1. The builder container executes the project initialization script and exposes
   the prepared source tree.
2. Selected `simple` or `builder` analyzers run in their configured images and
   write result files to the shared output directory.
3. `agent-bridge` analyzers run through the platform's local AI bridge after the
   builder stage.
4. `standalone` providers, such as DAST, use their own executor and do not join
   the SAST analyzer fan-out.
5. The platform imports declared result files and persists analyzer outcomes.

The canonical analyzer catalog is
`pipeline/config/analyzers.yaml`. Each entry declares its runtime type, image,
time class, supported languages, importer scan type, result filename, and
required environment.

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
