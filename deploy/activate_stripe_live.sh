#!/usr/bin/env bash
set -euo pipefail

project_dir="/root/cosmic135-manager/manager.cosmic135"
env_file="$project_dir/.env"
compose=(docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml)

cd "$project_dir"
"${compose[@]}" exec -T web python manage.py stripe_live_readiness --verify-api

python3 - "$env_file" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
output = []
found = False
for line in lines:
    if line.startswith("STRIPE_MODE="):
        output.append("STRIPE_MODE=live")
        found = True
    else:
        output.append(line)
if not found:
    output.append("STRIPE_MODE=live")
path.write_text("\n".join(output) + "\n")
PY

"${compose[@]}" up -d --force-recreate web worker beat
for _ in $(seq 1 30); do
  status="$(docker inspect manager135 --format '{{.State.Health.Status}}' 2>/dev/null || true)"
  [ "$status" = healthy ] && break
  sleep 2
done
[ "$(docker inspect manager135 --format '{{.State.Health.Status}}' 2>/dev/null || true)" = healthy ] || {
  echo "manager135 did not become healthy after switching to live Stripe." >&2
  exit 1
}
"${compose[@]}" exec -T web python manage.py stripe_live_readiness --verify-api
"${compose[@]}" exec -T web python manage.py shell -c \
  'from django.conf import settings; assert settings.STRIPE_MODE == "live"; print("STRIPE_MODE_LIVE")'
