import hashlib
import hmac
import json
import time
from urllib import error, request

from celery import shared_task
from django.conf import settings
from django.db import transaction

from automations.services import schedule_journey_emails
from commerce.models import Journey


def _signed_registration_request(journey):
    payload = json.dumps(
        {
            "event_id": f"journey-{journey.pk}",
            "journey_token": journey.token,
            "course_id": journey.cosmic_tools_course_id,
            "customer_email": journey.customer.email,
            "customer_name": journey.customer.name,
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.COSMIC_TOOLS_INTEGRATION_SECRET.encode(),
        timestamp.encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    return request.Request(
        settings.COSMIC_TOOLS_REGISTRATION_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Cosmic-Timestamp": timestamp,
            "X-Cosmic-Signature": f"sha256={signature}",
        },
    )


@shared_task(bind=True, max_retries=6)
def provision_cosmic_tools_registration(self, journey_pk):
    journey = Journey.objects.select_related("customer", "payment__attempt__offer").get(pk=journey_pk)
    if journey.registration_link_status == "ready":
        return journey.destination_url
    if journey.status != Journey.STATUS_PENDING or not journey.cosmic_tools_course_id:
        return None
    if not settings.COSMIC_TOOLS_INTEGRATION_SECRET:
        Journey.objects.filter(pk=journey.pk).update(
            registration_link_status="failed",
            registration_link_error="COSMIC_TOOLS_INTEGRATION_SECRET is not configured.",
        )
        return None
    try:
        with request.urlopen(_signed_registration_request(journey), timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        registration_url = result.get("registration_url", "")
        if not registration_url.startswith(("https://", "http://")):
            raise ValueError("Cosmic Tools returned an invalid registration URL.")
    except error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        Journey.objects.filter(pk=journey.pk).update(registration_link_error=detail)
        if 400 <= exc.code < 500 and exc.code not in {408, 429}:
            Journey.objects.filter(pk=journey.pk).update(registration_link_status="failed")
            return None
        raise self.retry(exc=exc, countdown=min(3600, 60 * (2 ** self.request.retries)))
    except (error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        Journey.objects.filter(pk=journey.pk).update(registration_link_error=str(exc))
        raise self.retry(exc=exc, countdown=min(3600, 60 * (2 ** self.request.retries)))

    with transaction.atomic():
        locked = Journey.objects.select_for_update().get(pk=journey.pk)
        if locked.status != Journey.STATUS_PENDING:
            return None
        locked.destination_url = registration_url
        locked.registration_link_status = "ready"
        locked.registration_link_error = ""
        locked.save(update_fields=["destination_url", "registration_link_status", "registration_link_error"])
        schedule_journey_emails(locked)
    return registration_url
