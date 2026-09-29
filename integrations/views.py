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
from .models import FormCompletionEvent

MAX_SKEW_SECONDS = 300

def _valid_signature(raw_body, timestamp, supplied):
    if not settings.FORM_CALLBACK_SECRET or not timestamp or not supplied:
        return False
    try:
        if abs(time.time() - int(timestamp)) > MAX_SKEW_SECONDS:
            return False
    except ValueError:
        return False
    expected = hmac.new(settings.FORM_CALLBACK_SECRET.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
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
        journey = Journey.objects.select_for_update().filter(token=data.get("journey_token")).first()
        if not journey:
            return JsonResponse({"error": "Unknown journey"}, status=404)
        event, created = FormCompletionEvent.objects.get_or_create(event_id=data.get("event_id", ""), defaults={"journey": journey, "submission_id": data.get("submission_id", ""), "completed_at": completed_at})
        if created and journey.status == Journey.STATUS_PENDING:
            journey.status = Journey.STATUS_COMPLETED
            journey.completed_at = completed_at
            journey.completion_source = "form"
            journey.save(update_fields=["status", "completed_at", "completion_source"])
            cancel_journey_emails(journey)
    return JsonResponse({"received": True, "duplicate": not created})

