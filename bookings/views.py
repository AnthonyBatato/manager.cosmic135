from datetime import datetime
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from google_auth_oauthlib.flow import Flow
from commerce.models import Customer, Journey
from .models import Booking, BookingType, CalendarConnection
from .services import available_slots, create_booking, encrypt_credentials, google_service, reschedule_booking
from users.auth import owner_required

def _booking_context(booking_type, journey=None):
    return {"booking_type": booking_type, "journey": journey, "slots": available_slots(booking_type)}

def booking_start(request, slug):
    booking_type = get_object_or_404(BookingType, slug=slug, active=True)
    return _handle_booking(request, booking_type, None)

def booking_start_id(request, booking_type_id):
    booking_type = get_object_or_404(BookingType, pk=booking_type_id, active=True)
    return _handle_booking(request, booking_type, None)

def booking_with_journey(request, booking_type_id, journey_token):
    booking_type = get_object_or_404(BookingType, pk=booking_type_id, active=True)
    journey = get_object_or_404(Journey.objects.select_related("customer"), token=journey_token, status=Journey.STATUS_PENDING)
    return _handle_booking(request, booking_type, journey)

def _handle_booking(request, booking_type, journey):
    if request.method == "POST":
        try:
            starts_at = datetime.fromisoformat(request.POST["starts_at"])
            if starts_at.tzinfo is None: starts_at = starts_at.replace(tzinfo=ZoneInfo(booking_type.timezone))
            if journey:
                customer = journey.customer
            else:
                email = request.POST["email"].strip().lower()
                customer, _ = Customer.objects.get_or_create(email=email, defaults={"name": request.POST.get("name", "").strip()})
            booking = create_booking(booking_type, customer, starts_at, journey)
        except (KeyError, ValueError) as exc:
            messages.error(request, str(exc))
        else:
            return redirect("booking_confirmed", token=booking.cancellation_token)
    return render(request, "bookings/start.html", _booking_context(booking_type, journey))

def booking_confirmed(request, token):
    return render(request, "bookings/confirmed.html", {"booking": get_object_or_404(Booking.objects.select_related("booking_type", "host", "customer"), cancellation_token=token)})

def booking_cancel(request, token):
    booking = get_object_or_404(Booking, cancellation_token=token)
    if request.method == "POST" and booking.status != Booking.STATUS_CANCELLED:
        booking.status = Booking.STATUS_CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        if booking.google_event_id and booking.host.calendar.encrypted_credentials:
            google_service(booking.host.calendar).events().delete(calendarId=booking.host.calendar.target_calendar_id, eventId=booking.google_event_id, sendUpdates="all").execute()
        from automations.services import schedule_booking_email
        schedule_booking_email(booking, "booking_cancelled")
        messages.success(request, "Booking cancelled.")
    return render(request, "bookings/confirmed.html", {"booking": booking})

def booking_reschedule(request, token):
    booking = get_object_or_404(Booking.objects.select_related("booking_type", "host", "customer"), cancellation_token=token)
    slots = available_slots(booking.booking_type)
    if request.method == "POST":
        try:
            starts_at = datetime.fromisoformat(request.POST["starts_at"])
            if starts_at.tzinfo is None: starts_at = starts_at.replace(tzinfo=ZoneInfo(booking.timezone))
            reschedule_booking(booking, starts_at)
        except (KeyError, ValueError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Booking rescheduled.")
            return redirect("booking_confirmed", token=token)
    return render(request, "bookings/reschedule.html", {"booking": booking, "slots": slots})

@owner_required
def google_connect(request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        messages.error(request, "Google OAuth credentials are not configured.")
        return redirect("home")
    flow = Flow.from_client_config({"web": {"client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, scopes=["https://www.googleapis.com/auth/calendar"], redirect_uri=request.build_absolute_uri(reverse("google_callback")))
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    request.session["google_oauth_state"] = state
    return redirect(url)

@owner_required
def google_callback(request):
    state = request.session.pop("google_oauth_state", "")
    flow = Flow.from_client_config({"web": {"client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET, "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}, scopes=["https://www.googleapis.com/auth/calendar"], state=state, redirect_uri=request.build_absolute_uri(reverse("google_callback")))
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    service = __import__("googleapiclient.discovery", fromlist=["build"]).build("calendar", "v3", credentials=flow.credentials, cache_discovery=False)
    primary = service.calendars().get(calendarId="primary").execute()
    CalendarConnection.objects.update_or_create(user=request.user, email=primary.get("id", request.user.email), defaults={"encrypted_credentials": encrypt_credentials(flow.credentials), "target_calendar_id": "primary", "busy_calendar_ids": ["primary"], "active": True})
    messages.success(request, "Google Calendar connected.")
    return redirect("home")

