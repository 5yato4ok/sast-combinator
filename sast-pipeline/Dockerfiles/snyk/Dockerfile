FROM node:20-slim

# Pinned: an unpinned install silently changes the analyzer on every image rebuild.
ARG SNYK_VERSION=1.1308.3

RUN apt-get update && apt-get install -y ca-certificates && \
    npm install -g "snyk@${SNYK_VERSION}" && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Read back per run into the AnalyzerBuild record (pipeline/analyzer_runner.py).
LABEL aist.tool.version="snyk ${SNYK_VERSION}"

WORKDIR /workspace

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
