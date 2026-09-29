import hashlib
import hmac
import json
import time
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from commerce.models import CheckoutAttempt, Customer, Journey, Offer, Payment
from pages.models import ActionMapping, LandingPage

@override_settings(FORM_CALLBACK_SECRET="shared-test-secret")
class FormCallbackTests(TestCase):
    def setUp(self):
        page = LandingPage.objects.create(name="Page", slug="page")
        offer = Offer.objects.create(name="Offer")
        action = ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk)
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer, status="paid")
        customer = Customer.objects.create(email="buyer@example.com")
        payment = Payment.objects.create(attempt=attempt)
        self.journey = Journey.objects.create(payment=payment, customer=customer)

    def signed_post(self, data, secret="shared-test-secret", timestamp=None):
        raw = json.dumps(data).encode()
        stamp = str(timestamp or int(time.time()))
        signature = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        return self.client.post(reverse("form_completed"), raw, content_type="application/json", HTTP_X_COSMIC_TIMESTAMP=stamp, HTTP_X_COSMIC_SIGNATURE=f"sha256={signature}")

    def test_valid_callback_completes_journey_and_is_idempotent(self):
        payload = {"journey_token": self.journey.token, "submission_id": "sub-1", "event_id": "evt-1", "completed_at": timezone.now().isoformat()}
        self.assertEqual(self.signed_post(payload).status_code, 200)
        self.assertTrue(self.signed_post(payload).json()["duplicate"])
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, Journey.STATUS_COMPLETED)

    def test_rejects_bad_or_expired_signature(self):
        payload = {"journey_token": self.journey.token, "submission_id": "sub-1", "event_id": "evt-2", "completed_at": timezone.now().isoformat()}
        self.assertEqual(self.signed_post(payload, secret="wrong").status_code, 401)
        self.assertEqual(self.signed_post(payload, timestamp=int(time.time()) - 600).status_code, 401)

