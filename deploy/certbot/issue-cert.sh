#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
WEBROOT="${3:-}"
RELOAD_CMD="${4:-nginx -s reload}"

if [[ -z "$DOMAIN" || -z "$EMAIL" || -z "$WEBROOT" ]]; then
  echo "usage: issue-cert.sh <domain> <email> <webroot> [reload_cmd]" >&2
  exit 2
fi

command -v certbot >/dev/null 2>&1 || { echo "certbot not installed" >&2; exit 3; }

mkdir -p "$WEBROOT"

certbot certonly \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --webroot \
  -w "$WEBROOT" \
  -d "$DOMAIN" \
  --deploy-hook "$RELOAD_CMD"

echo "certificate issued for $DOMAIN"
