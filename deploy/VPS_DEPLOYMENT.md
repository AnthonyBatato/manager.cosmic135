# Existing Cosmic135 VPS deployment

This deployment reuses the central Nginx and Certbot containers in
`/root/cosmic135`. The Landing Page Manager joins the existing external Docker
network `inside-network`. Do not start the bundled Caddy service on this VPS.

## DNS records

Create these records at the DNS provider, all pointing to the VPS public IP:

- `A` record: `manager.cosmic135.com`
- `A` record: `go.cosmic135.com`
- Wildcard `A` record: `*.go.cosmic135.com`

## First installation

```bash
mkdir -p /root/cosmic135-manager
cd /root/cosmic135-manager
git clone https://github.com/AnthonyBatato/manager.cosmic135.git
cd manager.cosmic135
cp .env.production.example .env
nano .env
```

Generate secrets on the server. Do not paste the generated values into chat or
store them in Git:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

Use separate generated values for `SECRET_KEY` and `FORM_CALLBACK_SECRET`. Use
the URL-safe base64 value from the third command for `TOKEN_ENCRYPTION_KEY`.
Set the same strong database password in both `POSTGRES_PASSWORD` and the
password portion of `DATABASE_URL`.

Start the application without Caddy:

```bash
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml up -d --build
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml ps
```

## Nginx and first certificates

Install the temporary HTTP configuration and reload Nginx:

```bash
cp deploy/nginx/manager.cosmic135.bootstrap.conf /root/cosmic135/cosmic135/nginx/manager.cosmic135.conf
docker exec nginx nginx -t
docker exec nginx nginx -s reload
```

Issue the manager certificate with the existing Certbot webroot:

```bash
cd /root/cosmic135
docker compose run --rm certbot certonly --webroot -w /var/www/certbot --email support@cosmic135.com --agree-tos --no-eff-email -d manager.cosmic135.com
```

Issue the `go.cosmic135.com` wildcard certificate using DNS validation:

```bash
docker compose run --rm certbot certonly --manual --preferred-challenges dns --email support@cosmic135.com --agree-tos --no-eff-email -d go.cosmic135.com -d '*.go.cosmic135.com'
```

Certbot will display one or more TXT records for
`_acme-challenge.go.cosmic135.com`. Add every displayed value at the DNS
provider, wait until it resolves, and only then continue the prompt. A manually
issued wildcard certificate cannot renew unattended; arrange DNS API automation
or renew it manually before expiry.

After both certificates exist, install the final HTTPS configuration:

```bash
cd /root/cosmic135-manager/manager.cosmic135
cp deploy/nginx/manager.cosmic135.conf /root/cosmic135/cosmic135/nginx/manager.cosmic135.conf
docker exec nginx nginx -t
docker exec nginx nginx -s reload
```

## Initial owner

```bash
cd /root/cosmic135-manager/manager.cosmic135
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml exec web python manage.py bootstrap_app --email YOUR_EMAIL
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml exec web python manage.py changepassword YOUR_EMAIL
```

The password command prompts securely instead of storing a password in shell
history. Google login can be used after its credentials and redirect URIs are
configured.

## Routine updates

```bash
cd /root/cosmic135-manager/manager.cosmic135
git pull origin main
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml up -d --build
```

Database migrations run automatically when the web container starts. Check the
deployment with:

```bash
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml ps
docker compose -p cosmic-manager -f docker-compose.yml -f docker-compose.server.yml logs --tail=100 web worker beat
```

## One-time automatic custom-domain provisioning

Install the host provisioner once after the manager containers and central
Nginx/Certbot services are working:

```bash
cd /root/cosmic135-manager/manager.cosmic135
bash deploy/install-domain-provisioner.sh
```

The installer creates a systemd timer that checks every two minutes. For every
domain whose CNAME has been verified in the manager, it atomically installs an
HTTP challenge configuration, requests a Let's Encrypt certificate, installs
the HTTPS configuration, reloads Nginx, and marks the domain connected. Failed
attempts use exponential backoff and are retried automatically.

If this VPS uses different paths or container names, edit the root-only file
`/etc/cosmic-domain-provisioner.env`, then restart the timer:

```bash
systemctl restart cosmic-domain-provisioner.timer
systemctl start cosmic-domain-provisioner.service
```

Inspect provisioning without exposing application secrets:

```bash
systemctl status cosmic-domain-provisioner.timer
journalctl -u cosmic-domain-provisioner.service -n 100 --no-pager
```

After this one-time installation, each new domain only requires:

1. Add the CNAME shown by the manager.
2. Click **Verify connection**.
3. Wait up to a few minutes for the status to change to **Connected**.
