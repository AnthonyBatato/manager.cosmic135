from django.db import models

class EmailTemplate(models.Model):
    KIND_CHOICES = [(x, x.replace("_", " ").title()) for x in ["payment_confirmation", "action_request", "reminder", "booking_confirmation", "booking_cancelled", "booking_rescheduled"]]
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    subject_en = models.CharField(max_length=250)
    subject_zh = models.CharField(max_length=250, blank=True)
    body_en = models.TextField()
    body_zh = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class ReminderStep(models.Model):
    name = models.CharField(max_length=120)
    delay_hours = models.PositiveIntegerField()
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    class Meta: ordering = ["delay_hours"]

class EmailDelivery(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    journey = models.ForeignKey("commerce.Journey", null=True, blank=True, on_delete=models.CASCADE, related_name="emails")
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.CASCADE, related_name="emails")
    template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT)
    reminder_step = models.ForeignKey(ReminderStep, null=True, blank=True, on_delete=models.SET_NULL)
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=16, default=STATUS_QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["journey", "template", "reminder_step"], name="unique_journey_email_step"),
            models.CheckConstraint(
                condition=(models.Q(journey__isnull=False, booking__isnull=True) | models.Q(journey__isnull=True, booking__isnull=False)),
                name="email_delivery_exactly_one_subject",
            ),
        ]

