# External API Guide (Mailbox Create and Receive)

This document explains how external systems call the Python backend to:

- create a mailbox address
- receive emails from that mailbox via API

## 1. Base URL and API prefix

- Base URL example: `http://127.0.0.1:8000`
- Both path styles are supported:
  - `/login`
  - `/api/login`

The backend has a compatibility middleware that maps `/api/*` to `/*`.

## 2. Response format

Most business responses use:

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

- `code = 200` means success.
- Non-200 business failures are returned in the same JSON format.
- Authentication failures from protected routes may return HTTP `401` directly.

## 3. Step 1: Get token (register or login)

### 3.1 Register

`POST /register`

```json
{
  "email": "alice@example.com",
  "password": "your_password"
}
```

### 3.2 Login

`POST /login`

```json
{
  "email": "alice@example.com",
  "password": "your_password"
}
```

Success response:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "token": "YOUR_TOKEN"
  }
}
```

Use this token for protected APIs:

- `Authorization: YOUR_TOKEN`
- or `Authorization: Bearer YOUR_TOKEN`

Both formats are accepted.

## 4. Step 2: Create mailbox

`POST /account/add`

Headers:

- `Authorization: YOUR_TOKEN`
- `Content-Type: application/json`

Body:

```json
{
  "email": "bot01@example.com"
}
```

Success `data` example:

```json
{
  "accountId": 12,
  "email": "bot01@example.com",
  "name": "bot01",
  "allReceive": 0,
  "sort": 1712868000,
  "isDel": 0
}
```

Common failures:

- `domain not allowed` (domain not in allowed list)
- `email prefix too short`
- `add account disabled`

You can query allowed domains and rules from:

- `GET /setting/websiteConfig`
- response fields: `data.allowedDomains`, `data.minEmailPrefix`

## 5. Step 3: Query mailbox list and get `accountId`

`GET /account/list`

Headers:

- `Authorization: YOUR_TOKEN`

Response `data` is an array of mailbox accounts, each containing `accountId`.

## 6. Step 4: Receive emails by API

After a mailbox is created (for example `bot01@example.com`), send emails to that address by SMTP, then poll receive APIs.

### 6.1 Poll latest emails

`GET /email/latest?accountId=12&allReceive=0&emailId=0`

Headers:

- `Authorization: YOUR_TOKEN`

Notes:

- `accountId` is required.
- `emailId` is the last seen id; only records with larger id are returned.
- Set `allReceive=1` to query across all mailbox accounts of the user.

### 6.2 List emails with pagination

`GET /email/list?accountId=12&allReceive=0&emailId=0&size=50&type=0`

Headers:

- `Authorization: YOUR_TOKEN`

Notes:

- `type=0` for inbox.
- If `emailId > 0`, it returns older emails (`id < emailId`).
- Response `data.list` items include `emailId`, `subject`, `text`, `content`, `sendEmail`, `toEmail`, `createTime`.

## 7. End-to-end curl example

```bash
# 1) login
curl -s -X POST "http://127.0.0.1:8000/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"alice@example.com\",\"password\":\"your_password\"}"

# 2) create mailbox (replace YOUR_TOKEN)
curl -s -X POST "http://127.0.0.1:8000/account/add" \
  -H "Authorization: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"bot01@example.com\"}"

# 3) list mailbox to confirm accountId
curl -s "http://127.0.0.1:8000/account/list" \
  -H "Authorization: YOUR_TOKEN"

# 4) poll inbox (replace accountId)
curl -s "http://127.0.0.1:8000/email/latest?accountId=12&allReceive=0&emailId=0" \
  -H "Authorization: YOUR_TOKEN"
```

## 8. How email enters the system

There are two supported receive paths:

### 8.1 Normal SMTP path (recommended)

- SMTP service listens on `SMTP_HOST:SMTP_PORT` (default `0.0.0.0:25`).
- External sender sends mail to your mailbox address.
- SMTP worker converts it and pushes to backend `/internal/smtp/receive`.
- You read emails from `/email/latest` or `/email/list`.

### 8.2 Internal gateway injection API (service-to-service)

`POST /internal/smtp/receive`

Header:

- `x-smtp-gateway-token: <SMTP_GATEWAY_TOKEN>`

Body example:

```json
{
  "from": "sender@remote.com",
  "to": ["bot01@example.com"],
  "subject": "Test",
  "text": "hello",
  "html": "<p>hello</p>",
  "raw": "raw email source"
}
```

This endpoint is intended for trusted internal gateway use. Do not expose it publicly without strict access control.
