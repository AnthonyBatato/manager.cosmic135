from celery import shared_task
from django.utils import timezone
from .models import StripeEvent
from .services import process_checkout_event

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=6)
def process_stripe_event(self, event_pk):
    event = StripeEvent.objects.get(pk=event_pk)
    try:
        process_checkout_event(event)
    except Exception as exc:
        StripeEvent.objects.filter(pk=event_pk).update(error=str(exc))
        raise

