FROM node:20-alpine

RUN apk add --no-cache bash git

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev --no-audit --no-fund
COPY analyze.sh /app/analyze.sh
COPY eslint-security.config.mjs unresolvable-links.mjs /app/
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]
