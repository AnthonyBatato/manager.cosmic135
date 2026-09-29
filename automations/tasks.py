from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone
import smtplib
from .models import EmailDelivery

@shared_task(bind=True, max_retries=5)
def send_delivery(self, delivery_pk):
    with transaction.atomic():
        delivery = EmailDelivery.objects.select_for_update().select_related("journey__customer", "booking__customer", "booking__booking_type", "template").get(pk=delivery_pk)
        journey = delivery.journey
        booking = delivery.booking
        customer = journey.customer if journey else booking.customer
        should_stop = delivery.status != EmailDelivery.STATUS_QUEUED or customer.unsubscribed_at
        if journey and journey.status != "pending":
            should_stop = True
        if should_stop:
            if delivery.status == EmailDelivery.STATUS_QUEUED:
                delivery.status = EmailDelivery.STATUS_CANCELLED
                delivery.save(update_fields=["status"])
            return
        delivery.attempts += 1
        delivery.save(update_fields=["attempts"])
    if journey:
        action_url = f"https://{settings.PUBLIC_ROOT_HOST}{reverse('continue_journey', kwargs={'token': journey.token})}"
    else:
        action_url = f"https://{settings.PUBLIC_ROOT_HOST}{reverse('booking_confirmed', kwargs={'token': booking.cancellation_token})}"
    context = Context({"customer": customer, "journey": journey, "booking": booking, "action_url": action_url})
    use_zh = customer.preferred_language == "zh"
    subject_source = delivery.template.subject_zh if use_zh and delivery.template.subject_zh else delivery.template.subject_en
    body_source = delivery.template.body_zh if use_zh and delivery.template.body_zh else delivery.template.body_en
    subject = Template(subject_source).render(context)
    body = Template(body_source).render(context)
    try:
        message = EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, [customer.email])
        count = message.send()
        if count != 1: raise ConnectionError("Email backend did not accept the message.")
    except (smtplib.SMTPException, ConnectionError, TimeoutError, OSError) as exc:
        EmailDelivery.objects.filter(pk=delivery_pk).update(status=EmailDelivery.STATUS_QUEUED, error=str(exc))
        raise self.retry(exc=exc, countdown=min(3600, 60 * (2 ** self.request.retries)))
    except Exception as exc:
        EmailDelivery.objects.filter(pk=delivery_pk).update(status=EmailDelivery.STATUS_FAILED, error=str(exc))
        return
    EmailDelivery.objects.filter(pk=delivery_pk).update(status=EmailDelivery.STATUS_SENT, sent_at=timezone.now(), error="")

