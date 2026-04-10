#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
WEBROOT="${3:-}"
RELOAD_CMD="${4:-nginx -s reload}"

if [[ -z "$DOMAIN" || -z "$EMAIL" || -z "$WEBROOT" ]]; then
  echo "usage: renew-cert.sh <domain> <email> <webroot> [reload_cmd]" >&2
  exit 2
fi

command -v certbot >/dev/null 2>&1 || { echo "certbot not installed" >&2; exit 3; }

mkdir -p "$WEBROOT"

certbot renew \
  --webroot \
  -w "$WEBROOT" \
  --deploy-hook "$RELOAD_CMD"

echo "certificate renewed for $DOMAIN"
