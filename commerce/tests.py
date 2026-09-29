from unittest.mock import patch
from django.test import TestCase
from pages.models import ActionMapping, LandingPage
from .models import CheckoutAttempt, Journey, Offer, Payment, StripeEvent
from .services import process_checkout_event

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
