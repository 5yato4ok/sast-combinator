FROM node:20-alpine

RUN apk add --no-cache bash git


RUN npm i -g \
    eslint@^9 \
    @eslint/js@^9 \
    typescript@^5 \
    @typescript-eslint/parser@^8 \
    @typescript-eslint/eslint-plugin@^8 \
    eslint-plugin-security@^3 \
    eslint-plugin-no-unsanitized@^4 \
    @microsoft/eslint-formatter-sarif@^3

WORKDIR /app
COPY analyze.sh /app/analyze.sh
COPY eslint-security.config.mjs /app/eslint-security.config.mjs
RUN chmod +x /app/analyze.sh
ENV NODE_PATH=/usr/local/lib/node_modules

ENTRYPOINT ["/app/analyze.sh"]
