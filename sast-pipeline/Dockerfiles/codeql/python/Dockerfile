FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates python3 python3-pip curl git unzip jq \
     && rm -rf /var/lib/apt/lists/*

# Install CodeQL CLI
ARG CODEQL_VERSION=2.27.3
RUN mkdir -p /opt/codeql && \
        curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
        unzip -q /tmp/codeql.zip -d /opt && \
        rm /tmp/codeql.zip && \
        ln -s /opt/codeql*/codeql /usr/local/bin/codeql

# Pack version must be a release built for CODEQL_VERSION
# (ghcr manifest label com.github.codeql.cli.version).
ARG CODEQL_QUERIES_VERSION=1.8.13
RUN codeql pack download "codeql/python-queries@${CODEQL_QUERIES_VERSION}"

WORKDIR /workspace
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
