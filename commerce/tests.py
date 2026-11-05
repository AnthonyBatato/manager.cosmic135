from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from automations.models import EmailDelivery, EmailTemplate, ReminderStep
from automations.services import schedule_journey_emails
from pages.models import ActionMapping, AdTrackingSettings, LandingPage
from users.models import ApprovedEmail
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
        payload = {"data": {"object": {"id": "cs_test", "payment_intent": "pi_test", "amount_total": 10000, "currency": "myr", "customer_details": {"email": "buyer@example.com", "name": "Buyer", "phone": "+60123456789"}}}}
        event = StripeEvent.objects.create(event_id="evt_test", event_type="checkout.session.completed", payload=payload)
        journey = process_checkout_event(event)
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertEqual(journey.customer.email, "buyer@example.com")
        self.assertEqual(journey.customer.name, "Buyer")
        self.assertEqual(journey.customer.phone, "+60123456789")
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

    @patch("integrations.tasks.provision_cosmic_tools_registration.delay")
    @patch("automations.services.schedule_journey_emails")
    def test_course_payment_provisions_link_before_email(self, schedule, provision):
        page = LandingPage.objects.create(name="Integrated", slug="integrated")
        offer = Offer.objects.create(
            name="Course", cosmic_tools_course_id=42,
            destination_url="https://tools.example/register/generic-course/",
        )
        action = ActionMapping.objects.create(
            page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk,
        )
        CheckoutAttempt.objects.create(page=page, action=action, offer=offer, stripe_session_id="cs_integrated")
        event = StripeEvent.objects.create(
            event_id="evt_integrated",
            event_type="checkout.session.completed",
            payload={"data": {"object": {
                "id": "cs_integrated", "payment_intent": "pi_integrated", "amount_total": 200,
                "currency": "myr", "customer_details": {"email": "course@example.com"},
            }}},
        )
        with self.captureOnCommitCallbacks(execute=True):
            journey = process_checkout_event(event)
        self.assertEqual(journey.cosmic_tools_course_id, 42)
        self.assertEqual(journey.registration_link_status, "pending")
        self.assertEqual(journey.destination_url, "")
        provision.assert_called_once_with(journey.pk)
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


class StripeCheckoutFlowTests(TestCase):
    def setUp(self):
        self.page = LandingPage.objects.create(name="Sales page", slug="sales-page", is_published=True)
        self.offer = Offer.objects.create(
            name="Course", stripe_test_price_id="price_test_course",
            stripe_live_price_id="price_live_course", destination_url="https://tools.example/register/",
        )
        self.action = ActionMapping.objects.create(
            page=self.page, key="checkout", label="Buy", action_type="checkout", target_id=self.offer.pk,
        )

    @override_settings(
        STRIPE_MODE="test", STRIPE_SECRET_KEY="sk_test_private",
        STRIPE_PUBLIC_BASE_URL="https://go.example.com", PUBLIC_ROOT_HOST="go.example.com",
    )
    @patch("commerce.views.stripe.checkout.Session.create")
    def test_checkout_uses_sandbox_price_and_public_success_page(self, create_session):
        create_session.return_value = SimpleNamespace(id="cs_test_created", url="https://checkout.stripe.test/session")
        response = self.client.get(reverse("checkout_start", args=[self.action.pk]))
        self.assertRedirects(response, "https://checkout.stripe.test/session", fetch_redirect_response=False)
        kwargs = create_session.call_args.kwargs
        self.assertEqual(kwargs["line_items"], [{"price": "price_test_course", "quantity": 1}])
        self.assertEqual(kwargs["name_collection"], {"individual": {"enabled": True, "optional": False}})
        self.assertEqual(kwargs["phone_number_collection"], {"enabled": True})
        self.assertEqual(kwargs["success_url"], "https://go.example.com/payments/success/?session_id={CHECKOUT_SESSION_ID}")
        attempt = CheckoutAttempt.objects.get(stripe_session_id="cs_test_created")
        self.assertEqual(attempt.stripe_mode, "test")

    def test_status_becomes_paid_only_after_webhook_created_journey(self):
        attempt = CheckoutAttempt.objects.create(
            page=self.page, action=self.action, offer=self.offer, stripe_session_id="cs_status",
        )
        processing = self.client.get(reverse("checkout_status"), {"session_id": "cs_status"})
        self.assertEqual(processing.json(), {"status": "created"})
        from .models import Customer
        customer = Customer.objects.create(email="buyer@example.com")
        payment = Payment.objects.create(attempt=attempt, amount_total=1000, currency="myr")
        journey = Journey.objects.create(
            payment=payment, customer=customer, destination_type="form", destination_url="https://tools.example/register/",
        )
        attempt.status = CheckoutAttempt.STATUS_PAID
        attempt.save(update_fields=["status"])
        paid = self.client.get(reverse("checkout_status"), {"session_id": "cs_status"}).json()
        self.assertEqual(paid["status"], "paid")
        self.assertTrue(paid["has_next_step"])
        self.assertEqual(paid["continue_url"], reverse("continue_journey", args=[journey.token]))

    @override_settings(STRIPE_WEBHOOK_SECRETS=["whsec_test", "whsec_live"])
    @patch("commerce.views.process_stripe_event.delay")
    @patch("commerce.views.stripe.Webhook.construct_event")
    def test_webhook_accepts_either_configured_secret_once(self, construct_event, delay):
        construct_event.side_effect = [
            stripe.SignatureVerificationError("bad signature", "sig"),
            {"id": "evt_live", "type": "checkout.session.completed", "livemode": True, "data": {"object": {}}},
        ]
        response = self.client.post(
            reverse("stripe_webhook"), data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="sig",
        )
        self.assertEqual(response.status_code, 200)
        event = StripeEvent.objects.get(event_id="evt_live")
        self.assertTrue(event.livemode)
        delay.assert_called_once_with(event.pk)


