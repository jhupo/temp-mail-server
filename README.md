# Temp Mail Server

Python temporary mail backend for VPS deployment.

Features:
- Receive mail for `*@yourdomain.com`
- Receive mail for `*@*.yourdomain.com`
- Create mailboxes by API
- Fetch latest message, message list, and verification code by API
- SMTP auto-ingest into PostgreSQL
- Optional API key protection for mailbox creation
- Optional lazy mailbox creation on incoming SMTP

## Stack

- FastAPI
- aiosmtpd
- PostgreSQL
- Redis
- Docker Compose

## Cloudflare DNS

For a root domain such as `freeloader.xyz`, configure:

```text
A   mail.freeloader.xyz      -> VPS_IP         DNS only
MX  freeloader.xyz          -> mail.freeloader.xyz   priority 10
MX  *.freeloader.xyz        -> mail.freeloader.xyz   priority 10
```

Recommended:

```text
A   *.freeloader.xyz        -> VPS_IP         DNS only
```

Notes:
- `mail.freeloader.xyz` must be `DNS only`, not proxied.
- Root domain and wildcard MX are both needed.
- The app accepts `domain == ALLOWED_ROOT_DOMAIN` or any subdomain ending with it.

## Docker Deploy

Start services:

```bash
docker compose up -d --build
```

Services:
- `api`: HTTP API on `8000`
- `smtp`: SMTP receiver on `25`
- `postgres`: database
- `redis`: rate limiting backend

Important environment values in [`docker-compose.yml`](C:/Users/jhupo-pc/Desktop/mail/temp-mail-server/docker-compose.yml):
- `ALLOWED_ROOT_DOMAIN`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `API_MASTER_KEY`

## Environment

Example values are in [`.env.example`](C:/Users/jhupo-pc/Desktop/mail/temp-mail-server/.env.example).

Important options:
- `ALLOWED_ROOT_DOMAIN`: allowed root domain, for example `freeloader.xyz`
- `MAILBOX_DEFAULT_TTL_MINUTES`: default mailbox lifetime
- `ALLOW_AUTO_CREATE_ON_SMTP`: auto-create mailbox rows when a message arrives for an unknown address
- `API_MASTER_KEY`: if set, `POST /api/v1/mailboxes/new` requires `X-API-Key`
- `RATE_LIMIT_NEW_PER_MINUTE`: mailbox creation rate limit per IP

## API

Base URL example:

```text
http://127.0.0.1:8000
```

### Create mailbox

Request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/mailboxes/new \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change_me_long_random_value" \
  -d '{"domain":"mga.freeloader.xyz","local_part":"asdi","ttl_minutes":60}'
```

Response:

```json
{
  "address": "asdi@mga.freeloader.xyz",
  "token": "your_mailbox_token",
  "expires_at": "2026-04-04T15:00:00.000000"
}
```

Notes:
- `domain` is optional. If omitted, the server uses `ALLOWED_ROOT_DOMAIN`.
- `local_part` is optional. If omitted, the server generates a random local part.
- `ttl_minutes` is optional.

### Get latest message

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/asdi@mga.freeloader.xyz/latest?token=your_mailbox_token"
```

### Get message list

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/asdi@mga.freeloader.xyz/messages?token=your_mailbox_token&limit=20"
```

### Extract verification code

Default regex extracts 4 to 8 digit codes:

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/asdi@mga.freeloader.xyz/latest/code?token=your_mailbox_token"
```

Custom regex:

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/asdi@mga.freeloader.xyz/latest/code?token=your_mailbox_token&pattern=code%3A%20([A-Z0-9]{6})"
```

## Auth and Access

Mailbox creation:
- If `API_MASTER_KEY` is set, `POST /api/v1/mailboxes/new` requires `X-API-Key`.
- If `API_MASTER_KEY` is not set, mailbox creation is open.

Mailbox reading:
- `latest`, `messages`, and `latest/code` require the mailbox `token`.
- Token is returned only when a mailbox is created through the API.

## SMTP Behavior

Incoming mail path:
- External sender connects to your VPS on port `25`
- `smtp` container accepts the message
- Message is parsed and stored in PostgreSQL

If `ALLOW_AUTO_CREATE_ON_SMTP=true`:
- A mailbox row is created automatically when mail arrives for an unknown address
- This does not automatically grant API read access unless you already have the token

## Health Check

```bash
curl http://127.0.0.1:8000/healthz
```

## Troubleshooting

### Mailbox creation works, but external mail does not arrive

Check:

```bash
ss -lntp | grep :25
docker compose logs --tail=100 smtp
docker compose ps
```

### Root domain works, subdomain does not

Check wildcard MX and A records:

```bash
dig MX mga.freeloader.xyz +short
dig A mga.freeloader.xyz +short
```

Expected:

```text
10 mail.freeloader.xyz.
VPS_IP
```

### Gmail sends but mail is rejected

Make sure:
- `ALLOWED_ROOT_DOMAIN` matches your real domain
- The SMTP parser includes the multipart Gmail fix in [`app/smtp_server.py`](C:/Users/jhupo-pc/Desktop/mail/temp-mail-server/app/smtp_server.py)
- You rebuilt containers after pulling updates

Update containers:

```bash
git pull
docker compose up -d --build
```

### Message exists in database but not in your API result

Check the exact mailbox address and token:

```bash
docker compose exec postgres psql -U tempmail -d tempmail -c "select id,address,last_message_at from mailboxes order by id desc limit 20;"
docker compose exec postgres psql -U tempmail -d tempmail -c "select from_addr,subject,received_at from messages order by id desc limit 20;"
```

## Production Recommendations

- Set `ALLOWED_ROOT_DOMAIN` to your real domain
- Set a strong `API_MASTER_KEY`
- Configure reverse PTR for your server IP
- Keep `mail.freeloader.xyz` and PTR aligned if possible
- Put Nginx in front of the API if you need HTTPS
- Limit who can call mailbox creation
