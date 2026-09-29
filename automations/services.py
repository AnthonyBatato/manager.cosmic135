from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import EmailDelivery, EmailTemplate, ReminderStep

def schedule_journey_emails(journey):
    now = timezone.now()
    for immediate in EmailTemplate.objects.filter(kind__in=["payment_confirmation", "action_request"], active=True):
        delivery, created = EmailDelivery.objects.get_or_create(journey=journey, template=immediate, reminder_step=None, defaults={"scheduled_for": now})
        if created:
            transaction.on_commit(lambda pk=delivery.pk: _dispatch(pk, now))
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

