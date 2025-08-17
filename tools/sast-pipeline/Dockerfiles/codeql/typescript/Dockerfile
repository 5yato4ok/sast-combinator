FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git unzip jq \
     && rm -rf /var/lib/apt/lists/*

# Install CodeQL CLI
ARG CODEQL_VERSION=2.18.4
RUN mkdir -p /opt/codeql && \
        curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
        unzip -q /tmp/codeql.zip -d /opt && \
        rm /tmp/codeql.zip && \
        ln -s /opt/codeql*/codeql /usr/local/bin/codeql

# Install query packs for LANGUAGE
RUN codeql pack install codeql/javascript-queries

WORKDIR /workspace
COPY analyze.sh /usr/local/bin/analyze.sh
RUN chmod +x /usr/local/bin/analyze.sh

ENTRYPOINT ["/usr/local/bin/analyze.sh"]
