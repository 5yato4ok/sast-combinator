FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base tools
RUN apt-get update && apt-get install -y \
    curl ca-certificates unzip bash findutils gnupg wget apt-transport-https software-properties-common \
 && rm -rf /var/lib/apt/lists/*

# ReSharper Command Line Tools (official ZIP)
RUN curl -fSL "https://data.services.jetbrains.com/products/download?code=RSCLT&platform=linux" -o /tmp/rsc.zip \
 && mkdir -p /opt/resharper \
 && unzip -q /tmp/rsc.zip -d /opt/resharper \
 && rm /tmp/rsc.zip


WORKDIR /workspace
COPY analyze.sh /workspace/analyze.sh

RUN chmod +x /workspace/analyze.sh

ENTRYPOINT ["/workspace/analyze.sh"]
