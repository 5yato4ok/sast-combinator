FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    git python3 python3-pip curl sudo jq docker.io && \
    pip3 install pyyaml && \
    apt-get clean

WORKDIR /app

COPY analyzer_runner.py /app/
COPY config/analyzers.yaml /app/config/analyzers.yaml
COPY Dockerfiles/builder/run_inside_builder.py /app/
COPY Dockerfiles/builder/builder-entrypoint.sh /app/
COPY Dockerfiles /app/Dockerfiles

ENV PYTHONPATH=/app

RUN chmod +x /app/builder-entrypoint.sh

ENTRYPOINT ["/app/builder-entrypoint.sh"]
