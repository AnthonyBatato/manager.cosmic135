import secrets

from django.db import models


def registration_token():
    return secrets.token_urlsafe(40)


class RegistrationSeat(models.Model):
    LINK_PENDING = "pending"
    LINK_READY = "ready"
    LINK_FAILED = "failed"
    journey = models.ForeignKey("commerce.Journey", on_delete=models.CASCADE, related_name="registration_seats")
    seat_number = models.PositiveSmallIntegerField()
    token = models.CharField(max_length=80, unique=True, default=registration_token)
    registration_url = models.URLField(blank=True)
    link_status = models.CharField(max_length=16, default=LINK_PENDING)
    error = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    submission_id = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["seat_number"]
        constraints = [
            models.UniqueConstraint(fields=["journey", "seat_number"], name="unique_registration_seat"),
        ]

    def __str__(self):
        return f"Journey {self.journey_id}, participant {self.seat_number}"

class FormCompletionEvent(models.Model):
    event_id = models.CharField(max_length=160, unique=True)
    journey = models.ForeignKey("commerce.Journey", on_delete=models.CASCADE, related_name="form_events")
    seat = models.ForeignKey(RegistrationSeat, null=True, blank=True, on_delete=models.SET_NULL, related_name="form_events")
    submission_id = models.CharField(max_length=160)
    completed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

