from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone
import smtplib
from .models import EmailDelivery


def render_bilingual(template, context):
    """Render Chinese first and English second for every automated email."""
    subject_zh = Template(template.subject_zh).render(context).strip()
    subject_en = Template(template.subject_en).render(context).strip()
    body_zh = Template(template.body_zh).render(context).strip()
    body_en = Template(template.body_en).render(context).strip()

    subject_parts = [part for part in (subject_zh, subject_en) if part]
    body_parts = [part for part in (body_zh, body_en) if part]
    subject = " ｜ ".join(subject_parts)
    body = "\n\n────────── English 英文 ──────────\n\n".join(body_parts)
    return subject, body

@shared_task(bind=True, max_retries=5)
def send_delivery(self, delivery_pk):
    with transaction.atomic():
        # Lock only the delivery row. Combining select_for_update() with the
        # nullable journey/booking select_related() joins makes PostgreSQL try
        # to lock the nullable side of an outer join, which it rejects.
        delivery = EmailDelivery.objects.select_for_update().get(pk=delivery_pk)
        delivery = EmailDelivery.objects.select_related(
            "journey__customer", "booking__customer", "booking__booking_type", "template",
        ).get(pk=delivery.pk)
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
        action_url = f"{settings.STRIPE_PUBLIC_BASE_URL}{reverse('continue_journey', kwargs={'token': journey.token})}"
    else:
        action_url = f"https://{settings.PUBLIC_ROOT_HOST}{reverse('booking_confirmed', kwargs={'token': booking.cancellation_token})}"
    payment = journey.payment if journey else None
    offer = payment.attempt.offer if payment else None
    context = Context({"customer": customer, "journey": journey, "payment": payment, "offer": offer, "booking": booking, "action_url": action_url})
    subject, body = render_bilingual(delivery.template, context)
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

