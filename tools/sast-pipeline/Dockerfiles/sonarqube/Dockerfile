FROM sonarsource/sonar-scanner-cli:latest

# Add utils
RUN apk add --no-cache bash curl jq

WORKDIR /
COPY analyze.sh /analyze.sh
RUN chmod +x /analyze.sh

ENTRYPOINT ["/analyze.sh"]
