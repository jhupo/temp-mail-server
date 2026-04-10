# Temp Mail Server

This project now exists only to serve `codex-console-sub2api`.

It exposes the mailbox endpoints that `sub2api` expects and no longer keeps the older `/api/v1/mailboxes/*` API.

## Active Endpoints

Base URL example:

```text
http://127.0.0.1:8000
```

Mailbox creation:

- `POST /admin/new_address`
- `POST /inbox/create`

Mailbox reading:

- `GET /admin/mails`
- `GET /admin/mails/{id}`
- `GET /api/mails`
- `GET /api/mails/{id}`
- `GET /user_api/mails`
- `GET /user_api/mails/{id}`
- `GET /inbox`

Health:

- `GET /healthz`

Frontend:

- `GET /`

## Auth Rules

- Admin endpoints use `x-admin-auth`
- Bearer endpoints use `Authorization: Bearer <token>`
- User token endpoints use `x-user-token`
- `/inbox` uses query param `token`

Admin endpoints are disabled unless `API_MASTER_KEY` is set, and then `x-admin-auth` must match it.

## Domain Configuration

- `ALLOWED_ROOT_DOMAINS` accepts a comma-separated allowlist such as `example.com,mail.example.com`
- `ALLOWED_ROOT_DOMAIN` is kept as a backward-compatible single-domain fallback
- mailbox creation without an explicit `domain` uses the first domain in `ALLOWED_ROOT_DOMAINS`
- SMTP recipients are accepted when they match an allowed domain or one of its subdomains

If SMTP auto-creates a mailbox before you claim it, you can later call `POST /admin/new_address` with the exact address and receive a fresh token for that mailbox.

## Database Migrations

Alembic is configured in this repo.

Run the latest migrations:

```bash
alembic upgrade head
```

Create a new migration after model changes:

```bash
alembic revision -m "describe change"
```

If you are migrating an existing database that was created before `ix_mailboxes_token_hash` existed, apply the Alembic migration path instead of creating the index manually.

## Frontend UI

This repo now includes a trimmed Vue 3 frontend under `frontend/` using the visual style and layout approach from `maillab/cloud-mail`, adapted to this backend's actual API surface.

Supported UI capabilities:

- create random mailbox
- create custom mailbox when `API_MASTER_KEY` is available
- switch between saved mailbox tokens
- poll and list mailbox messages
- open message details with HTML / text / raw tabs

Frontend dev/build:

```bash
cd frontend
npm install
npm run build
```

When `frontend/dist` exists, FastAPI serves it from `/`.

## Typical Flow

Create admin mailbox:

```bash
curl -X POST http://127.0.0.1:8000/admin/new_address \
  -H "Content-Type: application/json" \
  -H "x-admin-auth: change_me" \
  -d '{"name":"demo123","domain":"example.com","enablePrefix":true}'
```

Create inbox-style mailbox:

```bash
curl -X POST http://127.0.0.1:8000/inbox/create
```

Fetch inbox by token:

```bash
curl "http://127.0.0.1:8000/inbox?token=your_mailbox_token"
```

Fetch user mail list:

```bash
curl http://127.0.0.1:8000/user_api/mails \
  -H "x-user-token: your_mailbox_token"
```

Fetch admin mail list:

```bash
curl "http://127.0.0.1:8000/admin/mails?address=demo123@example.com" \
  -H "x-admin-auth: change_me"
```
