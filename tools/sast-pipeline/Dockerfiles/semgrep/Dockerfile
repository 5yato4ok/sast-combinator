FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y python3-pip curl git ca-certificates && \
    pip install --no-cache-dir semgrep --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
