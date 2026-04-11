# Cloud Mail VPS Edition

This repository runs Cloud Mail on a VPS with a Python backend, Python SMTP service, PostgreSQL, and Redis.

## Components

- `app`: FastAPI backend and Python SMTP service
- `mail-vue`: original Vue frontend
- `tempmail-postgres`: PostgreSQL database
- `tempmail-redis`: Redis service
- `deploy`: Caddy reverse proxy configuration

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://127.0.0.1`.

## Environment variables

- `CLOUD_MAIL_DOMAIN`: comma-separated mail domains
- `CLOUD_MAIL_ADMIN`: default admin email
- `CLOUD_MAIL_ADMIN_PASSWORD`: default admin password
- `CLOUD_MAIL_JWT_SECRET`: JWT signing secret
- `DATABASE_URL`: PostgreSQL SQLAlchemy URL
- `REDIS_URL`: Redis connection URL
- `SMTP_GATEWAY_TOKEN`: shared secret between SMTP and API
- `SMTP_HOST` / `SMTP_PORT`: SMTP listener bind address and port
- `SMTP_API_BASE`: internal API base URL used by the SMTP service

## Notes

- The runtime backend is implemented in Python under `app/`.
- SMTP traffic is accepted by `tempmail-smtp` and pushed to `/internal/smtp/receive`.
- Static frontend assets are built from `mail-vue` and served by the Python app behind Caddy.
