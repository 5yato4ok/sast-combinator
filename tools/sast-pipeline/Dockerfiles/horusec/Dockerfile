# horusec/Dockerfile
FROM horuszup/horusec-cli:latest

USER root
WORKDIR /workspace

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]