import hashlib
import hmac
import json
import time
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from commerce.models import CheckoutAttempt, Customer, Journey, Offer, Payment
from integrations.models import RegistrationSeat
from pages.models import ActionMapping, LandingPage

@override_settings(COSMIC_TOOLS_INTEGRATION_SECRET="shared-test-secret")
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

    def test_duo_journey_completes_only_after_both_participants_submit(self):
        first = RegistrationSeat.objects.create(journey=self.journey, seat_number=1)
        second = RegistrationSeat.objects.create(journey=self.journey, seat_number=2)

        first_payload = {"journey_token": first.token, "submission_id": "sub-1", "event_id": "evt-seat-1", "completed_at": timezone.now().isoformat()}
        self.assertEqual(self.signed_post(first_payload).status_code, 200)
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, Journey.STATUS_PENDING)

        second_payload = {"journey_token": second.token, "submission_id": "sub-2", "event_id": "evt-seat-2", "completed_at": timezone.now().isoformat()}
        self.assertEqual(self.signed_post(second_payload).status_code, 200)
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, Journey.STATUS_COMPLETED)


class CosmicToolsProvisioningTests(TestCase):
    def setUp(self):
        page = LandingPage.objects.create(name="Course page", slug="course-page")
        offer = Offer.objects.create(name="Course", cosmic_tools_course_id=42, post_payment_email="registration")
        action = ActionMapping.objects.create(
            page=page, key="checkout", label="Buy", action_type="checkout", target_id=offer.pk,
        )
        attempt = CheckoutAttempt.objects.create(page=page, action=action, offer=offer, status="paid")
        customer = Customer.objects.create(email="buyer@example.com", name="Buyer")
        payment = Payment.objects.create(attempt=attempt)
        self.journey = Journey.objects.create(
            payment=payment,
            customer=customer,
            cosmic_tools_course_id=42,
            registration_link_status="pending",
        )

    @override_settings(
        COSMIC_TOOLS_INTEGRATION_SECRET="integration-secret",
        COSMIC_TOOLS_REGISTRATION_API_URL="https://tools.example/integrations/registration-links/",
    )
    @patch("integrations.tasks.schedule_journey_emails")
    @patch("integrations.tasks.request.urlopen")
    def test_provisions_unique_link_then_schedules_email(self, urlopen, schedule):
        from integrations.tasks import provision_cosmic_tools_registration

        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps({
            "registration_url": "https://tools.example/register/link/customer-token/",
        }).encode()

        result = provision_cosmic_tools_registration.run(self.journey.pk)

        self.assertEqual(result, ["https://tools.example/register/link/customer-token/"])
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.registration_link_status, "ready")
        self.assertEqual(self.journey.destination_url, result[0])
        schedule.assert_called_once()
        outgoing = urlopen.call_args.args[0]
        self.assertEqual(outgoing.full_url, "https://tools.example/integrations/registration-links/")
        sent = json.loads(outgoing.data)
        self.assertEqual(sent["course_id"], 42)
        self.assertEqual(sent["customer_email"], "buyer@example.com")
        seat = self.journey.registration_seats.get(seat_number=1)
        self.assertEqual(sent["journey_token"], seat.token)
        self.assertTrue(outgoing.headers["X-cosmic-signature"].startswith("sha256="))

        self.assertEqual(provision_cosmic_tools_registration.run(self.journey.pk), result)
        self.assertEqual(urlopen.call_count, 1)
        schedule.assert_called_once()

    @override_settings(
        COSMIC_TOOLS_INTEGRATION_SECRET="integration-secret",
        COSMIC_TOOLS_REGISTRATION_API_URL="https://tools.example/integrations/registration-links/",
    )
    @patch("integrations.tasks.schedule_journey_emails")
    @patch("integrations.tasks.request.urlopen")
    def test_duo_offer_provisions_two_unique_registration_links(self, urlopen, schedule):
        from integrations.tasks import provision_cosmic_tools_registration

        self.journey.registration_quantity = 2
        self.journey.save(update_fields=["registration_quantity"])
        first = urlopen.return_value.__enter__.return_value
        first.read.side_effect = [
            json.dumps({"registration_url": "https://tools.example/register/link/one/"}).encode(),
            json.dumps({"registration_url": "https://tools.example/register/link/two/"}).encode(),
        ]

        result = provision_cosmic_tools_registration.run(self.journey.pk)

        self.assertEqual(result, [
            "https://tools.example/register/link/one/",
            "https://tools.example/register/link/two/",
        ])
        self.assertEqual(self.journey.registration_seats.count(), 2)
        payloads = [json.loads(call.args[0].data) for call in urlopen.call_args_list]
        self.assertNotEqual(payloads[0]["journey_token"], payloads[1]["journey_token"])
        schedule.assert_called_once()

