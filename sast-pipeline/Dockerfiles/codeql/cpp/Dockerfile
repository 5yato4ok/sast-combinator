FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://archive.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g; s|http://security.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git unzip jq \
    && rm -rf /var/lib/apt/lists/*

# Install CodeQL CLI
ARG CODEQL_VERSION=2.27.3
RUN test "$(dpkg --print-architecture)" = amd64 || (echo "This CodeQL runtime requires linux/amd64" >&2; exit 1)
ENV PATH="/opt/sast-tools/codeql:${PATH}"
LABEL aist.tool.version="${CODEQL_VERSION}"
RUN mkdir -p /opt/sast-tools && \
        curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
        unzip -q /tmp/codeql.zip -d /opt/sast-tools && \
        rm /tmp/codeql.zip

# Install query packs for LANGUAGE
# Pack version must be a release built for CODEQL_VERSION
# (ghcr manifest label com.github.codeql.cli.version).
ARG CODEQL_QUERIES_VERSION=1.9.2
ENV CODEQL_QUERIES_VERSION="${CODEQL_QUERIES_VERSION}"
RUN codeql pack download "codeql/cpp-queries@${CODEQL_QUERIES_VERSION}"

WORKDIR /workspace
COPY analyze.sh /usr/local/bin/analyze.sh
COPY capture.sh build.sh /opt/sast-tools/codeql/
RUN chmod +x /usr/local/bin/analyze.sh /opt/sast-tools/codeql/capture.sh /opt/sast-tools/codeql/build.sh

ENTRYPOINT ["/usr/local/bin/analyze.sh"]
