FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

ARG PROJECT_CONFIG_PATH

RUN apt-get update && apt-get install -y \
    git python3 python3-pip curl sudo jq docker.io && \
    pip3 install pyyaml python-dotenv && \
    apt-get clean

WORKDIR /app

COPY analyzer_runner.py /app/
COPY docker_utils.py /app/
COPY config_utils.py /app/
COPY ${PROJECT_CONFIG_PATH} /app/project_config.sh
COPY Dockerfiles/builder/run_inside_builder.py /app/
COPY Dockerfiles/builder/builder-entrypoint.sh /app/
COPY Dockerfiles /app/Dockerfiles
COPY .env /app/

ENV PYTHONPATH=/app

RUN chmod +x /app/builder-entrypoint.sh

ENTRYPOINT ["/app/builder-entrypoint.sh"]
