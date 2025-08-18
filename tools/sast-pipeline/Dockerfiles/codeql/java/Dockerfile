FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
#TODO: java version must be from project configuration
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git unzip jq openjdk-21-jdk \
 && rm -rf /var/lib/apt/lists/*

RUN curl -L -o /tmp/kotlin.zip \
      https://github.com/JetBrains/kotlin/releases/download/v1.9.25/kotlin-compiler-1.9.25.zip \
 && unzip /tmp/kotlin.zip -d /opt/ \
 && rm /tmp/kotlin.zip \
 && ln -sf /opt/kotlinc/bin/kotlinc /usr/local/bin/kotlinc \
 && ln -sf /opt/kotlinc/bin/kotlin /usr/local/bin/kotlin

# Install CodeQL CLI
ARG CODEQL_VERSION=2.18.4
RUN mkdir -p /opt/codeql && \
        curl -fsSL "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip && \
        unzip -q /tmp/codeql.zip -d /opt && \
        rm /tmp/codeql.zip && \
        ln -s /opt/codeql*/codeql /usr/local/bin/codeql

# Install query packs for LANGUAGE
RUN codeql pack download codeql/java-queries

WORKDIR /workspace
COPY analyze.sh /usr/local/bin/analyze.sh
RUN chmod +x /usr/local/bin/analyze.sh

ENTRYPOINT ["/usr/local/bin/analyze.sh"]
