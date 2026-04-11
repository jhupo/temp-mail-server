# Cloud Mail VPS Edition

This repository now uses the original `maillab/cloud-mail` frontend directly, but the runtime backend has been switched to Python for VPS deployment.

- frontend: `/mail-vue`
- reference worker source: `/mail-worker`
- runtime backend: `/app`

Current direction:

- keep the original cloud-mail frontend
- replace the runtime backend with Python
- run on a VPS with Docker
- receive SMTP on `25` / `587`
- expose web on `80` / `443`

## Current VPS baseline

- Python backend: FastAPI
- local SQLite database at `/data/cloud-mail.db`
- frontend built from `mail-vue`
- SMTP gateway forwards inbound mail to Python backend over HTTP

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
- `CLOUD_MAIL_JWT_SECRET` JWT signing secret
- `CLOUD_MAIL_ORM_LOG` reserved for future compatibility
- `SMTP_GATEWAY_TOKEN` shared secret between SMTP gateway and app

## Current note

This commit intentionally resets the repository to the upstream cloud-mail code organization first.
Current VPS deployment skeleton includes:

- `cloud-mail-app` Python backend
- `smtp-gateway` for SMTP receive on `25` / `587`
- `web` reverse proxy on `80` / `443`
- runtime state persisted in Docker volume `/data`
