#!/usr/bin/env bash
set -uo pipefail

ENV_FILE="${DOMAIN_PROVISIONER_ENV:-/etc/cosmic-domain-provisioner.env}"
if [[ -f "$ENV_FILE" ]]; then
    # This root-owned file contains paths and the public Certbot contact email.
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

LPM_PROJECT_DIR="${LPM_PROJECT_DIR:-/root/cosmic135-manager/manager.cosmic135}"
CENTRAL_COMPOSE_DIR="${CENTRAL_COMPOSE_DIR:-/root/cosmic135}"
CENTRAL_NGINX_CONF_DIR="${CENTRAL_NGINX_CONF_DIR:-/root/cosmic135/cosmic135/nginx}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-support@cosmic135.com}"
MANAGER_COMPOSE_PROJECT="${MANAGER_COMPOSE_PROJECT:-cosmic-manager}"
NGINX_CONTAINER="${NGINX_CONTAINER:-nginx}"
LOCK_FILE="${LOCK_FILE:-/var/lock/cosmic-domain-provisioner.lock}"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

manager_command() {
    docker compose \
        -p "$MANAGER_COMPOSE_PROJECT" \
        -f "$LPM_PROJECT_DIR/docker-compose.yml" \
        -f "$LPM_PROJECT_DIR/docker-compose.server.yml" \
        exec -T web python manage.py domain_provisioning "$@"
}

record_failure() {
    local domain="$1"
    local message="$2"
    message="${message: -4000}"
    manager_command fail "$domain" --error "$message" || true
    printf 'Provisioning failed for %s: %s\n' "$domain" "$message" >&2
}

if [[ ! -d "$LPM_PROJECT_DIR" || ! -d "$CENTRAL_NGINX_CONF_DIR" ]]; then
    printf 'Provisioner paths are invalid. Check %s.\n' "$ENV_FILE" >&2
    exit 1
fi

if ! domain_output="$(manager_command list)"; then
    echo "Could not read the custom-domain provisioning queue." >&2
    exit 1
fi
mapfile -t domains <<<"$domain_output"
for domain in "${domains[@]}"; do
    [[ -n "$domain" ]] || continue
    if [[ ! "$domain" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]]; then
        record_failure "$domain" "The queued hostname failed host-side validation."
        continue
    fi

    if ! manager_command start "$domain" >/dev/null; then
        continue
    fi

    config_name="cosmic-launch-${domain//./-}.conf"
    target_config="$CENTRAL_NGINX_CONF_DIR/$config_name"
    bootstrap_tmp="$(mktemp)"
    final_tmp="$(mktemp)"
    trap 'rm -f "$bootstrap_tmp" "$final_tmp"' EXIT

    sed "s/__DOMAIN__/$domain/g" \
        "$LPM_PROJECT_DIR/deploy/nginx/custom-domain.bootstrap.conf.template" >"$bootstrap_tmp"
    install -m 0644 "$bootstrap_tmp" "$target_config"

    if ! output="$(docker exec "$NGINX_CONTAINER" nginx -t 2>&1)"; then
        rm -f "$target_config"
        record_failure "$domain" "$output"
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi
    if ! output="$(docker exec "$NGINX_CONTAINER" nginx -s reload 2>&1)"; then
        rm -f "$target_config"
        record_failure "$domain" "$output"
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi

    if ! output="$(cd "$CENTRAL_COMPOSE_DIR" && docker compose run --rm \
        --entrypoint certbot certbot certonly --non-interactive --webroot \
        -w /var/www/certbot --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
        -d "$domain" 2>&1)"; then
        record_failure "$domain" "$output"
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi

    sed "s/__DOMAIN__/$domain/g" \
        "$LPM_PROJECT_DIR/deploy/nginx/custom-domain.conf.template" >"$final_tmp"
    install -m 0644 "$final_tmp" "$target_config"

    if ! output="$(docker exec "$NGINX_CONTAINER" nginx -t 2>&1)"; then
        install -m 0644 "$bootstrap_tmp" "$target_config"
        docker exec "$NGINX_CONTAINER" nginx -s reload || true
        record_failure "$domain" "$output"
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi
    if ! output="$(docker exec "$NGINX_CONTAINER" nginx -s reload 2>&1)"; then
        install -m 0644 "$bootstrap_tmp" "$target_config"
        docker exec "$NGINX_CONTAINER" nginx -s reload || true
        record_failure "$domain" "$output"
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi
    if ! manager_command success "$domain"; then
        record_failure "$domain" "HTTPS is ready, but the manager could not be updated."
        rm -f "$bootstrap_tmp" "$final_tmp"
        continue
    fi
    printf 'Custom domain is active: https://%s/\n' "$domain"

    rm -f "$bootstrap_tmp" "$final_tmp"
    trap - EXIT
done
