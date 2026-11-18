from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commerce.models import Offer
from pages.models import ActionMapping


REQUIRED_WEBHOOK_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "charge.refunded",
    "payment_intent.canceled",
}
WEBHOOK_URLS = {
    "https://manager.cosmic135.com/payments/webhook/stripe/",
    "https://go.cosmic135.com/payments/webhook/stripe/",
}


class Command(BaseCommand):
    help = "Check that Stripe live credentials, prices, and webhook configuration are ready."

    def add_arguments(self, parser):
        parser.add_argument("--verify-api", action="store_true")
        parser.add_argument("--expected-account", default="acct_1QRHAvG7cwotxqBt")

    def handle(self, *args, **options):
        errors = []
        live_key = settings.STRIPE_LIVE_SECRET_KEY
        webhook_secret = settings.STRIPE_LIVE_WEBHOOK_SECRET
        live_offer_ids = ActionMapping.objects.filter(
            enabled=True,
            action_type=ActionMapping.ACTION_CHECKOUT,
            page__is_published=True,
            target_id__isnull=False,
        ).values_list("target_id", flat=True)
        offers = list(Offer.objects.filter(active=True, pk__in=live_offer_ids).order_by("pk"))

        if not live_key.startswith(("sk_live_", "rk_live_")):
            errors.append("STRIPE_LIVE_SECRET_KEY is missing or is not a live key.")
        if not webhook_secret.startswith("whsec_"):
            errors.append("STRIPE_LIVE_WEBHOOK_SECRET is missing or invalid.")
        if not offers:
            errors.append("No active checkout offers are mapped from a published landing page.")
        for offer in offers:
            if not offer.stripe_live_price_id:
                errors.append(f"Offer {offer.pk} ({offer.name}) has no live Price ID.")

        if options["verify_api"] and not errors:
            self._verify_stripe_api(live_key, offers, options["expected_account"], errors)

        self.stdout.write(f"Current application mode: {settings.STRIPE_MODE}")
        for offer in offers:
            state = offer.stripe_live_price_id or "MISSING"
            self.stdout.write(f"Offer {offer.pk}: {offer.name} -> {state}")
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError("Stripe live readiness failed.")
        self.stdout.write(self.style.SUCCESS("STRIPE_LIVE_READY"))

    def _verify_stripe_api(self, live_key, offers, expected_account, errors):
        import stripe

        stripe.api_key = live_key
        account = stripe.Account.retrieve()
        if account.id != expected_account:
            errors.append(f"Live key belongs to unexpected Stripe account {account.id}.")
            return

        for offer in offers:
            try:
                price = stripe.Price.retrieve(offer.stripe_live_price_id)
            except stripe.StripeError as exc:
                errors.append(f"Cannot retrieve live price for offer {offer.pk}: {exc.user_message or exc}")
                continue
            if not price.livemode:
                errors.append(f"Offer {offer.pk} Price ID is not a live-mode price.")
            if not price.active:
                errors.append(f"Offer {offer.pk} live price is inactive.")

        endpoints = list(stripe.WebhookEndpoint.list(limit=100).auto_paging_iter())
        matches = [endpoint for endpoint in endpoints if endpoint.url in WEBHOOK_URLS]
        if not matches:
            errors.append("No live webhook endpoint targets the Cosmic135 payment webhook URL.")
            return
        if not any(REQUIRED_WEBHOOK_EVENTS.issubset(set(endpoint.enabled_events)) for endpoint in matches):
            errors.append("The live webhook endpoint is missing one or more required event types.")
