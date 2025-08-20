FROM node:20-alpine

RUN apk add --no-cache bash git

# ESLint + TS + security плагины + SARIF-форматтер
RUN npm i -g \
    eslint \
    @typescript-eslint/parser \
    @typescript-eslint/eslint-plugin \
    eslint-plugin-security \
    eslint-plugin-no-unsanitized \
    @microsoft/eslint-formatter-sarif

WORKDIR /app
COPY analyze.sh /app/analyze.sh
RUN chmod +x /app/analyze.sh

ENTRYPOINT ["/app/analyze.sh"]