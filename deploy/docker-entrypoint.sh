#!/usr/bin/env bash
set -euo pipefail

DOMAIN_CSV="${CLOUD_MAIL_DOMAIN:-}"
ADMIN_EMAIL="${CLOUD_MAIL_ADMIN:-superadmin@jhupo.com}"
JWT_SECRET="${CLOUD_MAIL_JWT_SECRET:-change_me_super_secret}"
ORM_LOG="${CLOUD_MAIL_ORM_LOG:-false}"

if [[ -n "$DOMAIN_CSV" ]]; then
  IFS=',' read -r -a DOMAIN_ARRAY <<< "$DOMAIN_CSV"
  TOML_DOMAINS="["
  for item in "${DOMAIN_ARRAY[@]}"; do
    value="$(echo "$item" | xargs)"
    [[ -z "$value" ]] && continue
    if [[ "$TOML_DOMAINS" != "[" ]]; then
      TOML_DOMAINS+=", "
    fi
    TOML_DOMAINS+="\"$value\""
  done
  TOML_DOMAINS+="]"
else
  TOML_DOMAINS="[]"
fi

cat >/app/mail-worker/wrangler-vps.toml <<EOF
name = "cloud-mail-vps"
main = "src/index.js"
compatibility_date = "2025-06-04"
keep_vars = true

[dev]
ip = "0.0.0.0"
port = 8000
local_protocol = "http"

[observability]
enabled = true

[[d1_databases]]
binding = "db"
database_name = "email"
database_id = "local-email"

[[kv_namespaces]]
binding = "kv"
id = "local-kv"

[[r2_buckets]]
binding = "r2"
bucket_name = "email"

[assets]
binding = "assets"
directory = "./dist"
not_found_handling = "single-page-application"
run_worker_first = true

[vars]
orm_log = $ORM_LOG
domain = $TOML_DOMAINS
admin = "$ADMIN_EMAIL"
jwt_secret = "$JWT_SECRET"
EOF

cd /app/mail-worker
exec npx wrangler dev --config wrangler-vps.toml --local --persist-to /data --host 0.0.0.0 --port 8000
