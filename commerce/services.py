from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pages.models import ActionMapping
from .models import CheckoutAttempt, Customer, Journey, Payment, StripeEvent

def _event_payment_intent(event):
    obj = event.payload.get("data", {}).get("object", {})
    return obj.get("payment_intent") or (obj.get("id") if event.event_type == "payment_intent.canceled" else "")

def _checkout_attempt_for_session(obj, event_record):
    session_id = obj.get("id")
    attempt = CheckoutAttempt.objects.select_for_update().select_related("offer").filter(
        stripe_session_id=session_id,
    ).first()
    if attempt:
        return attempt
    reference = str(obj.get("client_reference_id") or "")
    if reference.isdigit():
        attempt = CheckoutAttempt.objects.select_for_update().select_related("offer").filter(pk=int(reference)).first()
        if attempt and not attempt.stripe_session_id:
            attempt.stripe_session_id = session_id
            attempt.save(update_fields=["stripe_session_id", "updated_at"])
            return attempt
    metadata = obj.get("metadata") or {}
    offer_id = str(metadata.get("offer_id") or "")
    page_id = str(metadata.get("page_id") or "")
    action_id = str(metadata.get("action_id") or "")
    if offer_id.isdigit() and page_id.isdigit() and action_id.isdigit():
        return CheckoutAttempt.objects.create(
            page_id=int(page_id),
            page_version_id=int(metadata["page_version_id"]) if str(metadata.get("page_version_id") or "").isdigit() else None,
            action_id=int(action_id),
            offer_id=int(offer_id),
            stripe_session_id=session_id,
            stripe_mode="live" if event_record.livemode else "test",
        )
    raise CheckoutAttempt.DoesNotExist(f"No checkout attempt matches Stripe session {session_id}.")

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
def create_manual_payment(*, offer, customer_name, customer_email, customer_phone, amount_total, submission_token, note=""):
    """Create the same journey as a paid Stripe checkout without fabricating a Stripe event."""
    manual_reference = f"manual_{submission_token}"
    existing_attempt = CheckoutAttempt.objects.select_for_update().filter(
        stripe_session_id=manual_reference,
    ).first()
    if existing_attempt:
        return Journey.objects.get(payment__attempt=existing_attempt), False

    action = ActionMapping.objects.select_related("page", "page__published_version").filter(
        action_type=ActionMapping.ACTION_CHECKOUT,
        target_id=offer.pk,
        enabled=True,
        page__is_published=True,
    ).order_by("pk").first()
    if not action:
        raise ValueError("This offer is not mapped to an enabled checkout action on a published landing page.")

    email = customer_email.strip().lower()
    customer, created_customer = Customer.objects.get_or_create(
        email=email,
        defaults={"name": customer_name.strip(), "phone": customer_phone.strip()},
    )
    if not created_customer:
        changed = []
        if customer_name.strip() and customer.name != customer_name.strip():
            customer.name = customer_name.strip()
            changed.append("name")
        if customer_phone.strip() and customer.phone != customer_phone.strip():
            customer.phone = customer_phone.strip()
            changed.append("phone")
        if changed:
            customer.save(update_fields=[*changed, "updated_at"])

    attempt = CheckoutAttempt.objects.create(
        page=action.page,
        page_version=action.page.published_version,
        action=action,
        offer=offer,
        customer=customer,
        stripe_session_id=manual_reference,
        stripe_mode=settings.STRIPE_MODE,
        status=CheckoutAttempt.STATUS_PAID,
    )
    payment = Payment.objects.create(
        attempt=attempt,
        stripe_payment_intent_id=f"manual:{submission_token}",
        amount_total=amount_total,
        currency=offer.currency.lower(),
        source=Payment.SOURCE_MANUAL,
        manual_note=note.strip(),
    )
    journey = Journey.objects.create(
        payment=payment,
        customer=customer,
        destination_type=offer.destination_type,
        destination_id=offer.destination_id,
        destination_url="" if offer.cosmic_tools_course_id else offer.destination_url,
        cosmic_tools_course_id=offer.cosmic_tools_course_id,
        registration_quantity=offer.registration_quantity,
        registration_link_status="pending" if offer.cosmic_tools_course_id else "not_required",
    )
    if journey.cosmic_tools_course_id:
        from integrations.tasks import provision_cosmic_tools_registration
        transaction.on_commit(lambda pk=journey.pk: provision_cosmic_tools_registration.delay(pk))
    else:
        from automations.services import schedule_journey_emails
        schedule_journey_emails(journey)
    return journey, True

@transaction.atomic
def process_checkout_event(event_record):
    if event_record.processed_at:
        return None
    payload = event_record.payload
    obj = payload.get("data", {}).get("object", {})
    event_type = event_record.event_type
    session_id = obj.get("id")
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        attempt = _checkout_attempt_for_session(obj, event_record)
        event_mode = "live" if event_record.livemode else "test"
        if attempt.stripe_mode != event_mode:
            raise ValueError(
                f"Stripe event mode {event_mode!r} does not match checkout attempt mode {attempt.stripe_mode!r}."
            )
        if event_type == "checkout.session.completed" and obj.get("payment_status") not in {None, "paid", "no_payment_required"}:
            event_record.processed_at = timezone.now()
            event_record.error = ""
            event_record.save(update_fields=["processed_at", "error"])
            return None
        customer_details = obj.get("customer_details") or {}
        email = customer_details.get("email") or obj.get("customer_email")
        if not email:
            raise ValueError("Stripe session did not provide a customer email.")
        customer, created_customer = Customer.objects.get_or_create(
            email=email.lower(),
            defaults={
                "name": customer_details.get("name", ""),
                "phone": customer_details.get("phone", ""),
            },
        )
        if not created_customer:
            updated_fields = []
            for field in ("name", "phone"):
                value = customer_details.get(field, "")
                if value and getattr(customer, field) != value:
                    setattr(customer, field, value)
                    updated_fields.append(field)
            if updated_fields:
                customer.save(update_fields=[*updated_fields, "updated_at"])
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
            "destination_url": "" if attempt.offer.cosmic_tools_course_id else attempt.offer.destination_url,
            "cosmic_tools_course_id": attempt.offer.cosmic_tools_course_id,
            "registration_quantity": attempt.offer.registration_quantity,
            "registration_link_status": "pending" if attempt.offer.cosmic_tools_course_id else "not_required",
        })
        if created:
            if journey.cosmic_tools_course_id:
                from integrations.tasks import provision_cosmic_tools_registration
                transaction.on_commit(lambda pk=journey.pk: provision_cosmic_tools_registration.delay(pk))
            else:
                from automations.services import schedule_journey_emails
                schedule_journey_emails(journey)
        refund_seen = any(
            _event_payment_intent(previous) == payment.stripe_payment_intent_id
            for previous in StripeEvent.objects.filter(event_type__in=["charge.refunded", "payment_intent.canceled"])
        )
        if refund_seen:
            _mark_refunded(payment)
        if payment.status == "paid":
            from .tracking import queue_purchase_conversion
            queue_purchase_conversion(payment)
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

