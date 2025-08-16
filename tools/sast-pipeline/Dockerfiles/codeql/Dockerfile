FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git unzip jq \
 && rm -rf /var/lib/apt/lists/*
ARG CODEQL_VERSION=2.18.4

RUN mkdir -p /opt/codeql && \
    curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
    unzip -q /tmp/codeql.zip -d /opt && rm /tmp/codeql.zip && \
    ln -s /opt/codeql*/codeql /usr/local/bin/codeql \

WORKDIR /workspace
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
