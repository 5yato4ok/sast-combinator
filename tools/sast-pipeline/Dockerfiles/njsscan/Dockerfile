FROM python:3.11-alpine

RUN apk add --no-cache bash git
RUN pip install --no-cache-dir njsscan

WORKDIR /app
COPY analyze.sh /app/analyze.sh
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]
