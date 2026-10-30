# Pinned: ``latest`` silently crossed the v1 -> v2 major boundary on rebuild.
ARG BEARER_VERSION=v2.1.3
FROM bearer/bearer:${BEARER_VERSION}
ARG BEARER_VERSION

# Read back per run into the AnalyzerBuild record (pipeline/analyzer_runner.py).
LABEL aist.tool.version="bearer ${BEARER_VERSION}"

WORKDIR /workspace
USER root

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh


ENTRYPOINT ["/analyze.sh"]
