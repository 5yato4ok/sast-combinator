ARG BUILDER_BASE_IMAGE=ubuntu:22.04
FROM ${BUILDER_BASE_IMAGE}

USER root

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

ARG PROJECT_CONFIG_PATH

RUN apt-get update && apt-get install -y \
    git wget python3 python3-pip python3-venv python3-yaml python3-dotenv curl sudo jq docker.io && \
    apt-get clean

WORKDIR /app

COPY pipeline/ /app/pipeline
COPY ${PROJECT_CONFIG_PATH} /app/project_config.sh
COPY Dockerfiles/builder/run_inside_builder.py /app/
COPY Dockerfiles/builder/builder-entrypoint.sh /app/
COPY Dockerfiles /app/Dockerfiles

ENV PYTHONPATH=/app

RUN chmod +x /app/builder-entrypoint.sh

# Shared with analyzers through --volumes-from; reclaimed with --rm.
VOLUME ["/shared/build"]

ENTRYPOINT ["/app/builder-entrypoint.sh"]
