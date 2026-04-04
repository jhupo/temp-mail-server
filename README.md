# Temp Mail Server (Python)

一个可直接部署到 VPS 的临时邮箱服务端：

- 支持任意本地部分和任意子域收信（`*@jhupo.com`、`*@temp.jhupo.com`、`*@abc.jhupo.com`）
- `POST /api/v1/mailboxes/new` 创建临时邮箱
- `GET /api/v1/mailboxes/{address}/latest` 获取最新邮件
- `GET /api/v1/mailboxes/{address}/latest/code` 提取验证码
- 内置前端控制台（访问 `/`）
- SMTP 收件自动入库（可配置自动创建邮箱）

## 1. DNS (Cloudflare)

建议配置如下（都使用 DNS only）：

- `A  mail.jhupo.com -> VPS_IP`
- `MX jhupo.com -> mail.jhupo.com` (priority 10)
- `MX *.jhupo.com -> mail.jhupo.com` (priority 10)

说明：

- 根域 `jhupo.com` 仍需单独 MX。
- 服务端会校验 `domain == jhupo.com` 或 `domain.endswith(".jhupo.com")`。

## 2. 本地方式运行（开发用）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
python -m app.smtp_server
```

## 3. Docker Compose 一键部署（推荐）

```bash
docker compose up -d --build
```

默认会启动四个服务：

- `postgres`：数据库
- `redis`：限流存储
- `api`：HTTP API（`8000`）
- `smtp`：SMTP 收信（`25`）

首次上线前请修改 `docker-compose.yml` 中：

- `POSTGRES_PASSWORD`
- `DATABASE_URL` 中密码
- `ALLOWED_ROOT_DOMAIN`
- `API_MASTER_KEY`

## 4. API 示例

### 4.1 新建邮箱

```bash
curl -X POST http://127.0.0.1:8000/api/v1/mailboxes/new \
  -H "X-API-Key: change_me_long_random_value" \
  -H "Content-Type: application/json" \
  -d '{"domain":"temp.jhupo.com","ttl_minutes":120}'
```

返回示例：

```json
{
  "address": "x8ab29f0d1@temp.jhupo.com",
  "token": "....",
  "expires_at": "2026-04-04T12:00:00Z"
}
```

### 4.2 获取最新邮件

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/x8ab29f0d1@temp.jhupo.com/latest?token=YOUR_TOKEN"
```

### 4.3 获取最新邮件中的验证码

默认正则是 `\b(\d{4,8})\b`，会提取 4-8 位数字：

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/x8ab29f0d1@temp.jhupo.com/latest/code?token=YOUR_TOKEN"
```

也可以自定义正则：

```bash
curl "http://127.0.0.1:8000/api/v1/mailboxes/x8ab29f0d1@temp.jhupo.com/latest/code?token=YOUR_TOKEN&pattern=code%3A%20([A-Z0-9]{6})"
```

## 5. 前端控制台

启动后直接打开：

- `http://你的服务器IP:8000/`

支持：

- 创建邮箱（可选填写 API Key）
- 保存邮箱会话并切换
- 手动/自动拉取最新邮件
- 自动提取验证码

## 6. Nginx + HTTPS

已提供示例配置：

- `deploy/nginx.tempmail.conf`

建议 API 使用独立子域，例如 `api.jhupo.com`，再用 certbot 签证书。

## 7. 防火墙与端口

至少放行：

- `25/tcp` (SMTP)
- `80/tcp` 和 `443/tcp` (Nginx)

如果你不走 Nginx，才需要直接放行 `8000/tcp`。

## 8. 生产建议

- 增加 API 限流（Nginx 或 Redis）
- 增加 SMTP 单封大小限制
- 配置 PTR 反向解析，提升投递兼容
- 增加垃圾邮件过滤和黑名单策略

## 9. 安全与限流说明

- `POST /api/v1/mailboxes/new` 默认要求 `X-API-Key`（由 `API_MASTER_KEY` 控制）
- 若未设置 `API_MASTER_KEY`，则不校验 API key
- `POST /api/v1/mailboxes/new` 会按 IP 进行每分钟限流（`RATE_LIMIT_NEW_PER_MINUTE`）
