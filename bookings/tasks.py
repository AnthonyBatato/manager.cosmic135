from celery import shared_task
from django.utils import timezone
from .models import Booking, SlotHold
from .services import google_service

@shared_task
def clear_expired_slot_holds():
    return SlotHold.objects.filter(expires_at__lte=timezone.now()).delete()[0]

@shared_task
def reconcile_google_bookings():
    checked = cancelled = errors = 0
    bookings = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED,
        ends_at__gte=timezone.now(),
    ).exclude(google_event_id="").select_related("host__calendar")
    for booking in bookings.iterator():
        connection = booking.host.calendar
        if not connection.active or not connection.encrypted_credentials:
            continue
        try:
            event = google_service(connection).events().get(
                calendarId=connection.target_calendar_id,
                eventId=booking.google_event_id,
            ).execute()
            checked += 1
            if event.get("status") == "cancelled":
                booking.status = Booking.STATUS_CANCELLED
                booking.save(update_fields=["status", "updated_at"])
                cancelled += 1
        except Exception:
            errors += 1
    return {"checked": checked, "cancelled": cancelled, "errors": errors}

