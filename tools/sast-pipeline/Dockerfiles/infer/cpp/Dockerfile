FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates xz-utils jq python3 \
    && rm -rf /var/lib/apt/lists/*


ARG INFER_VERSION=v1.2.0
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*; \
    curl -fsSL -o /tmp/infer.tar.xz \
      "https://github.com/facebook/infer/releases/download/${INFER_VERSION}/infer-linux-x86_64-${INFER_VERSION}.tar.xz"; \
    xz -t /tmp/infer.tar.xz; \
    tar -C /opt -xJf /tmp/infer.tar.xz; \
    ln -sf "/opt/infer-linux-x86_64-${INFER_VERSION}/bin/infer" /usr/local/bin/infer; \
    rm -f /tmp/infer.tar.xz

WORKDIR /app
COPY analyze.sh /app/analyze.sh
COPY convert_report.py /app/convert_report.py
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]
