import hashlib

from django.conf import settings

from pages.models import AdTrackingSettings

from .models import AdConversionDelivery


def payment_event_id(payment):
    source = payment.stripe_payment_intent_id or f"payment:{payment.pk}"
    return "payment_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]


def queue_purchase_conversion(payment):
    tracking = AdTrackingSettings.objects.filter(
        page=payment.attempt.page, openai_enabled=True,
    ).exclude(openai_pixel_id="").first()
    if not tracking:
        return None
    source_url = f"https://{payment.attempt.page.slug}.{settings.PUBLIC_ROOT_HOST}/"
    event = {
        "id": payment_event_id(payment),
        "type": "order_created",
        "timestamp_ms": int(payment.paid_at.timestamp() * 1000),
        "action_source": "web",
        "source_url": source_url,
        "data": {
            "type": "contents",
            "amount": payment.amount_total,
            "currency": payment.currency.upper(),
        },
    }
    if payment.attempt.openai_oppref:
        event["oppref"] = payment.attempt.openai_oppref
    if payment.attempt.openai_obref:
        event["user"] = {"obref": payment.attempt.openai_obref}
    payload = {"integration_source": "cosmic_landing_manager", "events": [event]}
    delivery, _ = AdConversionDelivery.objects.get_or_create(
        provider="openai", pixel_id=tracking.openai_pixel_id, event_id=event["id"],
        defaults={"payment": payment, "event_type": event["type"], "payload": payload},
    )
    return delivery
