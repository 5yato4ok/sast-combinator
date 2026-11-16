# horusec/Dockerfile
FROM horuszup/horusec-cli:latest

USER root
# analyze.sh reads the report's status and normalizes it for import.
RUN apk add --no-cache jq
WORKDIR /workspace

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]