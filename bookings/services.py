import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from .models import Booking, BookingType, Host, SlotHold, TimeOff

def _fernet():
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured.")
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())

def encrypt_credentials(credentials):
    return _fernet().encrypt(credentials.to_json().encode())

def decrypt_credentials(connection):
    raw = _fernet().decrypt(bytes(connection.encrypted_credentials)).decode()
    return Credentials.from_authorized_user_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/calendar"])

def google_service(connection):
    return build("calendar", "v3", credentials=decrypt_credentials(connection), cache_discovery=False)

def google_is_free(host, starts_at, ends_at):
    if not host.calendar.encrypted_credentials:
        return True
    service = google_service(host.calendar)
    ids = host.calendar.busy_calendar_ids or [host.calendar.target_calendar_id]
    result = service.freebusy().query(body={"timeMin": starts_at.isoformat(), "timeMax": ends_at.isoformat(), "items": [{"id": value} for value in ids]}).execute()
    return not any(result.get("calendars", {}).get(value, {}).get("busy") for value in ids)

def host_is_free(host, starts_at, ends_at, include_google=True, exclude_booking=None):
    bookings = Booking.objects.filter(host=host, status=Booking.STATUS_CONFIRMED, starts_at__lt=ends_at, ends_at__gt=starts_at)
    if exclude_booking:
        bookings = bookings.exclude(pk=exclude_booking.pk)
    if bookings.exists():
        return False
    if SlotHold.objects.filter(host=host, expires_at__gt=timezone.now(), starts_at__lt=ends_at, ends_at__gt=starts_at).exists():
        return False
    if TimeOff.objects.filter(host=host, starts_at__lt=ends_at, ends_at__gt=starts_at).exists():
        return False
    return google_is_free(host, starts_at, ends_at) if include_google else True

def available_slots(booking_type, days=14):
    zone = ZoneInfo(booking_type.timezone)
    now = timezone.now()
    earliest = now + timedelta(hours=booking_type.minimum_notice_hours)
    horizon = now + timedelta(days=min(days, booking_type.booking_horizon_days))
    hosts = list(booking_type.hosts.filter(active=True).select_related("calendar").prefetch_related("working_hours"))
    slots = []
    cursor_date = earliest.astimezone(zone).date()
    while datetime.combine(cursor_date, datetime.min.time(), zone) < horizon and len(slots) < 120:
        for host in hosts:
            for hours in host.working_hours.filter(weekday=cursor_date.weekday()):
                cursor = datetime.combine(cursor_date, hours.start_time, zone)
                end_boundary = datetime.combine(cursor_date, hours.end_time, zone)
                while cursor + timedelta(minutes=booking_type.duration_minutes) <= end_boundary:
                    end = cursor + timedelta(minutes=booking_type.duration_minutes)
                    if cursor >= earliest and cursor < horizon and host_is_free(host, cursor, end, include_google=False):
                        slots.append({"host": host, "start": cursor, "end": end})
                    cursor += timedelta(minutes=max(15, booking_type.duration_minutes))
        cursor_date += timedelta(days=1)
    grouped = {}
    for slot in sorted(slots, key=lambda item: item["start"]):
        grouped.setdefault(slot["start"].isoformat(), slot)
    return list(grouped.values())[:80]

@transaction.atomic
def create_booking(booking_type, customer, starts_at, journey=None):
    hosts = booking_type.hosts.select_for_update().filter(active=True).select_related("calendar").order_by("last_assigned_at", "pk")
    if booking_type.assignment_mode == BookingType.ASSIGN_SPECIFIC:
        hosts = hosts.order_by("pk")[:1]
    ends_at = starts_at + timedelta(minutes=booking_type.duration_minutes)
    chosen = None
    for host in hosts:
        if host_is_free(host, starts_at, ends_at):
            chosen = host
            break
    if not chosen:
        raise ValueError("That time is no longer available. Please select another slot.")
    booking = Booking.objects.create(booking_type=booking_type, host=chosen, customer=customer, journey=journey, starts_at=starts_at, ends_at=ends_at, timezone=booking_type.timezone)
    if chosen.calendar.encrypted_credentials:
        event = google_service(chosen.calendar).events().insert(calendarId=chosen.calendar.target_calendar_id, body={
            "summary": f"{booking_type.name_en} — {customer.name or customer.email}",
            "description": f"Customer: {customer.email}",
            "location": booking_type.location,
            "start": {"dateTime": starts_at.isoformat(), "timeZone": booking_type.timezone},
            "end": {"dateTime": ends_at.isoformat(), "timeZone": booking_type.timezone},
            "attendees": [{"email": customer.email}],
        }, sendUpdates="all").execute()
        booking.google_event_id = event.get("id", "")
        booking.save(update_fields=["google_event_id"])
    chosen.last_assigned_at = timezone.now()
    chosen.save(update_fields=["last_assigned_at"])
    if journey:
        journey.status = "completed"
        journey.completed_at = timezone.now()
        journey.completion_source = "booking"
        journey.save(update_fields=["status", "completed_at", "completion_source"])
        from automations.services import cancel_journey_emails
        cancel_journey_emails(journey)
    from automations.services import schedule_booking_email
    transaction.on_commit(lambda: schedule_booking_email(booking, "booking_confirmation"))
    return booking

@transaction.atomic
def reschedule_booking(booking, starts_at):
    booking = Booking.objects.select_for_update().select_related("host__calendar", "booking_type", "customer").get(pk=booking.pk)
    ends_at = starts_at + timedelta(minutes=booking.booking_type.duration_minutes)
    if not host_is_free(booking.host, starts_at, ends_at, include_google=False, exclude_booking=booking):
        raise ValueError("That time is no longer available.")
    if booking.google_event_id and booking.host.calendar.encrypted_credentials:
        google_service(booking.host.calendar).events().patch(calendarId=booking.host.calendar.target_calendar_id, eventId=booking.google_event_id, body={"start": {"dateTime": starts_at.isoformat(), "timeZone": booking.timezone}, "end": {"dateTime": ends_at.isoformat(), "timeZone": booking.timezone}}).execute()
    booking.starts_at = starts_at
    booking.ends_at = ends_at
    booking.status = Booking.STATUS_CONFIRMED
    booking.save(update_fields=["starts_at", "ends_at", "status", "updated_at"])
    from automations.services import schedule_booking_email
    transaction.on_commit(lambda: schedule_booking_email(booking, "booking_rescheduled"))
    return booking

