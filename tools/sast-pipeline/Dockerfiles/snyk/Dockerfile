FROM node:20-slim

RUN apt-get update && apt-get install -y ca-certificates && \
    npm install -g snyk && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
