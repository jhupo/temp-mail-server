# Cloud Mail VPS Edition

This repository keeps the original `maillab/cloud-mail` frontend, but the runtime backend is now fully Python for VPS deployment.

- frontend: `/mail-vue`
- api backend: `/app`
- smtp service: `/app/smtp_server.py`

## Current direction

- keep the original cloud-mail frontend
- replace the old Worker backend with Python
- run on a VPS with Docker
- receive SMTP on `25`
- expose web on `80` / `443`
- persist state in PostgreSQL and Redis

## Current VPS baseline

- Python backend: FastAPI
- Python SMTP service
- PostgreSQL database
- Redis session/cache service
- frontend built from `mail-vue`

## Runtime layout

```text
temp-mail-server
├── app             Python FastAPI backend and SMTP service
├── mail-vue        Vue frontend
├── deploy          Caddy config
└── docker-compose.yml
```

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

```text
http://127.0.0.1
```

## Environment

Available variables:

- `CLOUD_MAIL_DOMAIN` comma-separated public mail domains
- `CLOUD_MAIL_ADMIN` admin account email
- `CLOUD_MAIL_ADMIN_PASSWORD` admin password
- `CLOUD_MAIL_JWT_SECRET` JWT signing secret
- `DATABASE_URL` PostgreSQL connection URL
- `REDIS_URL` Redis connection URL
- `SMTP_GATEWAY_TOKEN` shared secret between SMTP and API
- `SMTP_HOST` SMTP bind host
- `SMTP_PORT` SMTP bind port
- `SMTP_API_BASE` internal API base URL for SMTP delivery

## Current note

Current VPS deployment includes:

- `tempmail-api` Python backend
- `tempmail-smtp` Python SMTP service on `25`
- `tempmail-postgres` PostgreSQL
- `tempmail-redis` Redis
- `web` reverse proxy on `80` / `443`
- runtime state persisted in Docker volumes
