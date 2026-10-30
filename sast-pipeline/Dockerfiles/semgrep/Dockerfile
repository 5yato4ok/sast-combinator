FROM ubuntu:24.04

# Pinned: an unpinned install silently changes the analyzer on every image rebuild.
ARG SEMGREP_VERSION=1.183.0

RUN sed -i 's|http://archive.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g; s|http://security.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g' /etc/apt/sources.list.d/ubuntu.sources && \
    apt-get update && \
    apt-get install -y python3-pip curl git ca-certificates && \
    pip install --no-cache-dir "semgrep==${SEMGREP_VERSION}" --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Read back per run into the AnalyzerBuild record (pipeline/analyzer_runner.py).
LABEL aist.tool.version="semgrep ${SEMGREP_VERSION}"

WORKDIR /workspace

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
