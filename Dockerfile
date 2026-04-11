FROM node:22-bookworm AS app-base

WORKDIR /app

COPY mail-vue /app/mail-vue
COPY mail-worker /app/mail-worker
COPY deploy/docker-entrypoint.sh /app/deploy/docker-entrypoint.sh

WORKDIR /app/mail-vue
RUN npm install --legacy-peer-deps
RUN npm run build

WORKDIR /app/mail-worker
RUN npm install --legacy-peer-deps

EXPOSE 8000

RUN chmod +x /app/deploy/docker-entrypoint.sh

CMD ["/app/deploy/docker-entrypoint.sh"]
