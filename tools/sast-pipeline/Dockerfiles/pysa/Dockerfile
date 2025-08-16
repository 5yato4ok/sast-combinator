FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git curl jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir pyre-check
WORKDIR /
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
