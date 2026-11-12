import hashlib
import hmac
import json
import time
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from automations.services import cancel_journey_emails
from commerce.models import Journey
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

