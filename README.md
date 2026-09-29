# Cosmic135 Landing Page Manager

A private Django application for building and publishing landing pages, accepting Stripe payments, tracking external checkout clicks, following up with customers, and coordinating Google Calendar bookings.

## What is included

- English/Chinese manager UI with Django authentication, Google OAuth and an owner-managed email allowlist.
- Section-based page builder and validated static ZIP imports with immutable versions, preview, publish and rollback.
- Wildcard campaign hosts, verified custom domains and Caddy-managed HTTPS.
- Stripe-hosted Checkout with signed, idempotent webhook processing.
- Tracked SiteGiant/external checkout redirects without falsely treating clicks as payments.
- Opaque continuation links and Celery-powered bilingual email sequences.
- HMAC-signed Cosmic Tools registration completion callbacks.
- Multi-host Google Calendar booking, round-robin assignment, cancellation, rescheduling and reconciliation.
- PostgreSQL, Redis, Celery, Celery Beat, Gunicorn, WhiteNoise and Docker Compose.

## First deployment

1. Copy `.env.example` to `.env`. Set `DEBUG=0`, generate unique secrets and use a strong PostgreSQL password.
2. Generate the Fernet key used for Google refresh-token encryption:

   ```powershell
   .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Point `manager.cosmic135.com`, `go.cosmic135.com`, and `*.go.cosmic135.com` at the VPS. Open ports 80 and 443.
4. Start the stack:

   ```bash
   docker compose up -d --build
   docker compose exec web python manage.py bootstrap_app --email owner@example.com
   ```

   The command prompts for the initial password unless `--password` is supplied. Change the example email to the actual owner email.

5. In Google Cloud, add this OAuth redirect URI:

   `https://manager.cosmic135.com/accounts/google/login/callback/`

   Put the client ID and secret in `.env`. Calendar connections use a separate authorization flow at `https://manager.cosmic135.com/bookings/google/callback/` and that URI must also be allowed.

6. In Stripe, create a webhook to:

   `https://manager.cosmic135.com/commerce/stripe/webhook/`

   Subscribe to Checkout completion/expiration, asynchronous payment success/failure, charge refund and payment-intent events. Put the signing secret in `STRIPE_WEBHOOK_SECRET` and Stripe Price IDs on Offer records.

7. Configure SMTP variables. Google Workspace relay is supported, but any standard SMTP provider works without code changes.

The owner can use Django admin at `/admin/` to manage approved emails, roles, offers, templates, reminder steps, hosts, calendars and booking types. Team-member access is permission-based and can be refined using Django groups.

## Page upload formats

For a self-contained AI-generated page, upload `.html`, `.htm`, or `.txt` directly. The file must contain a complete UTF-8 HTML document. Inline CSS and JavaScript, base64 images, and HTTPS-hosted assets are supported. This is suitable for single-file exports such as `Latest 413.txt`.

For a page with separate image, CSS, JavaScript, or font files, use the ZIP format below.

The archive must have exactly one root `index.html`. All assets must use relative paths. Server-side code, executables, symlinks, nested archives, absolute paths and traversal paths are rejected.

Add action markers to buttons or links:

```html
<a data-lpm-action="checkout">Buy now</a>
<a data-lpm-action="booking">Book a time</a>
<a data-lpm-action="form">Register</a>
<a data-lpm-action="external-checkout">SiteGiant checkout</a>
```

Use a suffix for more than one action of a type, for example `data-lpm-action="checkout:premium"`. Each detected key must be mapped before publication.

## Cosmic Tools callback

Cosmic Tools should append `journey_token` to the registration URL, retain it during submission, then POST JSON to `/integrations/form-completed/` with headers:

- `X-Cosmic-Timestamp`: current Unix timestamp
- `X-Cosmic-Signature`: `sha256=` followed by the hex HMAC-SHA256 of `timestamp + "." + raw_request_body`

The body is:

```json
{
  "journey_token": "opaque-token",
  "submission_id": "external-id",
  "event_id": "globally-unique-event-id",
  "completed_at": "2026-09-29T12:00:00Z"
}
```

Both applications must share `FORM_CALLBACK_SECRET`. The callback rejects stale signatures and processes every event ID once. A Python signing example is in `integrations/example_cosmic_tools.py`.

## Operations

- Run tests: `.\.venv\Scripts\python.exe manage.py test`
- Production checks: set production environment values, then run `python manage.py check --deploy`.
- Logs: `docker compose logs -f web worker beat caddy`
- Create migrations: `python manage.py makemigrations`
- Apply migrations: `docker compose exec web python manage.py migrate`

Back up both PostgreSQL and the `published` volume every day to storage outside the VPS. Keep at least 30 daily restore points and test restoration regularly. A database backup without the matching published volume is incomplete. Stripe webhooks and Cosmic Tools callbacks are idempotent, so retrying delivery after recovery is safe.

## SiteGiant limitation

SiteGiant URLs are recorded as outbound clicks only. They do not create payment records or start post-payment reminders. Enable payment automation only after the actual account's webhook/API behavior or underlying Stripe event data has been verified and a dedicated adapter has been added.

## InfiniteSales migration checklist

For each priority page, export the copy, images, downloads, destination URLs and domain mapping before expiry. Rebuild or import it, map all actions, test on a temporary `*.go.cosmic135.com` hostname, and complete a Stripe test purchase through the email and registration/booking flow. Keep the previous page available until one successful production transaction is confirmed.
