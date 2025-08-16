FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://horusec.io/bin/install.sh | bash && mv /usr/local/bin/horusec /usr/bin/horusec


WORKDIR /

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh", "/workspace", "/shared/output"]
