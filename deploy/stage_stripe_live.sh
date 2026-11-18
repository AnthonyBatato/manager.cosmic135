#!/usr/bin/env bash
set -euo pipefail

project_dir="/root/cosmic135-manager/manager.cosmic135"
env_file="$project_dir/.env"
compose=(docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml)

read -r -s -p "Stripe live secret key: " stripe_key
printf '\n'
read -r -s -p "Stripe live webhook signing secret: " webhook_secret
printf '\n'
read -r -p "Single offer live Price ID: " single_price
read -r -p "Duo offer live Price ID: " duo_price

case "$stripe_key" in
  sk_live_*|rk_live_*) ;;
  *) echo "The supplied value is not a Stripe live secret/restricted key." >&2; exit 1 ;;
esac
case "$webhook_secret" in
  whsec_*) ;;
  *) echo "The supplied value is not a Stripe webhook signing secret." >&2; exit 1 ;;
esac
case "$single_price" in price_*) ;; *) echo "Invalid Single Price ID." >&2; exit 1 ;; esac
case "$duo_price" in price_*) ;; *) echo "Invalid Duo Price ID." >&2; exit 1 ;; esac

key_file="$(mktemp /tmp/cosmic-manager-live-key.XXXXXX)"
webhook_file="$(mktemp /tmp/cosmic-manager-live-webhook.XXXXXX)"
chmod 600 "$key_file" "$webhook_file"
trap 'rm -f "$key_file" "$webhook_file"' EXIT
printf '%s' "$stripe_key" > "$key_file"
printf '%s' "$webhook_secret" > "$webhook_file"
unset stripe_key webhook_secret

python3 - "$env_file" "$key_file" "$webhook_file" <<'PY'
import pathlib
import sys

env_path, key_path, webhook_path = map(pathlib.Path, sys.argv[1:])
updates = {
    "STRIPE_LIVE_SECRET_KEY": key_path.read_text().strip(),
    "STRIPE_LIVE_WEBHOOK_SECRET": webhook_path.read_text().strip(),
}
lines = env_path.read_text().splitlines()
seen = set()
output = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line else ""
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)
for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")
env_path.write_text("\n".join(output) + "\n")
PY

cd "$project_dir"
SINGLE_LIVE_PRICE_ID="$single_price" DUO_LIVE_PRICE_ID="$duo_price" \
  "${compose[@]}" exec -T \
  -e SINGLE_LIVE_PRICE_ID -e DUO_LIVE_PRICE_ID \
  web python manage.py shell -c \
  'import os; from commerce.models import Offer; Offer.objects.filter(pk=2).update(stripe_live_price_id=os.environ["SINGLE_LIVE_PRICE_ID"]); Offer.objects.filter(pk=3).update(stripe_live_price_id=os.environ["DUO_LIVE_PRICE_ID"])'

"${compose[@]}" up -d --force-recreate web worker beat
"${compose[@]}" exec -T web python manage.py stripe_live_readiness --verify-api

echo "Live Stripe configuration is staged and verified. STRIPE_MODE remains unchanged."
