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
- `APP_VERSION`: running app version (optional; if not set, the backend tries to use local git tag on HEAD)
- `APP_BUILD_SHA`: running commit sha (recommended to inject from CI)
- `APP_BUILD_TIME`: build time (optional)
- `UPDATE_SOURCE_REPO`: upstream repo used for update checks (default `jhupo/temp-mail-server`)
- `UPDATE_CHECK_URL`: custom update-check endpoint (optional, overrides repo check when set)
- `UPDATE_WEBHOOK_URL`: one-click update webhook URL (optional, CI/CD trigger endpoint)
- `UPDATE_WEBHOOK_TOKEN`: auth token for update webhook (optional)
- `UPDATE_WEBHOOK_TIMEOUT`: webhook timeout in seconds (optional)

Minimal local setup: usually only `CLOUD_MAIL_ADMIN` and `CLOUD_MAIL_ADMIN_PASSWORD` need to be set; other variables have defaults.

## Notes

- The runtime backend is implemented in Python under `app/`.
- SMTP traffic is accepted by `tempmail-smtp` and pushed to `/internal/smtp/receive`.
- Static frontend assets are built from `mail-vue` and served by the Python app behind Caddy.

## Version check and one-click update

Backend endpoints:

- `GET /version` returns current runtime version/build info
- `GET /update/check` (admin only) compares current tag version with upstream latest tag
- `POST /update/trigger` (admin only) sends webhook to CI/CD for deployment

By default, update detection works out-of-the-box as long as the service can access GitHub; extra update env config is optional.

Webhook request body (`/update/trigger`) example:

```json
{
  "event": "cloud_mail_update",
  "requestedAt": "2026-04-11T16:00:00+00:00",
  "requestedBy": {"userId": 1, "email": "admin@example.com", "name": "admin"},
  "target": "latest",
  "currentVersion": "v1.0",
  "currentBuildSha": "abc1234",
  "sourceRepo": "jhupo/temp-mail-server"
}
```

Set `UPDATE_WEBHOOK_URL` to your deployment pipeline endpoint (for example: GitHub Actions dispatch proxy, Jenkins webhook, or your own deploy service).

## External API guide

For external integration (create mailbox and receive emails), see:

- `doc/api-external.md`
