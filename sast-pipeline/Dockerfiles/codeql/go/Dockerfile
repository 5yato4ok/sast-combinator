FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://archive.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g; s|http://security.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git unzip jq \
     && rm -rf /var/lib/apt/lists/*

# CodeQL analyses Go by building it, so the toolchain must satisfy the project's go.mod.
# Ubuntu's golang-go is 1.18 and fails every module that declares a newer language version.
ARG GO_VERSION=1.27.3
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"
# A go.mod newer than GO_VERSION resolves through the module cache the builder populated;
# with GOPROXY=off and no cached toolchain the build fails loudly instead of reaching the network.
ENV GOTOOLCHAIN=auto

# Install CodeQL CLI
ARG CODEQL_VERSION=2.27.3
RUN mkdir -p /opt/codeql && \
        curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
        unzip -q /tmp/codeql.zip -d /opt && \
        rm /tmp/codeql.zip && \
        ln -s /opt/codeql*/codeql /usr/local/bin/codeql

# Install query packs for LANGUAGE
# Pack version must be a release built for CODEQL_VERSION
# (ghcr manifest label com.github.codeql.cli.version).
ARG CODEQL_QUERIES_VERSION=1.6.13
RUN codeql pack download "codeql/go-queries@${CODEQL_QUERIES_VERSION}"

WORKDIR /workspace
COPY analyze.sh /usr/local/bin/analyze.sh
RUN chmod +x /usr/local/bin/analyze.sh

ENTRYPOINT ["/usr/local/bin/analyze.sh"]
