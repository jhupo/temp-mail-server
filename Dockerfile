FROM node:22-bookworm

WORKDIR /app

COPY mail-vue /app/mail-vue
COPY mail-worker /app/mail-worker

WORKDIR /app/mail-vue
RUN npm install --legacy-peer-deps
RUN npm run build

WORKDIR /app/mail-worker
RUN npm install --legacy-peer-deps

EXPOSE 8000

CMD ["npx", "wrangler", "dev", "--config", "wrangler-vps.toml", "--local", "--persist-to", "/data", "--host", "0.0.0.0", "--port", "8000"]
