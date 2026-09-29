import secrets
from django.db import models
from django.utils import timezone

def journey_token():
    return secrets.token_urlsafe(40)

class Offer(models.Model):
    name = models.CharField(max_length=160)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    external_checkout_url = models.URLField(blank=True)
    currency = models.CharField(max_length=3, default="MYR")
    destination_type = models.CharField(max_length=16, choices=[("form", "Form"), ("booking", "Booking")], default="form")
    destination_id = models.PositiveBigIntegerField(null=True, blank=True)
    destination_url = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Customer(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    preferred_language = models.CharField(max_length=8, choices=[("en", "English"), ("zh", "中文")], default="en")
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.email

class CheckoutAttempt(models.Model):
    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"
    page = models.ForeignKey("pages.LandingPage", on_delete=models.CASCADE)
    action = models.ForeignKey("pages.ActionMapping", on_delete=models.CASCADE)
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT)
    page_version = models.ForeignKey("pages.PageVersion", null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)
    stripe_session_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, default=STATUS_CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Payment(models.Model):
    attempt = models.OneToOneField(CheckoutAttempt, on_delete=models.CASCADE)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    amount_total = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="myr")
    status = models.CharField(max_length=32, default="paid")
    paid_at = models.DateTimeField(default=timezone.now)

class StripeEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Journey(models.Model):
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="journey")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="journeys")
    token = models.CharField(max_length=80, unique=True, default=journey_token)
    destination_type = models.CharField(max_length=16, choices=[("booking", "Booking"), ("form", "Form")], default="form")
    destination_id = models.PositiveBigIntegerField(null=True, blank=True)
    destination_url = models.URLField(blank=True)
    status = models.CharField(max_length=16, default=STATUS_PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_source = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