class PostPaymentEmailTests(TestCase):
    def make_journey(self, email_mode):
        page = LandingPage.objects.create(name=f"Page {email_mode}", slug=f"page-{email_mode}")
        offer = Offer.objects.create(name="Offer", post_payment_email=email_mode)
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer)
        from .models import Customer
        customer = Customer.objects.create(email=f"{email_mode}@example.com")
        payment = Payment.objects.create(attempt=attempt)
        return Journey.objects.create(payment=payment, customer=customer)

    @patch("automations.services._dispatch")
    def test_confirmation_only_sends_no_registration_reminders(self, dispatch):
        confirmation = EmailTemplate.objects.create(name="Confirmed", kind="payment_confirmation", subject_en="Paid", body_en="Thanks")
        EmailTemplate.objects.create(name="Register", kind="action_request", subject_en="Register", body_en="Continue")
        reminder = EmailTemplate.objects.create(name="Reminder", kind="reminder", subject_en="Reminder", body_en="Continue")
        ReminderStep.objects.create(name="24 hours", delay_hours=24, template=reminder)
        journey = self.make_journey(Offer.EMAIL_CONFIRMATION)
        with self.captureOnCommitCallbacks(execute=True):
            schedule_journey_emails(journey)
        self.assertEqual(list(EmailDelivery.objects.values_list("template", flat=True)), [confirmation.pk])
        self.assertEqual(dispatch.call_count, 1)

    @patch("automations.services._dispatch")
    def test_both_sends_confirmation_registration_and_reminder(self, dispatch):
        EmailTemplate.objects.create(name="Confirmed", kind="payment_confirmation", subject_en="Paid", body_en="Thanks")
        EmailTemplate.objects.create(name="Register", kind="action_request", subject_en="Register", body_en="Continue")
        reminder = EmailTemplate.objects.create(name="Reminder", kind="reminder", subject_en="Reminder", body_en="Continue")
        ReminderStep.objects.create(name="24 hours", delay_hours=24, template=reminder)
        journey = self.make_journey(Offer.EMAIL_BOTH)
        with self.captureOnCommitCallbacks(execute=True):
            schedule_journey_emails(journey)
        self.assertEqual(EmailDelivery.objects.filter(journey=journey).count(), 3)
        self.assertEqual(dispatch.call_count, 3)


class PaymentSettingsTests(TestCase):
    def test_owner_can_open_payment_settings(self):
        user = get_user_model().objects.create_user("owner@example.com", email="owner@example.com", password="pass")
        ApprovedEmail.objects.create(email=user.email, role="owner")
        self.client.force_login(user)
        response = self.client.get(reverse("payment_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payments")
