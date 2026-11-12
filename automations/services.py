from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import EmailDelivery, EmailTemplate, ReminderStep

def schedule_journey_emails(journey):
    now = timezone.now()
    email_mode = journey.payment.attempt.offer.post_payment_email
    # Registration modes use one combined email: payment confirmation plus the
    # customer-specific next-step link. Selecting a single template also keeps
    # duplicate active templates from producing duplicate customer emails.
    immediate_kind = "payment_confirmation" if email_mode == "confirmation" else "action_request"
    immediate = EmailTemplate.objects.filter(kind=immediate_kind, active=True).order_by("pk").first()
    if immediate:
        delivery, created = EmailDelivery.objects.get_or_create(
            journey=journey,
            template=immediate,
            reminder_step=None,
            defaults={"scheduled_for": now},
        )
        if created:
            transaction.on_commit(lambda pk=delivery.pk: _dispatch(pk, now))
    if email_mode == "confirmation":
        return
    for step in ReminderStep.objects.filter(active=True, template__active=True).select_related("template"):
        scheduled = now + timedelta(hours=step.delay_hours)
        delivery, created = EmailDelivery.objects.get_or_create(journey=journey, template=step.template, reminder_step=step, defaults={"scheduled_for": scheduled})
        if created:
            transaction.on_commit(lambda pk=delivery.pk, eta=scheduled: _dispatch(pk, eta))

def _dispatch(pk, eta):
    from .tasks import send_delivery
    send_delivery.apply_async(args=[pk], eta=eta)

def cancel_journey_emails(journey):
    journey.emails.filter(status=EmailDelivery.STATUS_QUEUED).update(status=EmailDelivery.STATUS_CANCELLED)

def schedule_booking_email(booking, kind):
    template = EmailTemplate.objects.filter(kind=kind, active=True).first()
    if not template:
        return None
    delivery = EmailDelivery.objects.create(
        booking=booking, template=template, scheduled_for=timezone.now(),
    )
    transaction.on_commit(lambda: _dispatch(delivery.pk, delivery.scheduled_for))
    return delivery

