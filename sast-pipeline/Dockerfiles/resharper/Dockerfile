FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base tools
RUN sed -i 's|http://archive.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g; s|http://security.ubuntu.com/ubuntu|mirror://mirrors.ubuntu.com/mirrors.txt|g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    curl python3 ca-certificates coreutils unzip bash findutils gnupg wget apt-transport-https software-properties-common \
 && rm -rf /var/lib/apt/lists/*

# ReSharper Command Line Tools (official ZIP)
RUN curl -fSL "https://data.services.jetbrains.com/products/download?code=RSCLT&platform=linux" -o /tmp/rsc.zip \
 && mkdir -p /opt/resharper \
 && unzip -q /tmp/rsc.zip -d /opt/resharper \
 && rm /tmp/rsc.zip


COPY analyze.sh /analyze.sh
COPY profile.DotSettings /profile.DotSettings
COPY filter_sarif.py /filter_sarif.py

RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
