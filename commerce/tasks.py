from celery import shared_task
import json
from urllib import error, parse, request
from django.conf import settings
from django.utils import timezone
from .models import AdConversionDelivery, StripeEvent
from .services import process_checkout_event

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=6)
def process_stripe_event(self, event_pk):
    event = StripeEvent.objects.get(pk=event_pk)
    try:
        journey = process_checkout_event(event)
        if journey:
            for delivery_pk in journey.payment.ad_conversion_deliveries.filter(
                status=AdConversionDelivery.STATUS_QUEUED,
            ).values_list("pk", flat=True):
                send_ad_conversion.delay(delivery_pk)
    except Exception as exc:
        StripeEvent.objects.filter(pk=event_pk).update(error=str(exc))
        raise

@shared_task(bind=True, max_retries=6)
def send_ad_conversion(self, delivery_pk):
    delivery = AdConversionDelivery.objects.get(pk=delivery_pk)
    if delivery.status == AdConversionDelivery.STATUS_SENT:
        return
    if delivery.provider != "openai":
        AdConversionDelivery.objects.filter(pk=delivery_pk).update(
            status=AdConversionDelivery.STATUS_FAILED, error="Unsupported conversion provider.",
        )
        return
    if not settings.OPENAI_CONVERSIONS_API_KEY:
        AdConversionDelivery.objects.filter(pk=delivery_pk).update(
            status=AdConversionDelivery.STATUS_QUEUED,
            error="OPENAI_CONVERSIONS_API_KEY is not configured.",
        )
        return
    delivery.attempts += 1
    delivery.save(update_fields=["attempts", "updated_at"])
    endpoint = "https://bzr.openai.com/v1/events?pid=" + parse.quote(delivery.pixel_id, safe="")
    outgoing = request.Request(
        endpoint, data=json.dumps(delivery.payload).encode("utf-8"), method="POST",
        headers={
            "Authorization": f"Bearer {settings.OPENAI_CONVERSIONS_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(outgoing, timeout=15) as response:
            response_code = response.status
            response.read()
    except error.HTTPError as exc:
        response_code = exc.code
        detail = exc.read(1000).decode("utf-8", errors="replace")
        if 400 <= exc.code < 500 and exc.code not in {408, 429}:
            AdConversionDelivery.objects.filter(pk=delivery_pk).update(
                status=AdConversionDelivery.STATUS_FAILED, response_code=exc.code, error=detail,
            )
            return
        AdConversionDelivery.objects.filter(pk=delivery_pk).update(
            status=AdConversionDelivery.STATUS_QUEUED, response_code=exc.code, error=detail,
        )
        raise self.retry(exc=exc, countdown=min(3600, 60 * (2 ** self.request.retries)))
    except (error.URLError, TimeoutError, OSError) as exc:
        AdConversionDelivery.objects.filter(pk=delivery_pk).update(
            status=AdConversionDelivery.STATUS_QUEUED, error=str(exc),
        )
        raise self.retry(exc=exc, countdown=min(3600, 60 * (2 ** self.request.retries)))
    AdConversionDelivery.objects.filter(pk=delivery_pk).update(
        status=AdConversionDelivery.STATUS_SENT, response_code=response_code,
        sent_at=timezone.now(), error="",
    )

@shared_task
def dispatch_pending_ad_conversions():
    pending = list(AdConversionDelivery.objects.filter(
        status=AdConversionDelivery.STATUS_QUEUED,
    ).order_by("created_at").values_list("pk", flat=True)[:200])
    for delivery_pk in pending:
        send_ad_conversion.delay(delivery_pk)
    return len(pending)

