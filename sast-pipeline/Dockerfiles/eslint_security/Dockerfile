FROM node:20-alpine

RUN apk add --no-cache bash git

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev --no-audit --no-fund
COPY analyze.sh /app/analyze.sh
COPY eslint-security.config.mjs /app/eslint-security.config.mjs
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]
