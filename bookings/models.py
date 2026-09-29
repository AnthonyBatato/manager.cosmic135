import secrets
from datetime import time
from django.db import models
from django.utils import timezone

def secure_token():
    return secrets.token_urlsafe(32)

class CalendarConnection(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="calendar_connections")
    email = models.EmailField()
    encrypted_credentials = models.BinaryField(blank=True)
    target_calendar_id = models.CharField(max_length=255, default="primary")
    busy_calendar_ids = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.email

class Host(models.Model):
    name = models.CharField(max_length=120)
    calendar = models.OneToOneField(CalendarConnection, on_delete=models.CASCADE, related_name="host")
    active = models.BooleanField(default=True)
    last_assigned_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return self.name

class WorkingHours(models.Model):
    host = models.ForeignKey(Host, on_delete=models.CASCADE, related_name="working_hours")
    weekday = models.PositiveSmallIntegerField(help_text="Monday=0")
    start_time = models.TimeField(default=time(9, 0))
    end_time = models.TimeField(default=time(17, 0))
    class Meta:
        constraints = [models.UniqueConstraint(fields=["host", "weekday", "start_time"], name="unique_host_hours")]

class TimeOff(models.Model):
    host = models.ForeignKey(Host, on_delete=models.CASCADE, related_name="time_off")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=160, blank=True)

class BookingType(models.Model):
    ASSIGN_ROUND_ROBIN = "round_robin"
    ASSIGN_SPECIFIC = "specific"
    name_en = models.CharField(max_length=160)
    name_zh = models.CharField(max_length=160, blank=True)
    slug = models.SlugField(unique=True)
    instructions_en = models.TextField(blank=True)
    instructions_zh = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    buffer_before_minutes = models.PositiveIntegerField(default=0)
    buffer_after_minutes = models.PositiveIntegerField(default=0)
    minimum_notice_hours = models.PositiveIntegerField(default=24)
    booking_horizon_days = models.PositiveIntegerField(default=60)
    timezone = models.CharField(max_length=64, default="Asia/Kuala_Lumpur")
    location = models.CharField(max_length=255, blank=True)
    assignment_mode = models.CharField(max_length=20, choices=[(ASSIGN_ROUND_ROBIN, "Round robin"), (ASSIGN_SPECIFIC, "Specific host")], default=ASSIGN_ROUND_ROBIN)
    hosts = models.ManyToManyField(Host, related_name="booking_types")
    active = models.BooleanField(default=True)
    def __str__(self): return self.name_en

class SlotHold(models.Model):
    booking_type = models.ForeignKey(BookingType, on_delete=models.CASCADE)
    host = models.ForeignKey(Host, on_delete=models.CASCADE)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    token = models.CharField(max_length=64, unique=True, default=secure_token)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

class Booking(models.Model):
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    booking_type = models.ForeignKey(BookingType, on_delete=models.PROTECT, related_name="bookings")
    host = models.ForeignKey(Host, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey("commerce.Customer", on_delete=models.CASCADE, related_name="bookings")
    journey = models.ForeignKey("commerce.Journey", null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    timezone = models.CharField(max_length=64)
    google_event_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, default=STATUS_CONFIRMED)
    cancellation_token = models.CharField(max_length=64, unique=True, default=secure_token)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["host", "starts_at", "status"], name="unique_host_booking_slot")]

