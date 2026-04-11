# Cloud Mail VPS Edition

This repository keeps the original `maillab/cloud-mail` frontend, but the runtime backend is now fully Python for VPS deployment.

- frontend: `/mail-vue`
- api backend: `/app`
- smtp service: `/app/smtp_server.py`

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
- `APP_VERSION` current running version (optional, defaults to local git tag if head is tagged)
- `APP_BUILD_SHA` running commit sha (optional)
- `APP_BUILD_TIME` build time (optional)
- `UPDATE_SOURCE_REPO` repo used for update check (default `jhupo/temp-mail-server`)
- `UPDATE_CHECK_URL` custom update-check endpoint (optional)
- `UPDATE_WEBHOOK_URL` one-click update webhook (optional)
- `UPDATE_WEBHOOK_TOKEN` auth token for update webhook (optional)
- `UPDATE_WEBHOOK_TIMEOUT` webhook timeout in seconds (optional)

Minimal local setup: usually only `CLOUD_MAIL_ADMIN` and `CLOUD_MAIL_ADMIN_PASSWORD` are required; other variables have defaults.

## Version check and one-click update

Backend endpoints:

- `GET /version` return current running version/build info
- `GET /update/check` admin-only, compares current tag version with upstream latest tag
- `POST /update/trigger` admin-only, sends webhook to CI/CD for deployment

By default, update detection works out-of-the-box as long as the service can access GitHub.

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

## External API guide

For external integration (create mailbox and receive emails), see:

- `doc/api-external.md`
