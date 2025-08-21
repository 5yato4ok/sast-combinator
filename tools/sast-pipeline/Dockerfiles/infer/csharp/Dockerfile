FROM mcr.microsoft.com/infersharp:latest

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git unzip jq wget\
     && rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY analyze.sh /app/analyze.sh
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]