FROM bearer/bearer:latest

WORKDIR /workspace
USER root

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh


ENTRYPOINT ["/analyze.sh"]
