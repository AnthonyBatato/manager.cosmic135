import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from automations.services import cancel_journey_emails
from commerce.models import Journey, Offer
from commerce.services import create_manual_payment
from .models import FormCompletionEvent, RegistrationSeat

MAX_SKEW_SECONDS = 300

def _valid_signature(raw_body, timestamp, supplied):
    if not settings.COSMIC_TOOLS_INTEGRATION_SECRET or not timestamp or not supplied:
        return False
    try:
        if abs(time.time() - int(timestamp)) > MAX_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = hmac.new(settings.COSMIC_TOOLS_INTEGRATION_SECRET.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.removeprefix("sha256="))

@csrf_exempt
@require_POST
def form_completed(request):
    timestamp = request.headers.get("X-Cosmic-Timestamp", "")
    signature = request.headers.get("X-Cosmic-Signature", "")
    if not _valid_signature(request.body, timestamp, signature):
        return JsonResponse({"error": "Invalid or expired signature"}, status=401)
    try:
        data = json.loads(request.body)
        if not all(data.get(key) for key in ("journey_token", "submission_id", "event_id", "completed_at")):
            raise ValueError("Missing required field")
        completed_at = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
        if timezone.is_naive(completed_at): completed_at = timezone.make_aware(completed_at)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid payload"}, status=400)
    with transaction.atomic():
        token = data.get("journey_token")
        seat = RegistrationSeat.objects.select_for_update().select_related("journey").filter(token=token).first()
        journey = (
            Journey.objects.select_for_update().get(pk=seat.journey_id)
            if seat
            else Journey.objects.select_for_update().filter(token=token).first()
        )
        if not journey:
            return JsonResponse({"error": "Unknown journey"}, status=404)
        event, created = FormCompletionEvent.objects.get_or_create(
            event_id=data.get("event_id", ""),
            defaults={
                "journey": journey,
                "seat": seat,
                "submission_id": data.get("submission_id", ""),
                "completed_at": completed_at,
            },
        )
        if created and seat and not seat.completed_at:
            seat.completed_at = completed_at
            seat.submission_id = data.get("submission_id", "")
            seat.save(update_fields=["completed_at", "submission_id"])
        all_complete = not seat or not journey.registration_seats.filter(completed_at__isnull=True).exists()
        if created and all_complete and journey.status == Journey.STATUS_PENDING:
            journey.status = Journey.STATUS_COMPLETED
            journey.completed_at = completed_at
            journey.completion_source = "form"
            journey.save(update_fields=["status", "completed_at", "completion_source"])
            cancel_journey_emails(journey)
    return JsonResponse({"received": True, "duplicate": not created})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def manual_payments(request):
    """Signed server-to-server API used by the Cosmic Tools owner screen."""
    timestamp = request.headers.get("X-Cosmic-Timestamp", "")
    signature = request.headers.get("X-Cosmic-Signature", "")
    if not _valid_signature(request.body, timestamp, signature):
        return JsonResponse({"error": "Invalid or expired signature"}, status=401)

    if request.method == "GET":
        offers = Offer.objects.filter(
            active=True,
            cosmic_tools_course_id__isnull=False,
            post_payment_email__in=[Offer.EMAIL_REGISTRATION, Offer.EMAIL_BOTH],
        ).order_by("name")
        return JsonResponse({
            "offers": [
                {
                    "id": offer.pk,
                    "name": offer.name,
                    "course_id": offer.cosmic_tools_course_id,
                    "registration_quantity": offer.registration_quantity,
                    "currency": offer.currency.upper(),
                }
                for offer in offers
            ],
        })

    try:
        data = json.loads(request.body)
        offer_id = int(data["offer_id"])
        amount_minor = int(data["amount_minor"])
        if amount_minor <= 0:
            raise ValueError("Amount must be positive")
        submission_token = uuid.UUID(str(data["submission_token"]))
        customer_name = str(data["customer_name"]).strip()
        customer_email = str(data["customer_email"]).strip().lower()
        customer_phone = str(data.get("customer_phone", "")).strip()
        note = str(data.get("note", "")).strip()
        if not customer_name or len(customer_name) > 160 or len(customer_phone) > 40 or len(note) > 250:
            raise ValueError("Invalid customer details")
        validate_email(customer_email)
        offer = Offer.objects.get(pk=offer_id, active=True, cosmic_tools_course_id__isnull=False)
    except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError, Offer.DoesNotExist):
        return JsonResponse({"error": "Invalid manual payment payload"}, status=400)

    try:
        journey, created = create_manual_payment(
            offer=offer,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            amount_total=amount_minor,
            submission_token=submission_token,
            note=note,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)

    return JsonResponse({
        "journey_id": journey.pk,
        "created": created,
        "registration_quantity": journey.registration_quantity,
        "registration_link_status": journey.registration_link_status,
    }, status=201 if created else 200)

