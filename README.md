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
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:8000
```

## Current note

This commit intentionally resets the repository to the upstream cloud-mail code organization first.
The next iteration replaces Cloudflare-specific storage and runtime assumptions with VPS-native implementations while preserving the original API/UI model.
