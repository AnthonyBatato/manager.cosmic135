from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from django.urls import reverse
from pages.models import ActionMapping, AdTrackingSettings, LandingPage
from .models import AdConversionDelivery, CheckoutAttempt, Journey, Offer, Payment, StripeEvent
from .services import process_checkout_event
from .tasks import dispatch_pending_ad_conversions, send_ad_conversion
from .tracking import queue_purchase_conversion

class StripeEventTests(TestCase):
    @patch("automations.services.schedule_journey_emails")
    def test_completed_checkout_is_idempotent(self, schedule):
        page = LandingPage.objects.create(name="Page", slug="page")
        offer = Offer.objects.create(name="Offer", destination_url="https://tools.cosmic135.com/register/test/")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer, stripe_session_id="cs_test")
        payload = {"data": {"object": {"id": "cs_test", "payment_intent": "pi_test", "amount_total": 10000, "currency": "myr", "customer_details": {"email": "buyer@example.com", "name": "Buyer"}}}}
        event = StripeEvent.objects.create(event_id="evt_test", event_type="checkout.session.completed", payload=payload)
        journey = process_checkout_event(event)
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertEqual(journey.customer.email, "buyer@example.com")
        self.assertEqual(Journey.objects.count(), 1)
        self.assertIsNone(process_checkout_event(event))
        schedule.assert_called_once()

    @patch("automations.services.schedule_journey_emails")
    def test_refund_before_checkout_completion_is_reconciled(self, schedule):
        page = LandingPage.objects.create(name="Page", slug="page")
        offer = Offer.objects.create(name="Offer", destination_url="https://tools.cosmic135.com/register/test/")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        CheckoutAttempt.objects.create(page=page, action=action, offer=offer, stripe_session_id="cs_late")
        refund = StripeEvent.objects.create(
            event_id="evt_refund_first", event_type="charge.refunded",
            payload={"data": {"object": {"id": "ch_test", "payment_intent": "pi_late"}}},
        )
        process_checkout_event(refund)
        completed = StripeEvent.objects.create(
            event_id="evt_complete_later", event_type="checkout.session.completed",
            payload={"data": {"object": {"id": "cs_late", "payment_intent": "pi_late", "amount_total": 5000, "currency": "myr", "customer_details": {"email": "late@example.com"}}}},
        )
        process_checkout_event(completed)
        payment = Payment.objects.get(stripe_payment_intent_id="pi_late")
        self.assertEqual(payment.status, "refunded")
        self.assertEqual(payment.journey.status, Journey.STATUS_CANCELLED)

    @patch("automations.services.schedule_journey_emails")
    def test_delayed_checkout_waits_for_payment_success(self, schedule):
        page = LandingPage.objects.create(name="Page", slug="delayed")
        offer = Offer.objects.create(name="Offer", destination_url="https://tools.cosmic135.com/register/test/")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        CheckoutAttempt.objects.create(page=page, action=action, offer=offer, stripe_session_id="cs_delayed")
        event = StripeEvent.objects.create(
            event_id="evt_delayed", event_type="checkout.session.completed",
            payload={"data": {"object": {"id": "cs_delayed", "payment_status": "unpaid", "customer_details": {"email": "later@example.com"}}}},
        )
        self.assertIsNone(process_checkout_event(event))
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Journey.objects.exists())
        schedule.assert_not_called()

    @override_settings(PUBLIC_ROOT_HOST="go.example.com")
    def test_openai_purchase_delivery_is_page_specific_and_idempotent(self):
        page = LandingPage.objects.create(name="Page", slug="tracked-page")
        AdTrackingSettings.objects.create(page=page, openai_enabled=True, openai_pixel_id="pixel-123")
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(
            page=page, action=action, offer=offer, stripe_session_id="cs_delivery",
            openai_oppref="oppref-value", openai_obref="obref-value",
        )
        payment = Payment.objects.create(
            attempt=attempt, stripe_payment_intent_id="pi_delivery", amount_total=12500, currency="myr",
        )
        first = queue_purchase_conversion(payment)
        second = queue_purchase_conversion(payment)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AdConversionDelivery.objects.count(), 1)
        event = first.payload["events"][0]
        self.assertEqual(event["type"], "order_created")
        self.assertEqual(event["data"], {"type": "contents", "amount": 12500, "currency": "MYR"})
        self.assertEqual(event["oppref"], "oppref-value")
        self.assertEqual(event["user"], {"obref": "obref-value"})
        self.assertEqual(event["source_url"], "https://tracked-page.go.example.com/")

    @patch("commerce.tasks.send_ad_conversion.delay")
    def test_pending_conversion_dispatch_is_recoverable(self, delay):
        page = LandingPage.objects.create(name="Page", slug="recovery")
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer)
        payment = Payment.objects.create(attempt=attempt)
        delivery = AdConversionDelivery.objects.create(
            payment=payment, pixel_id="pixel-recovery", event_id="payment-recovery",
            event_type="order_created", payload={"events": []},
        )
        self.assertEqual(dispatch_pending_ad_conversions.run(), 1)
        delay.assert_called_once_with(delivery.pk)

    @override_settings(OPENAI_CONVERSIONS_API_KEY="private-server-key")
    @patch("commerce.tasks.request.urlopen")
    def test_openai_delivery_sends_without_exposing_secret(self, urlopen):
        page = LandingPage.objects.create(name="Page", slug="send-page")
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer)
        payment = Payment.objects.create(attempt=attempt, amount_total=5000)
        delivery = AdConversionDelivery.objects.create(
            payment=payment, pixel_id="pixel-send", event_id="payment-send", event_type="order_created",
            payload={"events": [{"id": "payment-send", "type": "order_created"}]},
        )
        response = MagicMock()
        response.status = 200
        response.read.return_value = b"{}"
        urlopen.return_value.__enter__.return_value = response
        send_ad_conversion.run(delivery.pk)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, AdConversionDelivery.STATUS_SENT)
        self.assertEqual(delivery.response_code, 200)
        outgoing = urlopen.call_args.args[0]
        self.assertEqual(outgoing.headers["Authorization"], "Bearer private-server-key")
        self.assertNotIn("private-server-key", delivery.payload)

    def test_confirmed_payment_page_fires_browser_purchase_after_consent(self):
        page = LandingPage.objects.create(name="Page", slug="purchase-page")
        AdTrackingSettings.objects.create(
            page=page, meta_enabled=True, meta_pixel_id="meta-123",
            google_ads_enabled=True, google_ads_id="AW-123", google_ads_conversion_label="PurchaseLabel",
            openai_enabled=True, openai_pixel_id="openai-123", require_consent=True,
        )
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer, stripe_session_id="cs_success")
        Payment.objects.create(
            attempt=attempt, stripe_payment_intent_id="pi_success", amount_total=7500, currency="myr",
        )
        url = reverse("checkout_success") + "?session_id=cs_success"
        without_consent = self.client.get(url)
        self.assertNotContains(without_consent, "cosmic-purchase-tracking")
        self.client.cookies[f"cosmic_ads_consent_{page.pk}"] = "granted"
        with_consent = self.client.get(url)
        self.assertContains(with_consent, "cosmic-purchase-tracking")
        self.assertContains(with_consent, "meta-123")
        self.assertContains(with_consent, "AW-123")
        self.assertContains(with_consent, "PurchaseLabel")
        self.assertContains(with_consent, "openai-123")
        self.assertContains(with_consent, "order_created")
        self.assertContains(with_consent, '"amountMinor":7500')

    def test_attribution_is_saved_only_after_tracking_consent(self):
        page = LandingPage.objects.create(name="Page", slug="attribution", is_published=True)
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        action_url = reverse("action_redirect", args=[page.slug, action.key])
        self.client.get(action_url + "?oppref=ignored-without-consent")
        self.assertNotIn("openai_oppref", self.client.session)
        self.client.cookies[f"cosmic_ads_consent_{page.pk}"] = "granted"
        self.client.cookies["__obref"] = "browser-reference"
        self.client.get(action_url + "?oppref=accepted-reference")
        self.assertEqual(self.client.session["openai_oppref"], "accepted-reference")
        self.assertEqual(self.client.session["openai_obref"], "browser-reference")
