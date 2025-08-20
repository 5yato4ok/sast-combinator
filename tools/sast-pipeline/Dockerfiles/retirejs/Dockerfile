FROM node:20-alpine

# minimal tools
RUN apk add --no-cache bash git

# Retire.js CLI
RUN npm i -g retire

WORKDIR /app

# runner
COPY analyze.sh /app/analyze.sh
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]
