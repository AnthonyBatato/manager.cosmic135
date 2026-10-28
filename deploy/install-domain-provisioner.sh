#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run this installer as root." >&2
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

install -m 0755 "$PROJECT_DIR/deploy/provision-custom-domains.sh" \
    /usr/local/sbin/cosmic-domain-provisioner
install -m 0644 "$PROJECT_DIR/deploy/systemd/cosmic-domain-provisioner.service" \
    /etc/systemd/system/cosmic-domain-provisioner.service
install -m 0644 "$PROJECT_DIR/deploy/systemd/cosmic-domain-provisioner.timer" \
    /etc/systemd/system/cosmic-domain-provisioner.timer

if [[ ! -f /etc/cosmic-domain-provisioner.env ]]; then
    install -m 0600 "$PROJECT_DIR/deploy/domain-provisioner.env.example" \
        /etc/cosmic-domain-provisioner.env
fi

systemctl daemon-reload
systemctl enable --now cosmic-domain-provisioner.timer
systemctl start cosmic-domain-provisioner.service

echo "Automatic custom-domain provisioning is installed."
systemctl --no-pager status cosmic-domain-provisioner.timer || true
