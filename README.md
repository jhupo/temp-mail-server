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

## Auth Rules

- Admin endpoints use `x-admin-auth`
- Bearer endpoints use `Authorization: Bearer <token>`
- User token endpoints use `x-user-token`
- `/inbox` uses query param `token`

If `API_MASTER_KEY` is set, `x-admin-auth` must match it.

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
