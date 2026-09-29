from django.db import transaction
from django.utils import timezone
from .models import CheckoutAttempt, Customer, Journey, Payment, StripeEvent

def _event_payment_intent(event):
    obj = event.payload.get("data", {}).get("object", {})
    return obj.get("payment_intent") or (obj.get("id") if event.event_type == "payment_intent.canceled" else "")

def _mark_refunded(payment):
    payment.status = "refunded"
    payment.save(update_fields=["status"])
    journey = Journey.objects.filter(payment=payment).first()
    if journey and journey.status == Journey.STATUS_PENDING:
        journey.status = Journey.STATUS_CANCELLED
        journey.completion_source = "refund"
        journey.save(update_fields=["status", "completion_source"])
        from automations.services import cancel_journey_emails
        cancel_journey_emails(journey)

@transaction.atomic
def process_checkout_event(event_record):
    if event_record.processed_at:
        return None
    payload = event_record.payload
    obj = payload.get("data", {}).get("object", {})
    event_type = event_record.event_type
    session_id = obj.get("id")
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        attempt = CheckoutAttempt.objects.select_for_update().select_related("offer").get(stripe_session_id=session_id)
        email = (obj.get("customer_details") or {}).get("email") or obj.get("customer_email")
        if not email:
            raise ValueError("Stripe session did not provide a customer email.")
        customer, _ = Customer.objects.get_or_create(email=email.lower(), defaults={"name": (obj.get("customer_details") or {}).get("name", "")})
        attempt.customer = customer
        attempt.status = CheckoutAttempt.STATUS_PAID
        attempt.save(update_fields=["customer", "status", "updated_at"])
        payment, _ = Payment.objects.get_or_create(attempt=attempt, defaults={
            "stripe_payment_intent_id": obj.get("payment_intent") or "",
            "amount_total": obj.get("amount_total") or 0,
            "currency": obj.get("currency") or attempt.offer.currency.lower(),
        })
        journey, created = Journey.objects.get_or_create(payment=payment, defaults={
            "customer": customer,
            "destination_type": attempt.offer.destination_type,
            "destination_id": attempt.offer.destination_id,
            "destination_url": attempt.offer.destination_url,
        })
        if created:
            from automations.services import schedule_journey_emails
            schedule_journey_emails(journey)
        refund_seen = any(
            _event_payment_intent(previous) == payment.stripe_payment_intent_id
            for previous in StripeEvent.objects.filter(event_type__in=["charge.refunded", "payment_intent.canceled"])
        )
        if refund_seen:
            _mark_refunded(payment)
    elif event_type == "checkout.session.expired":
        CheckoutAttempt.objects.filter(stripe_session_id=session_id).update(status=CheckoutAttempt.STATUS_EXPIRED)
        journey = None
    elif event_type == "checkout.session.async_payment_failed":
        CheckoutAttempt.objects.filter(stripe_session_id=session_id).update(status=CheckoutAttempt.STATUS_FAILED)
        journey = None
    elif event_type in {"charge.refunded", "payment_intent.canceled"}:
        payment_intent = obj.get("payment_intent") or obj.get("id")
        for payment in Payment.objects.filter(stripe_payment_intent_id=payment_intent):
            _mark_refunded(payment)
        journey = None
    else:
        journey = None
    event_record.processed_at = timezone.now()
    event_record.error = ""
    event_record.save(update_fields=["processed_at", "error"])
    return journey

