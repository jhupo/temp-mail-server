# Cloud Mail VPS Edition

This repository now uses the original `maillab/cloud-mail` frontend and backend layout directly:

- frontend: `/mail-vue`
- backend: `/mail-worker`

The target direction is:

- keep the original cloud-mail frontend and backend structure
- run on a VPS with Docker
- replace Cloudflare-hosted persistence/runtime dependencies with server-side equivalents

## Current VPS baseline

- worker runtime: `wrangler dev --local`
- local persistent runtime state mounted to `/data`
- frontend built from `mail-vue` and served by the worker assets binding

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

The Docker entrypoint injects runtime values into `mail-worker/wrangler-vps.toml`.

Available variables:

- `CLOUD_MAIL_DOMAIN` comma-separated public mail domains
- `CLOUD_MAIL_ADMIN` admin account email
- `CLOUD_MAIL_JWT_SECRET` JWT signing secret
- `CLOUD_MAIL_ORM_LOG` enable ORM logging (`true` / `false`)
- `SMTP_GATEWAY_TOKEN` shared secret between SMTP gateway and app

## Current note

This commit intentionally resets the repository to the upstream cloud-mail code organization first.
Current VPS deployment skeleton now includes:

- `cloud-mail-app` for the upstream worker app
- `smtp-gateway` for SMTP receive on `25` / `587`
- `web` reverse proxy on `80` / `443`
- worker runtime still uses `wrangler dev --local`
- runtime state persists in Docker volume `/data`

The next iteration continues replacing Cloudflare-specific storage and runtime assumptions with VPS-native implementations while preserving the original API/UI model.
